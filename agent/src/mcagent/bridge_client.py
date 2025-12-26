"""WebSocket client for communicating with the Minecraft bridge mod."""

import json
import struct
import time
from typing import Optional, Callable

import websockets
from websockets.client import WebSocketClientProtocol

from .protocol import (
    ActionMessage,
    AckMessage,
    StateMessage,
)

# Binary message types from mod
MSG_TYPE_FRAME = 0x01


class BridgeClient:
    """WebSocket client for the Minecraft bridge."""

    def __init__(self, ws_url: str):
        """Initialize the bridge client."""
        self.ws_url = ws_url
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.capabilities = {}
        self.latest_state: Optional[StateMessage] = None
        self._on_state_callback: Optional[Callable[[StateMessage], None]] = None
        self._on_ack_callback: Optional[Callable[[AckMessage], None]] = None
        self._on_frame_callback: Optional[Callable[[bytes, int, int], None]] = None
        self._last_send_time = 0.0

        # Frame state
        self.latest_frame: Optional[bytes] = None
        self.latest_frame_seq: int = 0
        self.latest_frame_ts: int = 0

    async def connect(self) -> bool:
        """
        Connect to the Minecraft bridge WebSocket server.

        Returns:
            True if connection successful
        """
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.connected = True

            # Set default capabilities (the mod doesn't implement hello protocol)
            self.capabilities = {
                "supports_mouse": False,
                "supports_inventory": False,
                "supports_chat_cmd": False,
            }

            return True

        except Exception as e:
            self.connected = False
            raise ConnectionError(f"Failed to connect to bridge: {e}")

    async def send_action(self, action: ActionMessage) -> bool:
        """
        Send an action to the Minecraft bridge.

        Args:
            action: The action to send

        Returns:
            True if sent successfully
        """
        if not self.connected or not self.ws:
            return False

        start = time.perf_counter()

        try:
            await self.ws.send(action.model_dump_json())
            self._last_send_time = time.perf_counter() - start
            return True
        except Exception as e:
            print(f"Error sending action: {e}")
            return False

    async def receive_messages(self):
        """
        Continuously receive and process messages from the bridge.

        This should be run as a background task.
        """
        if not self.ws:
            return

        print("[DEBUG] Starting to receive messages...")
        try:
            async for message in self.ws:
                if isinstance(message, bytes):
                    self._handle_binary_message(message)
                else:
                    await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            print("[DEBUG] WebSocket connection closed")
            self.connected = False
        except Exception as e:
            print(f"[DEBUG] Error receiving messages: {e}")
            self.connected = False

    def _handle_binary_message(self, data: bytes):
        """Handle a binary WebSocket message (frames)."""
        if len(data) < 9:
            print(f"[DEBUG] Received binary message too short: {len(data)} bytes")
            return

        msg_type = data[0]
        if msg_type == MSG_TYPE_FRAME:
            # Parse header: type(1) + seq(4) + ts(4) + jpeg_data
            seq, ts = struct.unpack(">II", data[1:9])
            frame_data = data[9:]

            self.latest_frame = frame_data
            self.latest_frame_seq = seq
            self.latest_frame_ts = ts

            if self._on_frame_callback:
                self._on_frame_callback(frame_data, seq, ts)

    async def _handle_message(self, message: str):
        """Handle an incoming message from the bridge."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "ack":
                ack = AckMessage.model_validate(data)
                if self._on_ack_callback:
                    self._on_ack_callback(ack)

            elif msg_type == "state":
                state = StateMessage.model_validate(data)
                self.latest_state = state
                if self._on_state_callback:
                    self._on_state_callback(state)

        except Exception as e:
            print(f"Error handling message: {e}")

    def set_state_callback(self, callback: Callable[[StateMessage], None]):
        """Set callback for state updates."""
        self._on_state_callback = callback

    def set_ack_callback(self, callback: Callable[[AckMessage], None]):
        """Set callback for acknowledgments."""
        self._on_ack_callback = callback

    def set_frame_callback(self, callback: Callable[[bytes, int, int], None]):
        """
        Set callback for frame updates.

        Args:
            callback: Function receiving (frame_data: bytes, sequence: int, timestamp: int)
        """
        self._on_frame_callback = callback

    async def configure_frames(
        self,
        enabled: bool = True,
        width: int = 854,
        height: int = 480,
        capture_every_n_frames: int = 1,
        jpeg_quality: float = 0.75,
    ):
        """
        Configure frame capture settings on the mod.

        Args:
            enabled: Whether frame capture is enabled
            width: Target frame width
            height: Target frame height
            capture_every_n_frames: Capture every N frames (1 = every frame, 2 = every other)
            jpeg_quality: JPEG compression quality (0.0 to 1.0)
        """
        if not self.connected or not self.ws:
            return

        config = {
            "type": "frame_config",
            "enabled": enabled,
            "width": width,
            "height": height,
            "captureEveryNFrames": capture_every_n_frames,
            "jpegQuality": jpeg_quality,
        }
        config_json = json.dumps(config)
        print(f"[DEBUG] Sending frame config: {config_json}")
        await self.ws.send(config_json)

    def get_last_send_time_ms(self) -> float:
        """Get the time taken for the last send in milliseconds."""
        return self._last_send_time * 1000

    async def close(self):
        """Close the WebSocket connection."""
        if self.ws:
            await self.ws.close()
            self.connected = False

    @staticmethod
    def _get_timestamp_ms() -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
