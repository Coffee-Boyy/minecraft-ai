"""WebSocket protocol message schemas for Minecraft bridge communication."""

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Key(str, Enum):
    """Valid keyboard keys."""

    W = "W"
    A = "A"
    S = "S"
    D = "D"
    SPACE = "SPACE"
    SHIFT = "SHIFT"
    CTRL = "CTRL"
    E = "E"
    Q = "Q"
    F = "F"
    ESC = "ESC"
    SPRINT = "SPRINT"


class Click(str, Enum):
    """Valid click actions."""

    NONE = "NONE"
    LMB = "LMB"
    RMB = "RMB"
    MMB = "MMB"


class Keys(BaseModel):
    """Key press and release actions."""

    down: list[Key] = Field(default_factory=list)
    up: list[Key] = Field(default_factory=list)


class Mouse(BaseModel):
    """Mouse movement deltas."""

    yaw_delta_deg: float = Field(ge=-12, le=12)
    pitch_delta_deg: float = Field(ge=-12, le=12)


class ActionPayload(BaseModel):
    """Payload for an action command."""

    id: str
    duration_ms: int = Field(ge=20, le=2000)
    keys: Keys
    mouse: Mouse
    click: Click
    hotbar: int = Field(ge=0, le=9, description="0 means no change; 1-9 selects slot")


class ActionEnvelope(BaseModel):
    """Complete action message envelope."""

    type: Literal["action"] = "action"
    ts: int
    payload: ActionPayload


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


class AckPayload(BaseModel):
    """Acknowledgment payload."""

    action_id: str
    applied: bool
    err: Optional[str] = None


class AckMessage(BaseModel):
    """Acknowledgment message."""

    type: Literal["ack"] = "ack"
    ts: int
    payload: AckPayload


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
Message = HelloMessage | ActionEnvelope | AckMessage | StateMessage
