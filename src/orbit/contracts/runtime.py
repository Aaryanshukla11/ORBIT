"""Runtime domain models and execution contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.models.common import ErrorDetail


class SystemState(str, Enum):
    """Global operational state of the ORBIT runtime."""

    BOOTING = "BOOTING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    HUMAN_TAKEOVER_ACTIVE = "HUMAN_TAKEOVER_ACTIVE"
    UNRESOLVED_LOCKED = "UNRESOLVED_LOCKED"
    SHUTDOWN = "SHUTDOWN"


class TaskStatus(str, Enum):
    """Lifecycle state of an individual agent task."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class ActionTier(str, Enum):
    """Safety classification tier for agent actions."""

    TIER_1_SAFE = "TIER_1_SAFE"               # Read-only or benign actions (observation, workspace query)
    TIER_2_CONSTRAINED = "TIER_2_CONSTRAINED" # Normal UI interaction within declared boundaries
    TIER_3_HIGH_IMPACT = "TIER_3_HIGH_IMPACT" # High-risk actions requiring explicit operator confirmation


class ActionStage(str, Enum):
    """Execution progression stage of an individual action."""

    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    DISPATCHED = "DISPATCHED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class VerificationStatus(str, Enum):
    """Outcome of post-action visual/semantic verification."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SKIPPED = "SKIPPED"


class VerificationResult(BaseModel):
    """Result of validating action outcome against expectations."""

    status: VerificationStatus = Field(..., description="Outcome of verification")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Diagnostic verification payload")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Action(BaseModel):
    """Individual atomic or sub-atomic operation dispatched by the runtime."""

    action_id: str = Field(..., description="Unique action identifier")
    task_id: str = Field(..., description="Parent task identifier")
    action_type: str = Field(..., description="Type identifier e.g. pointer_click, type_text, observe")
    tier: ActionTier = Field(default=ActionTier.TIER_1_SAFE, description="Safety classification")
    stage: ActionStage = Field(default=ActionStage.PENDING, description="Current action stage")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameter payload")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dispatched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    verification: Optional[VerificationResult] = None
    error: Optional[ErrorDetail] = None


class Step(BaseModel):
    """A logical milestone step within a multi-action execution plan."""

    step_id: str = Field(..., description="Unique step identifier")
    step_index: int = Field(..., ge=0, description="Zero-indexed sequence number")
    description: str = Field(..., description="Human-readable step objective")
    actions: List[Action] = Field(default_factory=list, description="Ordered list of actions in step")
    status: TaskStatus = Field(default=TaskStatus.CREATED, description="Step status")


class ExecutionPlan(BaseModel):
    """Sequence of planned steps to fulfill a user task."""

    plan_id: str = Field(..., description="Unique plan identifier")
    task_id: str = Field(..., description="Associated task identifier")
    description: str = Field(..., description="High-level plan summary")
    steps: List[Step] = Field(default_factory=list, description="Ordered execution steps")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Task(BaseModel):
    """User-submitted task record and tracking state."""

    task_id: str = Field(..., description="Unique task identifier")
    session_id: str = Field(..., description="Originating session identifier")
    prompt: str = Field(..., description="User prompt or task instruction")
    status: TaskStatus = Field(default=TaskStatus.CREATED, description="Current task lifecycle status")
    plan: Optional[ExecutionPlan] = Field(default=None, description="Active execution plan if generated")
    current_step_index: int = Field(default=0, description="Index of currently active step")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[ErrorDetail] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary task context metadata")
