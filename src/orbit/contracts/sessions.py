"""Session and connection lifecycle contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SessionState(str, Enum):
    """Lifecycle state of an operator session."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISCONNECTED = "DISCONNECTED"
    TERMINATED = "TERMINATED"


class DisconnectionPolicy(str, Enum):
    """Action to take when a client WebSocket drops connection."""

    PAUSE_ACTIVE_TASKS = "PAUSE_ACTIVE_TASKS"
    CANCEL_ACTIVE_TASKS = "CANCEL_ACTIVE_TASKS"
    ALLOW_HEADLESS = "ALLOW_HEADLESS"


class ClientConnectionInfo(BaseModel):
    """Metadata describing a connected client WebSocket."""

    connection_id: str = Field(..., description="Unique connection instance ID")
    client_ip: str = Field(default="127.0.0.1", description="Client IP address")
    user_agent: str = Field(default="ORBIT-Client/1.0", description="Client user agent identifier")
    connected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Session(BaseModel):
    """Operator session state record."""

    session_id: str = Field(..., description="Unique session identifier")
    state: SessionState = Field(default=SessionState.CREATED, description="Current session state")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_task_id: Optional[str] = Field(default=None, description="Currently executing task ID")
    disconnection_policy: DisconnectionPolicy = Field(
        default=DisconnectionPolicy.PAUSE_ACTIVE_TASKS,
        description="Policy enforced when the active WebSocket disconnects",
    )
    connection: Optional[ClientConnectionInfo] = Field(
        default=None,
        description="Active client connection info if connected",
    )
