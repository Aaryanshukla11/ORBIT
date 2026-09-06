"""Data contracts and models for ORBIT Plan Execution Subsystem (M1.8 Step 3).

Establishes strongly-typed execution state, compiled runtime actions, step execution
records, and aggregate plan execution results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.execution.context import CancellationReason, DispatchStage, ExecutionContext, PreemptionRecord
from orbit.runtime.execution.models import ClosedLoopExecutionResult
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanActionType, PlanStep
from orbit.runtime.targeting.models import ResolvedTarget, TargetIntent
from orbit.runtime.verification.models import ActionVerificationResult, ExpectedOutcome


class PlanExecutionStatus(str, Enum):
    """Aggregate lifecycle status of an executable plan."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"


class PlanStepExecutionStatus(str, Enum):
    """Discrete execution status of an individual PlanStep."""

    PENDING = "PENDING"          # Initial state, waiting for predecessors
    READY = "READY"              # Predecessors succeeded, eligible for execution
    RUNNING = "RUNNING"          # Currently executing in closed loop
    SUCCEEDED = "SUCCEEDED"      # Successfully executed and verified
    FAILED = "FAILED"            # Executed or grounded, but failed verification or closed-loop error
    BLOCKED = "BLOCKED"          # Predecessor failed or was skipped; blocked from executing
    SKIPPED = "SKIPPED"          # Intentionally bypassed by plan policy
    CANCELLED = "CANCELLED"      # Aborted due to user cancellation or human takeover
    UNSUPPORTED = "UNSUPPORTED"  # Step action cannot be compiled to supported runtime primitives


class CompiledRuntimeAction(BaseModel):
    """Concrete runtime execution intent compiled from an abstract PlanStep.

    SAFETY INVARIANT:
    CompiledRuntimeAction declares semantic targeting (TargetIntent) and action parameters
    (e.g., text, shortcut keys). It MUST NEVER contain pre-baked physical screen coordinates.
    All coordinates are resolved dynamically at runtime by ClosedLoopExecutionEngine.
    """

    step_id: str = Field(..., description="Source PlanStep identifier")
    action_type: str = Field(..., description="Concrete engine action type (e.g. pointer_click, type_text, shortcut, observe)")
    target_intent: Optional[TargetIntent] = Field(default=None, description="Perception and targeting intent for runtime grounding")
    action_parameters: Dict[str, Any] = Field(default_factory=dict, description="Action-specific arguments (e.g. text, button, count)")
    expected_outcome: Optional[ExpectedOutcome] = Field(default=None, description="Post-action state delta expectation for verification")
    is_supported: bool = Field(default=True, description="Whether this action is supported by available runtime capabilities")
    rejection_reason: Optional[str] = Field(default=None, description="Diagnostic explanation if step cannot be compiled")
    requires_fresh_observation: bool = Field(default=True, description="Whether execution must capture a fresh frame")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic and traceability metadata")


class PlanStepExecutionResult(BaseModel):
    """Forensic audit record of an individual PlanStep execution."""

    step_id: str = Field(..., description="PlanStep identifier")
    step_index: int = Field(..., description="Topological sequence index")
    action_type: PlanActionType = Field(..., description="Abstract plan action objective")
    status: PlanStepExecutionStatus = Field(..., description="Terminal execution status of this step")
    compiled_action: Optional[CompiledRuntimeAction] = Field(default=None, description="Compiled runtime action if compiled")
    execution_result: Optional[ClosedLoopExecutionResult] = Field(default=None, description="ClosedLoopExecutionEngine structured result")
    verification_result: Optional[ActionVerificationResult] = Field(default=None, description="Post-action verification result")
    resolved_target: Optional[ResolvedTarget] = Field(default=None, description="Resolved target from live observation")
    failure_reason: Optional[str] = Field(default=None, description="Diagnostic failure message if step failed")
    failure_code: Optional[str] = Field(default=None, description="Standardized error code if step failed")
    desktop_generation_id: Optional[int] = Field(default=None, description="Desktop generation evaluated during step execution")
    is_dispatched: bool = Field(default=False, description="Whether physical OS input was actually dispatched to hardware")
    start_time_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Step execution start timestamp")
    end_time_utc: Optional[datetime] = Field(default=None, description="Step execution end timestamp")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Step duration in milliseconds")
    dependencies: List[str] = Field(default_factory=list, description="Predecessor step IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Telemetry and diagnostic details")


