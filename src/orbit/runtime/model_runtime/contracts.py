"""Strongly-typed contracts and data models for ORBIT Model Runtime Engine (Milestone M1.9 Step 4).

Defines lifecycle status enums, runtime kinds, activation statuses, switch policies,
health diagnostics, active model contexts, request envelopes, and results.

SECURITY INVARIANT:
Credentials, API keys, and authorization headers are NEVER stored, serialized, or logged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator

from orbit.runtime.models.models import (
    CloudAuthStatus,
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelFileFormat,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)


class ModelRuntimeStatus(str, Enum):
    """Operational lifecycle state of a model runtime instance."""

    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    BUSY = "BUSY"
    SWITCHING = "SWITCHING"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class ModelRuntimeKind(str, Enum):
    """Runtime execution environment classification."""

    LOCAL = "LOCAL"
    REMOTE = "REMOTE"
    UNKNOWN = "UNKNOWN"


class ModelActivationStatus(str, Enum):
    """Detailed outcome classification for model activation and switching."""

    ACTIVATED = "ACTIVATED"
    ALREADY_ACTIVE = "ALREADY_ACTIVE"
    SWITCH_REJECTED = "SWITCH_REJECTED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INITIALIZATION_FAILED = "INITIALIZATION_FAILED"
    ACTIVE_TASK_CONFLICT = "ACTIVE_TASK_CONFLICT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ModelSwitchPolicy(str, Enum):
    """Policy governing model switching when an autonomous task may be running."""

    REJECT_DURING_ACTIVE_TASK = "REJECT_DURING_ACTIVE_TASK"  # Default: safely reject if task executing
    WAIT_FOR_SAFE_CHECKPOINT = "WAIT_FOR_SAFE_CHECKPOINT"    # Wait for safe pause/checkpoint before switching
    CANCEL_AND_SWITCH = "CANCEL_AND_SWITCH"                  # Cancel running task and switch immediately
    FORCE = "FORCE"                                          # Force switch regardless


class ModelRuntimeCapability(str, Enum):
    """Functional capabilities exposed by a model runtime."""

    TEXT_GENERATION = "TEXT_GENERATION"
    CHAT = "CHAT"
    VISION = "VISION"
    TOOL_CALLING = "TOOL_CALLING"
    REASONING = "REASONING"
    EMBEDDINGS = "EMBEDDINGS"
    CODE = "CODE"


class ModelRuntimeHealth(BaseModel):
    """Diagnostic health assessment of a model runtime."""

    model_id: str = Field(..., description="Unique model identifier")
    status: ModelRuntimeStatus = Field(default=ModelRuntimeStatus.READY, description="Runtime status")
    is_healthy: bool = Field(default=True, description="Whether runtime is operational and responsive")
    latency_ms: Optional[float] = Field(default=None, ge=0.0, description="Health check ping roundtrip latency in ms")
    checked_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of health evaluation",
    )
    diagnostic_message: Optional[str] = Field(default=None, description="Human-readable health or error message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider metrics without credentials")


class RuntimeInitializationResult(BaseModel):
    """Result of initializing a model runtime instance."""

    is_success: bool = Field(..., description="Whether initialization succeeded")
    model_id: str = Field(..., description="Model identifier")
    status: ModelRuntimeStatus = Field(..., description="Post-initialization runtime status")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Elapsed time in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Error message if initialization failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Safe runtime initialization details")


class ModelRuntimeInfo(BaseModel):
    """Metadata describing a runtime instance."""

    model_id: str = Field(..., description="Unique model identifier (e.g. 'ollama:qwen2.5:latest')")
    display_name: str = Field(default="", description="Display name for UI/logs")
    provider: ModelProviderKind = Field(..., description="Provider backend kind")
    runtime_kind: ModelRuntimeKind = Field(default=ModelRuntimeKind.LOCAL, description="LOCAL or REMOTE")
    status: ModelRuntimeStatus = Field(default=ModelRuntimeStatus.UNINITIALIZED, description="Current runtime status")
    capabilities: Set[ModelCapability] = Field(default_factory=set, description="Verified model capabilities")
    context_window: Optional[int] = Field(default=None, ge=0, description="Context window in tokens")
    parameter_size: Optional[str] = Field(default=None, description="Parameter scale (e.g. '7B')")
    quantization: Optional[str] = Field(default=None, description="Quantization (e.g. 'Q4_K_M')")
    endpoint: Optional[str] = Field(default=None, description="Provider endpoint (sanitized)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Safe metadata")


class ActiveModelContext(BaseModel):
    """Immutable snapshot of the currently active model context in ORBIT.
    
    Safe for exposure to WebSocket streaming, API endpoints, and UI frontend.
    Contains zero secrets or credentials.
    """

    model_id: str = Field(..., description="Unique identifier of active model")
    display_name: str = Field(default="", description="Human-readable model name")
    provider: ModelProviderKind = Field(..., description="Provider backend kind")
    runtime_kind: ModelRuntimeKind = Field(default=ModelRuntimeKind.LOCAL, description="LOCAL or REMOTE")
    runtime_status: ModelRuntimeStatus = Field(default=ModelRuntimeStatus.ACTIVE, description="Active status")
    health: ModelRuntimeHealth = Field(..., description="Latest health diagnostic")
    activated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when model was activated",
    )
    generation: int = Field(default=1, ge=1, description="Monotonic activation generation counter")
    capabilities: Set[ModelCapability] = Field(default_factory=set, description="Supported capabilities")
    context_window: Optional[int] = Field(default=None, ge=0, description="Context window size in tokens")
    endpoint: Optional[str] = Field(default=None, description="Sanitized provider endpoint")
    descriptor: Optional[ModelDescriptor] = Field(default=None, description="Full model descriptor")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Safe context metadata")


class ModelActivationRequest(BaseModel):
    """Request envelope to activate a model in ORBIT."""

    model_id: str = Field(..., description="Target model ID to activate")
    timeout_seconds: float = Field(default=60.0, gt=0.0, description="Timeout in seconds")
    preload_weights: bool = Field(default=True, description="Whether to preload weights/warmup")
    required_capabilities: Set[ModelCapability] = Field(
        default_factory=set,
        description="Capabilities that the model must satisfy",
    )
    policy: ModelSwitchPolicy = Field(
        default=ModelSwitchPolicy.REJECT_DURING_ACTIVE_TASK,
        description="Task conflict switching policy",
    )
    options: Dict[str, Any] = Field(default_factory=dict, description="Additional options")


class ModelActivationResult(BaseModel):
    """Outcome of an explicit model activation."""

    is_successful: bool = Field(..., description="Whether model was activated successfully")
    model_id: str = Field(..., description="Target model ID")
    status: ModelActivationStatus = Field(..., description="Activation status code")
    generation: int = Field(default=0, ge=0, description="Active generation counter")
    active_context: Optional[ActiveModelContext] = Field(default=None, description="Active context snapshot if active")
    failure_reason: Optional[str] = Field(default=None, description="Typed failure reason")
    diagnostic_message: Optional[str] = Field(default=None, description="Diagnostic error message")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Elapsed time in ms")


class ModelSwitchResult(BaseModel):
    """Outcome of a transactional model switch operation."""

    is_successful: bool = Field(..., description="Whether switch succeeded")
    previous_model_id: Optional[str] = Field(default=None, description="Model ID active before switch")
    active_model_id: Optional[str] = Field(default=None, description="Model ID active after switch attempt")
    generation: int = Field(default=0, ge=0, description="Active generation counter")
    switched: bool = Field(default=False, description="Whether model changed")
    status: ModelActivationStatus = Field(..., description="Switch outcome status code")
    active_context: Optional[ActiveModelContext] = Field(default=None, description="Active context after attempt")
    failure_reason: Optional[str] = Field(default=None, description="Typed failure code")
    diagnostic_message: Optional[str] = Field(default=None, description="Diagnostic error message")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Elapsed time in ms")


# =============================================================================
# Exception Hierarchy
# =============================================================================


class ModelRuntimeError(Exception):
    """Base exception for Model Runtime errors."""
    pass


class ModelNotFoundError(ModelRuntimeError):
    """Raised when a requested model ID is not found."""
    pass


class ModelUnavailableError(ModelRuntimeError):
    """Raised when a requested model is known but runtime is unreachable/offline."""
    pass


class ModelInitializationError(ModelRuntimeError):
    """Raised when runtime initialization or warmup fails."""
    pass


class ActiveTaskConflictError(ModelRuntimeError):
    """Raised when a switch is requested while an autonomous task is actively running."""
    pass


class StaleModelGenerationError(ModelRuntimeError):
    """Raised when an inference request specifies an out-of-date generation counter."""
    pass


class NoActiveModelError(ModelRuntimeError):
    """Raised when inference is dispatched but no AI model is active."""
    pass


class ModelSwitchRejectedError(ModelRuntimeError):
    """Raised when a switch request is rejected by policy or validation."""
    pass
