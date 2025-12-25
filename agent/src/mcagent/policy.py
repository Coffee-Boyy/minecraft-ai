"""VLM policy for generating Minecraft actions from screenshots."""

import json
import time
import traceback
from typing import Optional

import httpx

from .config import Config
from .protocol import ActionMessage


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
        self.client = httpx.Client(timeout=30.0)
        self.system_prompt = f"""You are a Minecraft control policy. Given a screenshot and goal, output ONLY a JSON action.

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

        # Build the user prompt
        user_text = f"Goal: {goal}"
        if state:
            user_text += f"\nState: {json.dumps(state)}"

        # Prepare the API request
        payload = {
            "model": self.config.vllm_model,
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
            "response_format": {
                "type": "json_schema",
                "json_schema": ACTION_JSON_SCHEMA,
            },
        }

        try:
            # print(f"[Policy] Request: {json.dumps(payload)}")
            response = self.client.post(
                f"{self.config.vllm_base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            # Extract the content
            content = result["choices"][0]["message"]["content"]
            print(f"[Policy] VLM response content: {content}")

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
        self.client.close()
