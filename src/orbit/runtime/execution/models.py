"""Domain models and contracts for ORBIT M1.6 Step 3 closed-loop execution."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.runtime.targeting.models import ResolvedTarget, TargetIntent
from orbit.runtime.verification.models import ActionVerificationResult, ExpectedOutcome, VerificationOutcome
from orbit.runtime.execution.context import DispatchStage, PreemptionRecord


class ExecutionState(str, Enum):
    """Explicit lifecycle states of the closed-loop execution engine."""

    IDLE = "IDLE"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    RESOLVING_TARGET = "RESOLVING_TARGET"
    VALIDATING = "VALIDATING"
    ACTING = "ACTING"
    DISPATCHING = "DISPATCHING"
    RE_OBSERVING = "RE_OBSERVING"
    VERIFYING = "VERIFYING"
    RETRY_PENDING = "RETRY_PENDING"
    REPLANNING = "REPLANNING"
    RECOVERING = "RECOVERING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"              # Terminal
    FAILED = "FAILED"                    # Terminal
    CANCELLED = "CANCELLED"              # Terminal
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"    # Terminal


class RecoveryReason(str, Enum):
    """Specific cause triggering a bounded recovery attempt."""

    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    GENERATION_MISMATCH = "GENERATION_MISMATCH"
    COORDINATE_INVALID = "COORDINATE_INVALID"
    TRANSIENT_TIMEOUT = "TRANSIENT_TIMEOUT"
    DISPATCH_FAILED = "DISPATCH_FAILED"


class ExecutionPolicy(BaseModel):
    """Conservative, explicit bounds governing closed-loop retries and recoveries."""

    max_total_attempts: int = Field(default=3, ge=1, le=10, description="Hard cap on total action dispatch attempts")
    max_target_resolution_attempts: int = Field(default=2, ge=1, le=5, description="Maximum attempts to locate target")
    max_verification_retries: int = Field(default=2, ge=0, le=5, description="Maximum re-tries upon verification failure")
    max_recovery_attempts: int = Field(default=2, ge=0, le=5, description="Maximum recovery cycles before failing closed")
    execution_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0, description="Total execution timeout in seconds")
    retry_backoff_base_ms: float = Field(default=10.0, ge=0.0, le=5000.0, description="Base backoff sleep in ms between retries")
    allow_inconclusive_as_success: bool = Field(default=False, description="Whether inconclusive verification may pass")


class ExecutionAttemptRecord(BaseModel):
    """Diagnostic audit record of a single cycle attempt in the closed loop."""

    attempt_index: int = Field(..., description="Zero-indexed attempt sequence number")
    state_at_start: ExecutionState = Field(..., description="Engine state when attempt began")
    target_id: Optional[str] = Field(default=None, description="Resolved target identifier if localized")
    dispatch_point: Optional[Tuple[int, int]] = Field(default=None, description="Physical coordinates dispatched")
    generation_id: int = Field(default=0, description="Desktop generation ID at action time")
    verification_outcome: Optional[VerificationOutcome] = Field(default=None, description="Result from ActionVerifier")
    failure_reason: Optional[str] = Field(default=None, description="Failure diagnostic if attempt failed")
    duration_ms: float = Field(default=0.0, description="Duration of this attempt in milliseconds")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClosedLoopExecutionResult(BaseModel):
    """Authoritative structured result of a closed-loop action execution."""

    final_state: ExecutionState = Field(..., description="Terminal state of the execution engine")
    is_success: bool = Field(..., description="Whether action was genuinely verified as successful")
    total_attempts: int = Field(default=0, ge=0, description="Total action dispatch attempts performed")
    total_recoveries: int = Field(default=0, ge=0, description="Total recovery cycles executed")
    total_verification_attempts: int = Field(default=0, ge=0, description="Total post-action verifications run")
    elapsed_duration_ms: float = Field(default=0.0, ge=0.0, description="Total elapsed duration in ms")
    attempts: List[ExecutionAttemptRecord] = Field(default_factory=list, description="Per-attempt diagnostic history")
    transition_history: List[Tuple[str, str, str, float]] = Field(
        default_factory=list,
        description="State machine history: (from_state, to_state, reason, timestamp_s)",
    )
    verification_result: Optional[ActionVerificationResult] = Field(default=None, description="Final ActionVerificationResult")
    resolved_target: Optional[ResolvedTarget] = Field(default=None, description="Final resolved target if any")
    failure_reason: Optional[str] = Field(default=None, description="Structured explanation if execution terminated in failure")
    failure_code: Optional[str] = Field(default=None, description="Standardized error code if failed")
    dispatch_stage: DispatchStage = Field(default=DispatchStage.NOT_DISPATCHED, description="Epistemic dispatch status of the action")
    preemption_record: Optional[PreemptionRecord] = Field(default=None, description="Forensic details if execution was preempted")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary telemetry and diagnostic details")

    @property
    def is_action_dispatched(self) -> bool:
        """Distinguish whether an action was dispatched vs whether it succeeded."""
        return self.total_attempts > 0
