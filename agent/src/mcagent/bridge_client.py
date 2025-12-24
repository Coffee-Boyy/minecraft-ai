"""WebSocket client for communicating with the Minecraft bridge mod."""

import asyncio
import json
import time
from typing import Optional, Callable

import websockets
from websockets.client import WebSocketClientProtocol

from .protocol import (
    ActionEnvelope,
    ActionPayload,
    HelloMessage,
    AckMessage,
    StateMessage,
)


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
        self._last_send_time = 0.0

    async def connect(self) -> bool:
        """
        Connect to the Minecraft bridge WebSocket server.

        Returns:
            True if connection successful
        """
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.connected = True

            # Send hello message
            hello = HelloMessage(
                type="hello",
                ts=self._get_timestamp_ms(),
                payload={
                    "version": "0.1.0",
                    "capabilities": {
                        "supports_mouse": True,
                        "supports_inventory": True,
                        "supports_chat_cmd": False,
                    },
                },
            )
            await self.ws.send(hello.model_dump_json())

            # Wait for hello response
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            hello_msg = HelloMessage.model_validate_json(response)
            self.capabilities = hello_msg.payload.capabilities.model_dump()

            return True

        except Exception as e:
            self.connected = False
            raise ConnectionError(f"Failed to connect to bridge: {e}")

    async def send_action(self, action: ActionPayload) -> bool:
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

        envelope = ActionEnvelope(
            type="action",
            ts=self._get_timestamp_ms(),
            payload=action,
        )

        try:
            await self.ws.send(envelope.model_dump_json())
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

        try:
            async for message in self.ws:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
        except Exception as e:
            print(f"Error receiving messages: {e}")
            self.connected = False

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

    def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
