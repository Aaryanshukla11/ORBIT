"""Inbound client command contracts and payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from orbit.contracts.sessions import DisconnectionPolicy


class CommandType(str, Enum):
    """Inbound client command classification."""

    SUBMIT_TASK = "SUBMIT_TASK"
    CANCEL_TASK = "CANCEL_TASK"
    PAUSE_TASK = "PAUSE_TASK"
    RESUME_TASK = "RESUME_TASK"
    AUTHORIZE_ACTION = "AUTHORIZE_ACTION"
    REQUEST_FRAME = "REQUEST_FRAME"
    TRIGGER_TAKEOVER = "TRIGGER_TAKEOVER"
    RELEASE_TAKEOVER = "RELEASE_TAKEOVER"
    RECOVER_LOCKED = "RECOVER_LOCKED"
    MOVE_POINTER = "MOVE_POINTER"
    CLICK_POINTER = "CLICK_POINTER"
    POINTER_BUTTON_DOWN = "POINTER_BUTTON_DOWN"
    POINTER_BUTTON_UP = "POINTER_BUTTON_UP"
    POINTER_EMERGENCY_RELEASE = "POINTER_EMERGENCY_RELEASE"
    RECOVER_POINTER_LOCKOUT = "RECOVER_POINTER_LOCKOUT"
    TYPE_TEXT = "TYPE_TEXT"
    PRESS_SHORTCUT = "PRESS_SHORTCUT"
    KEYBOARD_KEY_DOWN = "KEYBOARD_KEY_DOWN"
    KEYBOARD_KEY_UP = "KEYBOARD_KEY_UP"
    KEYBOARD_EMERGENCY_RELEASE = "KEYBOARD_EMERGENCY_RELEASE"
    RECOVER_KEYBOARD_LOCKOUT = "RECOVER_KEYBOARD_LOCKOUT"
    HEARTBEAT = "HEARTBEAT"
    MODEL_LIST = "MODEL_LIST"
    MODEL_STATUS = "MODEL_STATUS"
    MODEL_ACTIVE = "MODEL_ACTIVE"
    MODEL_DISCOVER = "MODEL_DISCOVER"
    MODEL_ACTIVATE = "MODEL_ACTIVATE"
    MODEL_SWITCH = "MODEL_SWITCH"
    MODEL_HEALTH = "MODEL_HEALTH"
    TASK_HISTORY_LIST = "TASK_HISTORY_LIST"
    TASK_HISTORY_DETAIL = "TASK_HISTORY_DETAIL"
    TASK_HISTORY_CLEAR = "TASK_HISTORY_CLEAR"
    DIAGNOSTICS_RUN = "DIAGNOSTICS_RUN"



class BaseCommand(BaseModel):
    """Base model for all inbound client commands."""

    command_id: str = Field(..., description="Unique command ID for request-response correlation")
    command_type: CommandType = Field(..., description="Command type classification")
    session_id: str = Field(..., description="Originating session identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = Field(default=None, description="Optional upstream correlation ID")


class SubmitTaskPayload(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural language prompt or command instruction")
    context: Dict[str, Any] = Field(default_factory=dict)
    disconnection_policy: DisconnectionPolicy = Field(default=DisconnectionPolicy.PAUSE_ACTIVE_TASKS)


class CancelTaskPayload(BaseModel):
    task_id: str
    reason: Optional[str] = None


class PauseTaskPayload(BaseModel):
    task_id: str
    reason: Optional[str] = None


class ResumeTaskPayload(BaseModel):
    task_id: str


class AuthorizeActionPayload(BaseModel):
    task_id: str
    action_id: str
    approved: bool = Field(..., description="True if operator approves execution, False to reject")
    reason: Optional[str] = None


class RequestFramePayload(BaseModel):
    display_index: int = Field(default=0, ge=0)
    format: str = Field(default="jpeg")


class TriggerTakeoverPayload(BaseModel):
    reason: Optional[str] = Field(default="Manual operator takeover triggered")


class ReleaseTakeoverPayload(BaseModel):
    pass


class RecoverLockedPayload(BaseModel):
    recovery_token: str = Field(
        default="CONFIRM_OPERATOR_MANUAL_RESET",
        description="Explicit security token to clear hardware lockouts",
    )


class MovePointerPayload(BaseModel):
    x: int = Field(..., description="Target physical X coordinate")
    y: int = Field(..., description="Target physical Y coordinate")
    tolerance_px: int = Field(default=1, ge=0, description="Destination verification tolerance")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Optional movement duration")
    expected_generation: Optional[int] = Field(default=None, description="Optional desktop generation ID for consistency verification")


class ClickPointerPayload(BaseModel):
    x: Optional[int] = Field(default=None, description="Optional target physical X coordinate")
    y: Optional[int] = Field(default=None, description="Optional target physical Y coordinate")
    button: str = Field(default="left", description="Mouse button: left, right, middle")
    count: int = Field(default=1, ge=1, description="Number of consecutive clicks")
    dwell_ms: float = Field(default=50.0, ge=1.0, description="Click dwell delay in milliseconds")
    expected_generation: Optional[int] = Field(default=None, description="Optional desktop generation ID for consistency verification")


class PointerButtonPayload(BaseModel):
    button: str = Field(default="left", description="Mouse button: left, right, middle")


class PointerEmergencyReleasePayload(BaseModel):
    pass


class RecoverPointerLockoutPayload(BaseModel):
    recovery_token: str = Field(..., description="Unique administrative recovery token")


class TypeTextPayload(BaseModel):
    text: str = Field(..., min_length=1, description="Unicode text sequence to type")
    delay_ms: float = Field(default=2.0, ge=0.0, description="Inter-character delay in milliseconds")
    target_hwnd: Optional[int] = Field(default=None, description="Optional target window HWND to focus-verify")


class PressShortcutPayload(BaseModel):
    combination: str = Field(..., min_length=1, description="Shortcut combination e.g. 'ctrl+c'")
    target_hwnd: Optional[int] = Field(default=None, description="Optional target window HWND to focus-verify")


class KeyboardKeyPayload(BaseModel):
    key_code: str = Field(..., min_length=1, description="Key name or virtual key code e.g. 'enter', 'shift'")


class KeyboardEmergencyReleasePayload(BaseModel):
    pass


class RecoverKeyboardLockoutPayload(BaseModel):
    recovery_token: str = Field(..., min_length=1, description="Unique administrative recovery token")


class HeartbeatPayload(BaseModel):
    client_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Milestone M1.9 Step 5: Model Manager WebSocket Inbound Payloads
# =============================================================================


class ModelListPayload(BaseModel):
    """Inbound payload to list registered and discovered models."""
    provider: Optional[str] = Field(default=None, description="Optional provider filter (e.g. 'OLLAMA')")
    capability: Optional[str] = Field(default=None, description="Optional capability filter (e.g. 'TEXT_GENERATION')")
    include_all: bool = Field(default=True, description="Whether to include discovered, installed, and configured models")


class ModelStatusPayload(BaseModel):
    """Inbound payload to query overall model runtime status."""
    pass


class ModelActivePayload(BaseModel):
    """Inbound payload to query the currently active model context."""
    pass


class ModelDiscoverPayload(BaseModel):
    """Inbound payload to trigger a model discovery scan."""
    include_runtimes: bool = Field(default=True, description="Scan local provider runtimes like Ollama")
    include_cloud: bool = Field(default=True, description="Scan configured cloud providers")
    include_files: bool = Field(default=True, description="Scan local model weight files")


class ModelActivatePayload(BaseModel):
    """Inbound payload to activate a target AI model."""
    model_id: str = Field(..., min_length=1, description="Target model ID (e.g. 'ollama:qwen2.5:latest')")
    timeout_seconds: float = Field(default=30.0, gt=0.0, description="Activation timeout in seconds")
    preload_weights: bool = Field(default=True, description="Whether to preload model weights into memory")
    required_capabilities: Optional[list[str]] = Field(default=None, description="Optional list of required capabilities")
    policy: str = Field(default="REJECT_DURING_ACTIVE_TASK", description="Switching policy")


class ModelSwitchPayload(BaseModel):
    """Inbound payload to safely switch between AI models."""
    model_id: str = Field(..., min_length=1, description="Target model ID to switch to")
    policy: str = Field(default="REJECT_DURING_ACTIVE_TASK", description="Policy: REJECT_DURING_ACTIVE_TASK, CANCEL_AND_SWITCH, etc.")
    timeout_seconds: float = Field(default=30.0, gt=0.0, description="Switching timeout in seconds")
    preload_weights: bool = Field(default=True, description="Whether to preload model weights")
    required_capabilities: Optional[list[str]] = Field(default=None, description="Optional list of required capabilities")


class ModelHealthPayload(BaseModel):
    """Inbound payload to probe model health."""
    model_id: Optional[str] = Field(default=None, description="Optional target model ID, or active model if omitted")


class TaskHistoryListPayload(BaseModel):
    """Inbound payload to list historical execution records."""
    limit: int = Field(default=50, ge=1, le=500)
    status_filter: Optional[str] = Field(default=None, description="ALL, RUNNING, COMPLETED, FAILED, CANCELLED")
    search_query: Optional[str] = Field(default=None, description="Optional search term across goal, model, app")


class TaskHistoryDetailPayload(BaseModel):
    """Inbound payload to get full execution record detail."""
    execution_id: Optional[str] = Field(default=None)
    task_id: Optional[str] = Field(default=None)


class TaskHistoryClearPayload(BaseModel):
    """Inbound payload to clear execution history."""
    pass


class DiagnosticsRunPayload(BaseModel):
    """Inbound payload to trigger on-demand diagnostics run."""
    pass



