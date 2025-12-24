"""WebSocket protocol message schemas for Minecraft bridge communication."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class ActionMessage(BaseModel):
    """Action message matching Java Protocol.ActionMessage."""

    type: Literal["action"] = "action"
    forward: float = Field(ge=-1.0, le=1.0, default=0.0)  # -1.0 to 1.0
    strafe: float = Field(ge=-1.0, le=1.0, default=0.0)   # -1.0 to 1.0
    yaw: float = Field(default=0.0)     # degrees (absolute, not delta)
    pitch: float = Field(default=0.0)   # degrees (absolute, not delta)
    jump: bool = False
    attack: bool = False
    use: bool = False
    sneak: bool = False
    sprint: bool = False
    duration_ms: int = Field(ge=20, le=2000, default=150)


class Capabilities(BaseModel):
    """Bridge capabilities."""

    supports_mouse: bool = True
    supports_inventory: bool = True
    supports_chat_cmd: bool = False


class HelloPayload(BaseModel):
    """Hello handshake payload."""

    version: str
    capabilities: Capabilities


class HelloMessage(BaseModel):
    """Hello handshake message."""

    type: Literal["hello"] = "hello"
    ts: int
    payload: HelloPayload


class AckMessage(BaseModel):
    """Acknowledgment message from Java bridge."""

    type: Literal["ack"] = "ack"
    action_type: str
    success: bool
    error: Optional[str] = None


class PlayerState(BaseModel):
    """Player state information from Java bridge."""

    x: float
    y: float
    z: float
    yaw: float
    pitch: float
    health: float
    food: float
    experience_level: int
    on_ground: bool
    in_water: bool
    in_lava: bool


class WorldState(BaseModel):
    """World state information from Java bridge."""

    dimension: str
    time: int
    is_raining: bool
    is_thundering: bool


class StateMessage(BaseModel):
    """State update message from Java bridge."""

    type: Literal["state"] = "state"
    player: PlayerState
    world: WorldState


# Union type for all message types
Message = HelloMessage | ActionMessage | AckMessage | StateMessage
