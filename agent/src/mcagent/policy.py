"""VLM policy for generating Minecraft actions from screenshots."""

import base64
import json
import time
import traceback
from collections import deque
from pathlib import Path
from typing import Optional

import httpx

from .config import Config
from .protocol import ActionMessage


# Directory for debug frame captures
DEBUG_FRAMES_DIR = Path("./") / "mcagent_frames"


# JSON schema for the action format expected from the LLM
ACTION_SCHEMA_DESCRIPTION = """{
  "forward": float (-1.0 to 1.0, negative=backward),
  "strafe": float (-1.0 to 1.0, negative=left, positive=right),
  "yaw": float (absolute yaw in degrees, 0=south, 90=west, 180=north, -90=east),
  "pitch": float (absolute pitch in degrees, -90=up, 0=straight, 90=down),
  "jump": bool,
  "attack": bool (left click),
  "use": bool (right click),
  "sneak": bool,
  "sprint": bool,
  "duration_ms": int (20-2000, how long to hold this action)
}"""

# Formal JSON schema for structured output
ACTION_JSON_SCHEMA = {
    "name": "minecraft_action",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "forward": {
                "type": "number",
                "description": "Movement forward/backward (-1.0 to 1.0, negative=backward)",
            },
            "strafe": {
                "type": "number",
                "description": "Movement left/right (-1.0 to 1.0, negative=left, positive=right)",
            },
            "yaw": {
                "type": "number",
                "description": "Absolute yaw in degrees (0=south, 90=west, 180=north, -90=east)",
            },
            "pitch": {
                "type": "number",
                "description": "Absolute pitch in degrees (-90=up, 0=straight, 90=down)",
            },
            "jump": {"type": "boolean", "description": "Whether to jump"},
            "attack": {"type": "boolean", "description": "Left click (break blocks or hit entities)"},
            "use": {"type": "boolean", "description": "Right click (place blocks or interact)"},
            "sneak": {"type": "boolean", "description": "Whether to sneak"},
            "sprint": {"type": "boolean", "description": "Whether to sprint"},
            "duration_ms": {
                "type": "integer",
                "description": "How long to hold this action (20-2000ms)",
            },
        },
        "required": [
            "forward",
            "strafe",
            "yaw",
            "pitch",
            "jump",
            "attack",
            "use",
            "sneak",
            "sprint",
            "duration_ms",
        ],
        "additionalProperties": False,
    },
}


