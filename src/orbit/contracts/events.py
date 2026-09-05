"""Outbound WebSocket and runtime event envelopes and payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from orbit.contracts.runtime import (
    Action,
    ActionStage,
    ExecutionPlan,
    SystemState,
    TaskStatus,
)
from orbit.contracts.sessions import SessionState
from orbit.models.common import ErrorDetail


class EventType(str, Enum):
    """Classification of outbound events emitted by ORBIT."""

    RUNTIME_STATUS = "RUNTIME_STATUS"
    SESSION_STATE_CHANGED = "SESSION_STATE_CHANGED"
    TASK_STATE_CHANGED = "TASK_STATE_CHANGED"
    PLAN_UPDATED = "PLAN_UPDATED"
    ACTION_STAGE_CHANGED = "ACTION_STAGE_CHANGED"
    OBSERVATION_FRAME = "OBSERVATION_FRAME"
    TAKEOVER_EVENT = "TAKEOVER_EVENT"
    ACTION_AUTHORIZATION_REQUIRED = "ACTION_AUTHORIZATION_REQUIRED"
    RECOVERY_EVENT = "RECOVERY_EVENT"
    POINTER_MOVED = "POINTER_MOVED"
    POINTER_CLICKED = "POINTER_CLICKED"
    POINTER_BUTTON_STATE_CHANGED = "POINTER_BUTTON_STATE_CHANGED"
    POINTER_LOCKOUT_CHANGED = "POINTER_LOCKOUT_CHANGED"
    KEYBOARD_TYPED = "KEYBOARD_TYPED"
    SHORTCUT_EXECUTED = "SHORTCUT_EXECUTED"
    KEYBOARD_KEY_STATE_CHANGED = "KEYBOARD_KEY_STATE_CHANGED"
    KEYBOARD_LOCKOUT_CHANGED = "KEYBOARD_LOCKOUT_CHANGED"
    ERROR = "ERROR"
    HEARTBEAT_ACK = "HEARTBEAT_ACK"



class RuntimeEvent(BaseModel):
    """Standardized event envelope sent over WebSocket and internal bus."""

    protocol_version: str = Field(default="1.0.0", description="Protocol version identifier")
    event_id: str = Field(..., description="Unique event identifier")
    event_type: EventType = Field(..., description="Event type classification")
    event_seq: int = Field(default=0, ge=0, description="Monotonically increasing sequence number")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str = Field(..., description="Associated session identifier")
    correlation_id: Optional[str] = Field(default=None, description="Request correlation identifier")
    causation_id: Optional[str] = Field(default=None, description="Immediate causal event identifier")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Structured event payload")


# Specific Payload Schemas for Type Validation

class RuntimeStatusPayload(BaseModel):
    system_state: SystemState
    active_session_id: Optional[str] = None
    active_task_id: Optional[str] = None
    capabilities: Dict[str, str] = Field(default_factory=dict)


class SessionStatePayload(BaseModel):
    session_id: str
    state: SessionState
    active_task_id: Optional[str] = None


class TaskStatePayload(BaseModel):
    task_id: str
    session_id: str
    status: TaskStatus
    prompt: str
    error: Optional[ErrorDetail] = None


class PlanUpdatedPayload(BaseModel):
    task_id: str
    plan: ExecutionPlan


class ActionStagePayload(BaseModel):
    action_id: str
    task_id: str
    stage: ActionStage
    action: Action


class TakeoverEventPayload(BaseModel):
    is_active: bool
    source: str = Field(default="human_input", description="human_input or manual_trigger")
    reason: Optional[str] = None


class ActionAuthRequiredPayload(BaseModel):
    action_id: str
    task_id: str
    action_type: str
    tier: str
    description: str
    parameters: Dict[str, Any]


class ErrorEventPayload(BaseModel):
    code: str
    message: str
    recoverable: bool = True
    details: Optional[Dict[str, Any]] = None
