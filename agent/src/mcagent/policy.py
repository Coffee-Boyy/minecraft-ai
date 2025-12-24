"""VLM policy for generating Minecraft actions from screenshots."""

import json
import time
from typing import Optional

import httpx

from .config import Config
from .protocol import ActionPayload, Click, Keys, Mouse


class VLMPolicy:
    """
    Vision-Language Model policy for Minecraft control.

    Sends screenshots to Qwen2.5-VL and parses JSON action responses.
    """

    def __init__(self, config: Config):
        """Initialize the VLM policy."""
        self.config = config
        self.client = httpx.Client(timeout=30.0)
        self.system_prompt = (
            "You are a Minecraft control policy. You ONLY output strict JSON matching ActionSchema. "
            "No extra keys. No prose."
        )
        self._last_inference_time = 0.0

    def get_action(self, image_data_url: str, goal: str, state: Optional[dict] = None) -> ActionPayload:
        """
        Get the next action from the VLM based on the current screenshot.

        Args:
            image_data_url: Base64-encoded PNG image data URL
            goal: Current goal description
            state: Optional state information from Minecraft

        Returns:
            ActionPayload with the next action to take
        """
        start = time.perf_counter()

        # Build the user prompt
        user_text = (
            f"Given the screenshot, output the next action as JSON.\n"
            f"Current goal: {goal}.\n"
            f"Constraints: keep output <= 40 tokens if possible."
        )

        if state:
            user_text += f"\nCurrent state: {json.dumps(state)}"

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
            "temperature": 0.2,
        }

        # Call the VLM API
        try:
            response = self.client.post(
                f"{self.config.vllm_base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            # Extract the content
            content = result["choices"][0]["message"]["content"]

            # Parse the JSON action
            action_dict = self._parse_action_json(content)
            action = self._dict_to_action_payload(action_dict)

            self._last_inference_time = time.perf_counter() - start
            return action

        except Exception as e:
            self._last_inference_time = time.perf_counter() - start
            # Return a safe default action (do nothing)
            return self._get_default_action(f"Error: {str(e)}")

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

    def _dict_to_action_payload(self, action_dict: dict) -> ActionPayload:
        """Convert a dictionary to an ActionPayload with validation."""
        # Provide defaults for required fields
        duration_ms = action_dict.get("duration_ms", self.config.action_duration_ms_default)

        # Parse keys
        keys_data = action_dict.get("keys", {})
        keys = Keys(
            down=[k for k in keys_data.get("down", [])],
            up=[k for k in keys_data.get("up", [])],
        )

        # Parse mouse
        mouse_data = action_dict.get("mouse", {})
        mouse = Mouse(
            yaw_delta_deg=mouse_data.get("yaw_delta_deg", 0.0),
            pitch_delta_deg=mouse_data.get("pitch_delta_deg", 0.0),
        )

        # Parse click
        click_str = action_dict.get("click", "NONE")
        click = Click(click_str)

        # Parse hotbar
        hotbar = action_dict.get("hotbar", 0)

        # Generate action ID
        action_id = action_dict.get("id", f"act_{int(time.time() * 1000)}")

        return ActionPayload(
            id=action_id,
            duration_ms=duration_ms,
            keys=keys,
            mouse=mouse,
            click=click,
            hotbar=hotbar,
        )

    def _get_default_action(self, reason: str = "default") -> ActionPayload:
        """Get a safe default action (do nothing)."""
        return ActionPayload(
            id=f"default_{int(time.time() * 1000)}",
            duration_ms=self.config.action_duration_ms_default,
            keys=Keys(down=[], up=[]),
            mouse=Mouse(yaw_delta_deg=0.0, pitch_delta_deg=0.0),
            click=Click.NONE,
            hotbar=0,
        )

    def get_last_inference_time_ms(self) -> float:
        """Get the time taken for the last inference in milliseconds."""
        return self._last_inference_time * 1000

    def close(self):
        """Close the HTTP client."""
        self.client.close()