class PlanExecutionResult(BaseModel):
    """Authoritative structured result of a multi-step plan execution."""

    plan_id: str = Field(..., description="ExecutableTaskPlan identifier")
    task_id: str = Field(..., description="Associated high-level task identifier")
    final_status: PlanExecutionStatus = Field(..., description="Terminal status of plan execution")
    is_success: bool = Field(..., description="Whether all required plan steps succeeded")
    total_steps: int = Field(default=0, ge=0, description="Total steps in the plan")
    completed_steps: int = Field(default=0, ge=0, description="Number of successfully executed steps")
    failed_steps: int = Field(default=0, ge=0, description="Number of failed steps")
    blocked_steps: int = Field(default=0, ge=0, description="Number of blocked steps due to predecessor failures")
    skipped_steps: int = Field(default=0, ge=0, description="Number of skipped steps")
    step_results: List[PlanStepExecutionResult] = Field(default_factory=list, description="Ordered step execution records")
    start_time_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Plan execution start timestamp")
    end_time_utc: Optional[datetime] = Field(default=None, description="Plan execution end timestamp")
    elapsed_duration_ms: float = Field(default=0.0, ge=0.0, description="Total elapsed plan duration in milliseconds")
    failure_reason: Optional[str] = Field(default=None, description="Plan-level failure explanation if failed")
    failure_code: Optional[str] = Field(default=None, description="Standardized plan-level failure code")
    preemption_record: Optional[PreemptionRecord] = Field(default=None, description="Forensic preemption details if cancelled or takeover")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Aggregate diagnostics and telemetry")

    @property
    def total_dispatches(self) -> int:
        """Count total physical OS input dispatches across all steps."""
        return sum(1 for r in self.step_results if r.is_dispatched)


class PlanExecutionContext:
    """Execution context binding an active plan execution to cancellation, takeover, and session."""

    def __init__(
        self,
        plan: ExecutableTaskPlan,
        session_id: str,
        task_id: Optional[str] = None,
        parent_token: Optional[CancellationToken] = None,
        takeover_checker: Optional[Any] = None,
    ) -> None:
        self.plan = plan
        self.session_id = session_id
        self.task_id = task_id or plan.task_id
        self.raw_context = ExecutionContext(
            execution_id=self.task_id,
            parent_token=parent_token,
            takeover_checker=takeover_checker,
        )
        self.step_states: Dict[str, PlanStepExecutionStatus] = {
            step.step_id: PlanStepExecutionStatus.PENDING for step in plan.steps
        }
        self.step_results: Dict[str, PlanStepExecutionResult] = {}
        self._start_time = time.perf_counter()

    @property
    def is_cancelled(self) -> bool:
        return self.raw_context.is_cancelled

    @property
    def token(self) -> CancellationToken:
        return self.raw_context.token

    async def is_takeover_active(self) -> bool:
        return await self.raw_context.is_takeover_active()

    def mark_step_status(self, step_id: str, status: PlanStepExecutionStatus) -> None:
        self.step_states[step_id] = status

    def get_step_status(self, step_id: str) -> PlanStepExecutionStatus:
        return self.step_states.get(step_id, PlanStepExecutionStatus.PENDING)

    def record_step_result(self, result: PlanStepExecutionResult) -> None:
        self.step_results[result.step_id] = result
        self.step_states[result.step_id] = result.status
