"""Data contracts and strongly typed models for Dynamic Replanning and Plan Repair (M1.8 Step 4).

Safety Invariants:
1. Immutable audit records: All replan decisions, failure classifications, and history signatures are recorded with UTC timestamps.
2. Deterministic failure categorization: Failures are strictly classified into RECOVERABLE, TERMINAL, or INCONCLUSIVE with structured evidence.
3. Bounded budget enforcement: Strict caps on global and per-step replan cycles and backtracking depth.
4. Completed step preservation: Replan results explicitly declare which steps are preserved, modified, appended, or backtracked.
5. Fresh observation requirement: Target coordinates are never adjusted by guessing; generation parity is strictly enforced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from orbit.runtime.execution.context import PreemptionRecord
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanActionType, PlanStep


class FailureCategory(str, Enum):
    """Broad classification of step execution failures."""
    RECOVERABLE = "RECOVERABLE"
    TERMINAL = "TERMINAL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ReplanReason(str, Enum):
    """Specific cause that triggered a replan or recovery attempt."""
    # Strongly typed failure reasons (M1.8 Step 4 requirements)
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    STALE_GENERATION = "STALE_GENERATION"
    WINDOW_MOVED = "WINDOW_MOVED"
    WINDOW_RESIZED = "WINDOW_RESIZED"
    WINDOW_NOT_AVAILABLE = "WINDOW_NOT_AVAILABLE"
    APPLICATION_NOT_AVAILABLE = "APPLICATION_NOT_AVAILABLE"
    VISUAL_STATE_CHANGED = "VISUAL_STATE_CHANGED"
    OCR_STATE_CHANGED = "OCR_STATE_CHANGED"
    OCCLUDED = "OCCLUDED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    ACTION_FAILED = "ACTION_FAILED"
    PREDECESSOR_INVALIDATED = "PREDECESSOR_INVALIDATED"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    CANCELLED = "CANCELLED"
    UNSUPPORTED_RECOVERY = "UNSUPPORTED_RECOVERY"
    RECOVERY_BUDGET_EXHAUSTED = "RECOVERY_BUDGET_EXHAUSTED"

    # Additional contextual reasons / aliases
    WINDOW_NOT_FOCUSED = "WINDOW_NOT_FOCUSED"
    FOCUS_LOST = "FOCUS_LOST"
    GENERATION_MISMATCH = "GENERATION_MISMATCH"
    COORDINATE_OUT_OF_BOUNDS = "COORDINATE_OUT_OF_BOUNDS"
    ACTION_TIMEOUT = "ACTION_TIMEOUT"
    OPERATOR_CANCEL = "OPERATOR_CANCEL"
    WORKSPACE_COLLISION = "WORKSPACE_COLLISION"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    CYCLIC_LOOP_DETECTED = "CYCLIC_LOOP_DETECTED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"


class ReplanStatus(str, Enum):
    """Lifecycle status of a dynamic replan attempt."""
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    REPAIRING = "REPAIRING"
    RESUMED = "RESUMED"
    BACKTRACKED = "BACKTRACKED"
    EXHAUSTED = "EXHAUSTED"
    TERMINATED = "TERMINATED"
    LOOP_DETECTED = "LOOP_DETECTED"


class RecoveryStrategy(str, Enum):
    """Recommended strategy for repairing an execution plan or recovering state."""
    REFOCUS_APPLICATION = "REFOCUS_APPLICATION"
    REOPEN_APPLICATION = "REOPEN_APPLICATION"
    FALLBACK_PERCEPTION_STRATEGY = "FALLBACK_PERCEPTION_STRATEGY"
    RETRY_WITH_FRESH_OBSERVATION = "RETRY_WITH_FRESH_OBSERVATION"
    SPLICED_PRECURSOR_STEPS = "SPLICED_PRECURSOR_STEPS"
    BACKTRACK_TO_CHECKPOINT = "BACKTRACK_TO_CHECKPOINT"
    ABORT_FAIL_CLOSED = "ABORT_FAIL_CLOSED"


class FailureClassification(BaseModel):
    """Deterministic classification of a plan step execution failure with structured evidence."""
    category: FailureCategory
    reason: ReplanReason
    is_recoverable: bool
    diagnostic_message: str
    suggested_strategy: RecoveryStrategy
    failure_code: Optional[str] = None
    step_id: str
    action_type: PlanActionType
    raw_error: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionCheckpoint(BaseModel):
    """Represents the last verified valid execution state before or after a plan step."""
    checkpoint_id: str
    step_id: str
    step_index: int = 0
    completed_step_ids: List[str] = Field(default_factory=list)
    desktop_generation_id: Optional[int] = None
    window_identity: Optional[str] = None
    application_name: Optional[str] = None
    window_rect: Optional[Tuple[int, int, int, int]] = None  # (left, top, right, bottom)
    verified_state: Dict[str, Any] = Field(default_factory=dict)
    execution_evidence: Dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReplanBudget(BaseModel):
    """Bounded limits governing dynamic replanning and recovery."""
    max_global_replans: int = 3
    max_step_replans: int = 2
    max_target_resolution_attempts: int = 3
    max_backtracking_depth: int = 2
    max_step_retries: int = 2
    max_total_elapsed_ms: float = 30000.0  # 30 seconds max replan time
    allow_perceptual_fallbacks: bool = True
    allow_precursor_splicing: bool = True
    allow_backtracking: bool = True


# Alias for centralized recovery policy configuration
RecoveryPolicyConfig = ReplanBudget


class RecoveryDecision(BaseModel):
    """Deterministic decision emitted by the recovery policy engine."""
    decision: RecoveryStrategy
    is_terminal: bool
    reason: ReplanReason
    target_step_id: Optional[str] = None
    checkpoint: Optional[ExecutionCheckpoint] = None
    diagnostic_message: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FailureSignature(BaseModel):
    """Deterministic signature of a failure used to detect infinite cycles."""
    step_id: str
    action_type: PlanActionType
    reason: ReplanReason
    failure_code: Optional[str] = None
    target_identifier: Optional[str] = None
    desktop_generation_id: Optional[int] = None

    def signature_key(self) -> str:
        return f"{self.step_id}:{self.action_type.value}:{self.reason.value}:{self.failure_code}:{self.target_identifier}:{self.desktop_generation_id}"


class ReplanHistoryRecord(BaseModel):
    """Audit record capturing a single replan or repair event."""
    revision_id: int
    trigger_step_id: str
    classification: FailureClassification
    signature: FailureSignature
    repaired_plan_id: Optional[str] = None
    preserved_step_ids: List[str] = Field(default_factory=list)
    inserted_step_ids: List[str] = Field(default_factory=list)
    removed_step_ids: List[str] = Field(default_factory=list)
    backtracked_step_ids: List[str] = Field(default_factory=list)
    checkpoint_id: Optional[str] = None
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    elapsed_duration_ms: float = 0.0
    status: ReplanStatus = ReplanStatus.RESUMED
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlanRepairResult(BaseModel):
    """Result of a dynamic plan repair or backtracking operation."""
    is_success: bool
    repaired_plan: Optional[ExecutableTaskPlan] = None
    revision_id: int = 1
    replan_reason: ReplanReason = ReplanReason.UNKNOWN_ERROR
    preserved_step_ids: List[str] = Field(default_factory=list)
    inserted_steps: List[PlanStep] = Field(default_factory=list)
    removed_step_ids: List[str] = Field(default_factory=list)
    backtracked_step_ids: List[str] = Field(default_factory=list)
    checkpoint: Optional[ExecutionCheckpoint] = None
    failure_reason: Optional[str] = None
    failure_code: Optional[str] = None
    preemption_record: Optional[PreemptionRecord] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
