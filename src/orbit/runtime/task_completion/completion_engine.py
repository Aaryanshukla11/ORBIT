"""End-to-end Autonomous Task Completion Engine for ORBIT (M1.8 Step 5).

Coordinates the complete operational capability chain:
NATURAL LANGUAGE GOAL
        ↓
TASK UNDERSTANDING
        ↓
DEPENDENCY-AWARE DAG TASK PLANNING
        ↓
PLAN EXECUTION (Closed-Loop with Dynamic Replanning & Backtracking)
        ↓
PRE & POST OBSERVATION CAPTURE
        ↓
INDEPENDENT GOAL COMPLETION VERIFICATION
        ↓
STRUCTURED AUDIT RESULT
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from PIL import Image

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.contracts.capabilities import FrameData, ObservationCapability
from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.execution import ExecutionPolicy
from orbit.runtime.execution.context import ExecutionContext
from orbit.runtime.perception import SemanticPerceptionEngine
from orbit.runtime.plan_execution import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanExecutor,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning import ExecutableTaskPlan, TaskPlanningEngine
from orbit.runtime.task_completion.evidence import CompletionEvidenceCollector
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
    TaskExecutionResult,
)
from orbit.runtime.task_understanding import TaskUnderstandingEngine, TaskUnderstandingResult, TaskUnderstandingStatus

logger = logging.getLogger(__name__)


class TaskCompletionEngine:
    """Core coordinator executing autonomous desktop tasks from natural language goals."""

    def __init__(
        self,
        plan_executor: PlanExecutor,
        observation: Optional[ObservationCapability] = None,
        task_understanding_engine: Optional[TaskUnderstandingEngine] = None,
        task_planning_engine: Optional[TaskPlanningEngine] = None,
        perception_engine: Optional[SemanticPerceptionEngine] = None,
        goal_verifier: Optional[GoalVerifier] = None,
        evidence_collector: Optional[CompletionEvidenceCollector] = None,
    ) -> None:
        self._plan_executor = plan_executor
        self._obs = observation
        self._task_understanding = task_understanding_engine or TaskUnderstandingEngine()
        self._task_planning = task_planning_engine or TaskPlanningEngine(understanding_engine=self._task_understanding)
        self._perception_engine = perception_engine or SemanticPerceptionEngine()
        self._evidence_collector = evidence_collector or CompletionEvidenceCollector()
        self._goal_verifier = goal_verifier or GoalVerifier(
            perception_engine=self._perception_engine,
            evidence_collector=self._evidence_collector,
        )

    @property
    def plan_executor(self) -> PlanExecutor:
        return self._plan_executor

    @property
    def observation(self) -> Optional[ObservationCapability]:
        return self._obs or getattr(self._plan_executor.execution_engine, "observation", None)

    @property
    def goal_verifier(self) -> GoalVerifier:
        return self._goal_verifier

    @property
    def task_understanding_engine(self) -> TaskUnderstandingEngine:
        return self._task_understanding

    @property
    def task_planning_engine(self) -> TaskPlanningEngine:
        return self._task_planning

    async def execute_task(
        self,
        goal: str,
        session_id: str = "default_session",
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        policy: Optional[ExecutionPolicy] = None,
        cancel_token: Optional[CancellationToken] = None,
        exec_context: Optional[ExecutionContext] = None,
    ) -> TaskExecutionResult:
        """Execute a natural-language task goal end-to-end with independent goal verification."""
        t_start = time.perf_counter()
        start_utc = datetime.now(timezone.utc)
        effective_task_id = task_id or f"task_{uuid4().hex[:8]}"

        logger.info("TaskCompletionEngine starting task %s: '%s'", effective_task_id, goal)

        # 0. Capture initial pre-execution observation & frame (for visual diffs / state comparison)
        pre_snapshot: Optional[ObservationSnapshot] = None
        pre_image: Optional[Image.Image] = None
        obs_cap = self.observation
        if obs_cap is not None:
            try:
                if hasattr(obs_cap, "capture_snapshot"):
                    pre_snapshot = await obs_cap.capture_snapshot()
                if hasattr(obs_cap, "capture_screen"):
                    frame: FrameData = await obs_cap.capture_screen(display_index=0)
                    if frame and frame.raw_bytes:
                        pre_image = Image.open(io.BytesIO(frame.raw_bytes))
            except Exception as ex:
                logger.debug("Initial pre-execution observation capture notice: %s", ex)

        # 1. Phase 1: Task Understanding
        understanding: TaskUnderstandingResult = self._task_understanding.understand(
            request=goal,
            metadata=context or {},
        )

        if understanding.status in {TaskUnderstandingStatus.INVALID, TaskUnderstandingStatus.FAILED}:
            err_msg = (
                "; ".join(understanding.diagnostic_messages)
                if understanding.diagnostic_messages
                else "Task understanding failed to parse valid intent"
            )
            evidence = self._evidence_collector.build_evidence(
                snapshot=pre_snapshot,
                diagnostics={"understanding_status": understanding.status.value, "error": err_msg},
            )
            verif_res = GoalVerificationResult(
                status=TaskCompletionStatus.FAILED,
                is_completed=False,
                failure_reason=err_msg,
                failure_code="TASK_UNDERSTANDING_FAILED",
                evidence=evidence,
            )
            return self._build_result(
                task_id=effective_task_id,
                session_id=session_id,
                goal=goal,
                understanding=understanding,
                plan=None,
                plan_result=None,
                verification_result=verif_res,
                start_utc=start_utc,
                t_start=t_start,
            )

        if understanding.status == TaskUnderstandingStatus.UNSUPPORTED:
            err_msg = (
                "; ".join(understanding.diagnostic_messages)
                if understanding.diagnostic_messages
                else "Task goal is unsupported"
            )
            evidence = self._evidence_collector.build_evidence(
                snapshot=pre_snapshot,
                diagnostics={"understanding_status": understanding.status.value, "error": err_msg},
            )
            verif_res = GoalVerificationResult(
                status=TaskCompletionStatus.UNSUPPORTED,
                is_completed=False,
                failure_reason=err_msg,
                failure_code="UNSUPPORTED_TASK",
                evidence=evidence,
            )
            return self._build_result(
                task_id=effective_task_id,
                session_id=session_id,
                goal=goal,
                understanding=understanding,
                plan=None,
                plan_result=None,
                verification_result=verif_res,
                start_utc=start_utc,
                t_start=t_start,
            )

        # 2. Phase 2: Task Planning
        plan: ExecutableTaskPlan = self._task_planning.plan_task(
            understanding=understanding,
            task_id=effective_task_id,
        )

        if not plan.is_valid or plan.status.value in {"UNSUPPORTED", "INVALID", "FAILED"}:
            err_msg = (
                "; ".join(plan.unresolved_items)
                if plan.unresolved_items
                else f"Task planning failed with status {plan.status.value}"
            )
            status = TaskCompletionStatus.UNSUPPORTED if plan.status.value == "UNSUPPORTED" else TaskCompletionStatus.FAILED
            evidence = self._evidence_collector.build_evidence(
                snapshot=pre_snapshot,
                diagnostics={"plan_status": plan.status.value, "error": err_msg},
            )
            verif_res = GoalVerificationResult(
                status=status,
                is_completed=False,
                failure_reason=err_msg,
                failure_code=f"PLANNING_{plan.status.value}",
                evidence=evidence,
            )
            return self._build_result(
                task_id=effective_task_id,
                session_id=session_id,
                goal=goal,
                understanding=understanding,
                plan=plan,
                plan_result=None,
                verification_result=verif_res,
                start_utc=start_utc,
                t_start=t_start,
            )

        # 3. Phase 3: Plan Execution (Closed Loop with dynamic replanning & recovery)
        plan_result: PlanExecutionResult = await self._plan_executor.execute_plan(
            plan=plan,
            session_id=session_id,
            task_id=effective_task_id,
            policy=policy,
            cancel_token=cancel_token,
            context=exec_context,
        )

        # 4. Phase 4: Capture Fresh Post-Execution Observation
        post_snapshot: Optional[ObservationSnapshot] = None
        post_image: Optional[Image.Image] = None
        if obs_cap is not None:
            try:
                if hasattr(obs_cap, "capture_snapshot"):
                    post_snapshot = await obs_cap.capture_snapshot()
                if hasattr(obs_cap, "capture_screen"):
                    frame = await obs_cap.capture_screen(display_index=0)
                    if frame and frame.raw_bytes:
                        post_image = Image.open(io.BytesIO(frame.raw_bytes))
            except Exception as ex:
                logger.error("Post-execution observation capture failed: %s", ex)

        # Fallback to last step verification snapshot if direct capture is unavailable
        if post_snapshot is None and plan_result.step_results:
            last_res = plan_result.step_results[-1]
            if last_res.execution_result and last_res.execution_result.verification_result:
                # If execution result has snapshot
                pass

        # 5. Phase 5: Independent Final Goal Verification
        verification_result: GoalVerificationResult = await self._goal_verifier.verify_goal(
            understanding=understanding,
            plan=plan,
            plan_result=plan_result,
            post_snapshot=post_snapshot,
            post_image=post_image,
            pre_snapshot=pre_snapshot,
            pre_image=pre_image,
            session_id=session_id,
        )

        # 6. Phase 6: Compile Structured Result
        return self._build_result(
            task_id=effective_task_id,
            session_id=session_id,
            goal=goal,
            understanding=understanding,
            plan=plan,
            plan_result=plan_result,
            verification_result=verification_result,
            start_utc=start_utc,
            t_start=t_start,
        )

    def _build_result(
        self,
        task_id: str,
        session_id: str,
        goal: str,
        understanding: Optional[TaskUnderstandingResult],
        plan: Optional[ExecutableTaskPlan],
        plan_result: Optional[PlanExecutionResult],
        verification_result: GoalVerificationResult,
        start_utc: datetime,
        t_start: float,
    ) -> TaskExecutionResult:
        """Build a comprehensive TaskExecutionResult."""
        t_end = time.perf_counter()
        end_utc = datetime.now(timezone.utc)
        elapsed_ms = (t_end - t_start) * 1000.0

        completed_steps: List[str] = []
        failed_steps: List[str] = []
        recovery_attempts = 0
        replan_history: List[Dict[str, Any]] = []

        if plan_result is not None:
            completed_steps = [
                s.step_id for s in plan_result.step_results
                if s.status == PlanStepExecutionStatus.SUCCEEDED
            ]
            failed_steps = [
                s.step_id for s in plan_result.step_results
                if s.status == PlanStepExecutionStatus.FAILED
            ]
            recovery_attempts = plan_result.diagnostics.get("total_replans", 0)
            replan_history = plan_result.diagnostics.get("replan_history", [])

        is_success = verification_result.status == TaskCompletionStatus.COMPLETED

        return TaskExecutionResult(
            task_id=task_id,
            session_id=session_id,
            goal=goal,
            understanding=understanding,
            plan=plan,
            plan_execution_result=plan_result,
            goal_verification_result=verification_result,
            completion_status=verification_result.status,
            is_success=is_success,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            recovery_attempts=recovery_attempts,
            replan_history=replan_history,
            evidence=verification_result.evidence,
            failure_reason=verification_result.failure_reason,
            failure_code=verification_result.failure_code,
            start_time_utc=start_utc,
            end_time_utc=end_utc,
            elapsed_duration_ms=elapsed_ms,
            diagnostics={
                "is_goal_completed": is_success,
                "verification_diagnostics": verification_result.diagnostics,
                "plan_diagnostics": plan_result.diagnostics if plan_result else {},
            },
        )