class VLMPolicy:
    """
    Vision-Language Model policy for Minecraft control.

    Sends screenshots to a VLM and parses JSON action responses.
    """

    def __init__(self, config: Config):
        """Initialize the VLM policy."""
        self.config = config
        # NOTE: We deliberately avoid keeping a long-lived sync HTTP client here.
        # The agent offloads inference to a worker thread, and httpx.Client is not
        # guaranteed to be safe to use across threads.
        self.system_prompt = f"""You are a Minecraft control policy. Given a screenshot of the current Minecraft world and goal, output ONLY a JSON action.

Action schema:
{ACTION_SCHEMA_DESCRIPTION}

Rules:
- Output ONLY valid JSON, no explanation or markdown
- Keep actions short (100-300ms duration) for responsive control
- Use forward=1.0 to walk forward, strafe for sideways movement
- Set jump=true to jump, sprint=true to run faster
- Use attack=true to break blocks or hit entities
- Use use=true to place blocks or interact"""
        self._last_inference_time = 0.0

        # Ring buffer for last 5 frames (stores tuples of (timestamp, image_bytes))
        self._frame_buffer: deque[tuple[float, bytes]] = deque(maxlen=5)
        self._frame_counter = 0

        # Ensure debug frames directory exists
        DEBUG_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[Policy] Debug frames will be saved to: {DEBUG_FRAMES_DIR}")

    def _save_frame_to_buffer(self, image_data_url: str) -> None:
        """Extract image bytes from data URL and save to ring buffer."""
        try:
            # Parse data URL: "data:image/png;base64,<data>" or "data:image/jpeg;base64,<data>"
            if not image_data_url.startswith("data:"):
                return

            # Extract the base64 part after the comma
            comma_idx = image_data_url.find(",")
            if comma_idx == -1:
                return

            b64_data = image_data_url[comma_idx + 1 :]
            image_bytes = base64.b64decode(b64_data)

            # Add to ring buffer with timestamp
            self._frame_buffer.append((time.time(), image_bytes))
            self._frame_counter += 1

            # Save all frames in buffer to temp files
            self._write_debug_frames()

        except Exception as e:
            print(f"[Policy] Error saving frame to buffer: {e}")

    def _write_debug_frames(self) -> None:
        """Write all frames in buffer to temp files."""
        for i, (_timestamp, image_bytes) in enumerate(self._frame_buffer):
            # Determine file extension from image header
            ext = ".png" if image_bytes[:4] == b"\x89PNG" else ".jpg"
            frame_path = DEBUG_FRAMES_DIR / f"frame_{i}{ext}"
            frame_path.write_bytes(image_bytes)

    def get_action(
        self, image_data_url: str, goal: str, state: Optional[dict] = None
    ) -> ActionMessage:
        """
        Get the next action from the VLM based on the current screenshot.

        Args:
            image_data_url: Base64-encoded image data URL (PNG or JPEG)
            goal: Current goal description
            state: Optional state information from Minecraft

        Returns:
            ActionMessage with the next action to take
        """
        start = time.perf_counter()

        # Save frame to debug buffer
        self._save_frame_to_buffer(image_data_url)

        # Build the user prompt
        user_text = f"Goal: {goal}"
        if state:
            user_text += f"\nState: {json.dumps(state)}"

        # Prepare the API request
        payload = {
            "model": self.config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
            "max_tokens": self.config.max_new_tokens,
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 0,
            "frequency_penalty": 1.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": ACTION_JSON_SCHEMA,
            },
        }

        try:
            # print(f"[Policy] Request: {json.dumps(payload)}")
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.config.LLM_BASE_URL}/chat/completions",
                    json=payload,
                )
            response.raise_for_status()
            result = response.json()

            # Extract the content
            content = result["choices"][0]["message"]["content"]
            print(f"[Policy] LLM response content: {content}")

            # Parse the JSON action
            action_dict = self._parse_action_json(content)
            action = self._dict_to_action(action_dict)

            self._last_inference_time = time.perf_counter() - start
            return action

        except httpx.HTTPStatusError as e:
            self._last_inference_time = time.perf_counter() - start
            print(f"[Policy] HTTP error: {e}")
            print(f"[Policy] Response body: {e.response.text}")
            traceback.print_exc()
            # Return a safe default action (do nothing)
            return self._get_default_action()

        except Exception as e:
            self._last_inference_time = time.perf_counter() - start
            print(f"[Policy] Error: {e}")
            traceback.print_exc()
            # Return a safe default action (do nothing)
            return self._get_default_action()

    def _parse_action_json(self, content: str) -> dict:
        """
        Parse JSON from the VLM response.

        Handles cases where the model might wrap JSON in markdown code blocks.
        """
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (code fence markers)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        # Try to find JSON content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from text
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = content[start_idx : end_idx + 1]
                return json.loads(json_str)
            raise

    def _dict_to_action(self, action_dict: dict) -> ActionMessage:
        """Convert a dictionary to an ActionMessage with validation."""
        return ActionMessage(
            forward=float(action_dict.get("forward", 0.0)),
            strafe=float(action_dict.get("strafe", 0.0)),
            yaw=float(action_dict.get("yaw", 0.0)),
            pitch=float(action_dict.get("pitch", 0.0)),
            jump=bool(action_dict.get("jump", False)),
            attack=bool(action_dict.get("attack", False)),
            use=bool(action_dict.get("use", False)),
            sneak=bool(action_dict.get("sneak", False)),
            sprint=bool(action_dict.get("sprint", False)),
            duration_ms=int(
                action_dict.get("duration_ms", self.config.action_duration_ms_default)
            ),
        )

    def _get_default_action(self) -> ActionMessage:
        """Get a safe default action (do nothing)."""
        return ActionMessage(
            forward=0.0,
            strafe=0.0,
            yaw=0.0,
            pitch=0.0,
            jump=False,
            attack=False,
            use=False,
            sneak=False,
            sprint=False,
            duration_ms=self.config.action_duration_ms_default,
        )

    def get_last_inference_time_ms(self) -> float:
        """Get the time taken for the last inference in milliseconds."""
        return self._last_inference_time * 1000

    def close(self):
        """Close the HTTP client."""
        # No-op: we create a short-lived httpx.Client per request for thread safety.
        return
