"""Configuration management for the Minecraft AI agent."""

import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class Config:
    """Agent configuration loaded from environment variables."""

    vllm_base_url: str
    vllm_model: str
    bridge_ws_url: str
    capture_mode: Literal["screen", "window", "mod"]
    capture_window_title: str
    capture_fps: int
    decision_hz: int
    max_new_tokens: int
    output_strict_json: bool
    action_duration_ms_default: int
    kill_switch_key: str
    max_actions_per_minute: int
    capture_resolution: tuple[int, int]
    jpeg_quality: float

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            vllm_base_url=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1"),
            vllm_model=os.getenv("VLLM_MODEL", "Qwen2.5-VL-7B-Instruct"),
            bridge_ws_url=os.getenv("BRIDGE_WS_URL", "ws://127.0.0.1:8765/ws"),
            capture_mode=os.getenv("CAPTURE_MODE", "mod"),  # type: ignore
            capture_window_title=os.getenv("CAPTURE_WINDOW_TITLE", "Minecraft"),
            capture_fps=int(os.getenv("CAPTURE_FPS", "10")),
            decision_hz=int(os.getenv("DECISION_HZ", "6")),
            max_new_tokens=int(os.getenv("MAX_NEW_TOKENS", "64")),
            output_strict_json=bool(int(os.getenv("OUTPUT_STRICT_JSON", "1"))),
            action_duration_ms_default=int(os.getenv("ACTION_DURATION_MS_DEFAULT", "150")),
            kill_switch_key=os.getenv("KILL_SWITCH_KEY", "F10"),
            max_actions_per_minute=int(os.getenv("MAX_ACTIONS_PER_MINUTE", "1200")),
            capture_resolution=(854, 480),  # 480p as per spec
            jpeg_quality=float(os.getenv("JPEG_QUALITY", "0.75")),
        )

    def __str__(self) -> str:
        """Return a formatted string representation of the config."""
        return (
            f"Config:\n"
            f"  VLM: {self.vllm_base_url} ({self.vllm_model})\n"
            f"  Bridge: {self.bridge_ws_url}\n"
            f"  Capture: {self.capture_mode} @ {self.capture_fps} fps "
            f"({self.capture_resolution[0]}x{self.capture_resolution[1]})\n"
            f"  Decision Hz: {self.decision_hz}\n"
            f"  Max Tokens: {self.max_new_tokens}\n"
            f"  Kill Switch: {self.kill_switch_key}"
        )
