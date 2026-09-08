"""Dynamic Replanner and Runtime Recovery Orchestrator (M1.8 Step 4).

Coordinates failure classification, state validation, recovery policy decisions,
checkpoint management, backtracking, fresh observation capture, plan repair,
and structural DAG validation.

Safety Invariants:
1. Pure compilation & transformation: Zero direct synthetic mouse/keyboard events during repair.
2. Complete Progress Preservation: Succeeded steps are NEVER dropped or re-executed.
3. Fail-Closed on Preemption: Human takeover or operator cancellation aborts replanning immediately.
4. Bounded Recovery: Strict global and per-step replan budgets and backtracking limits prevent non-terminating loops.
5. Fresh Observation Grounding: Every recovery attempt is grounded in a freshly captured observation snapshot.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.cancellation import CancellationToken
from orbit.runtime.execution.context import CancellationReason, ExecutionContext, PreemptionRecord
from orbit.runtime.plan_execution.models import PlanStepExecutionResult
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanStep
from orbit.runtime.replanning.backtracking import BacktrackingEngine
from orbit.runtime.replanning.checkpoint_manager import ExecutionCheckpointManager
from orbit.runtime.replanning.failure_classifier import FailureClassifier
from orbit.runtime.replanning.history import ReplanHistoryTracker
from orbit.runtime.replanning.models import (
    ExecutionCheckpoint,
    FailureClassification,
    PlanRepairResult,
    RecoveryDecision,
    RecoveryPolicyConfig,
    RecoveryStrategy,
    ReplanBudget,
    ReplanHistoryRecord,
    ReplanReason,
    ReplanStatus,
)
from orbit.runtime.replanning.recovery_policy import RecoveryPolicyEngine
from orbit.runtime.replanning.repair import PlanRepairEngine
from orbit.runtime.replanning.state_validator import StateValidator
from orbit.runtime.replanning.validator import RepairedPlanValidator

logger = logging.getLogger(__name__)


class DynamicReplanner:
    """Coordinates failure analysis, state validation, policy decisions, checkpointing, repair, and backtracking.

    .. deprecated::
        Superseded in production by the unified AI-native `AgentExecutionLoop` and `ModelRouter`.
        Retained for backward compatibility, testing, and legacy failure classification.
    """

    def __init__(
        self,
        classifier: Optional[FailureClassifier] = None,
        state_validator: Optional[StateValidator] = None,
        recovery_policy: Optional[RecoveryPolicyEngine] = None,
        checkpoint_manager: Optional[ExecutionCheckpointManager] = None,
        backtracking_engine: Optional[BacktrackingEngine] = None,
        history_tracker: Optional[ReplanHistoryTracker] = None,
        repair_engine: Optional[PlanRepairEngine] = None,
        validator: Optional[RepairedPlanValidator] = None,
        observation: Optional[Any] = None,
        budget: Optional[ReplanBudget] = None,
    ) -> None:
        self._classifier = classifier or FailureClassifier()
        self._state_validator = state_validator or StateValidator()
        self._policy = recovery_policy or RecoveryPolicyEngine(config=budget)
        self._checkpoint_manager = checkpoint_manager or ExecutionCheckpointManager()
        self._backtracking = backtracking_engine or BacktrackingEngine(
            max_depth=budget.max_backtracking_depth if budget else 2
        )
        self._history = history_tracker or ReplanHistoryTracker(budget=budget)
        self._repair_engine = repair_engine or PlanRepairEngine()
        self._validator = validator or RepairedPlanValidator()
        self._observation = observation

    @property
    def classifier(self) -> FailureClassifier:
        return self._classifier

    # Alias for backwards compatibility
    @property
    def analyzer(self) -> FailureClassifier:
        return self._classifier

    @property
    def state_validator(self) -> StateValidator:
        return self._state_validator

    @property
    def recovery_policy(self) -> RecoveryPolicyEngine:
        return self._policy

    @property
    def checkpoint_manager(self) -> ExecutionCheckpointManager:
        return self._checkpoint_manager

    @property
    def backtracking(self) -> BacktrackingEngine:
        return self._backtracking

    @property
    def history(self) -> ReplanHistoryTracker:
        return self._history

    @property
    def repair_engine(self) -> PlanRepairEngine:
        return self._repair_engine

    @property
    def validator(self) -> RepairedPlanValidator:
        return self._validator

    @property
    def observation(self) -> Optional[Any]:
        return self._observation

    @property
    def total_replans(self) -> int:
        return self._history.total_replans

    @property
    def successful_replans(self) -> int:
        return self._history.successful_replans

    async def attempt_replan(
        self,
        failed_step: PlanStep,
        step_result: PlanStepExecutionResult,
        completed_step_ids: Set[str],
        current_plan: ExecutableTaskPlan,
        session_id: str,
        cancel_token: Optional[CancellationToken] = None,
        context: Optional[ExecutionContext] = None,
    ) -> PlanRepairResult:
        """Attempt to recover/repair the failing execution plan after a step failure."""
        step_id = failed_step.step_id

        # 1. Preemption & Operator Cancellation Check (Fail-Closed)
        if (cancel_token and cancel_token.is_cancelled) or (context and context.is_cancelled):
            reason_code = (
                context.cancellation_reason.value
                if context and context.cancellation_reason
                else "OPERATOR_CANCEL"
            )
            logger.warning("Replanning aborted due to active cancellation/preemption (%s)", reason_code)
            return PlanRepairResult(
                is_success=False,
                repaired_plan=None,
                revision_id=self._history.total_replans,
                replan_reason=ReplanReason.CANCELLED,
                failure_reason="Replanning cancelled or preempted by operator",
                failure_code=reason_code,
                preemption_record=context.last_preemption_record if context else None,
            )

        # 2. Deterministic Failure Classification
        classification = self._classifier.classify_failure(failed_step, step_result)
        logger.info(
            "Classified failure for step %s: category=%s, reason=%s, recoverable=%s, strategy=%s",
            step_id,
            classification.category.value,
            classification.reason.value,
            classification.is_recoverable,
            classification.suggested_strategy.value,
        )

        if not classification.is_recoverable:
            logger.warning("Failure for step %s is TERMINAL; aborting replan fail-closed", step_id)
            return PlanRepairResult(
                is_success=False,
                repaired_plan=None,
                revision_id=self._history.total_replans,
                replan_reason=classification.reason,
                failure_reason=f"Terminal failure ({classification.reason.value}): {classification.diagnostic_message}",
                failure_code=classification.failure_code or "TERMINAL_FAILURE",
                preemption_record=context.last_preemption_record if context else None,
            )

        # 3. Fresh Re-Observation Snapshot Capture (MANDATORY for recovery)
        fresh_snapshot: Optional[ObservationSnapshot] = None
        if self._observation and hasattr(self._observation, "capture_snapshot"):
            try:
                fresh_snapshot = await self._observation.capture_snapshot()
                logger.info(
                    "Captured fresh observation snapshot for recovery (generation=%s)",
                    fresh_snapshot.generation_id if fresh_snapshot else "N/A",
                )
            except Exception as ex:
                logger.warning("Failed to capture fresh observation snapshot during recovery: %s", ex)

        # 4. State Validation Against Live Observation
        latest_chk = self._checkpoint_manager.get_latest_checkpoint()
        state_val = self._state_validator.validate_step_state(
            step=failed_step,
            fresh_snapshot=fresh_snapshot,
            checkpoint=latest_chk,
            expected_generation_id=step_result.desktop_generation_id,
        )

        # If state validator found a specific issue (e.g. window moved/resized/disappeared), refine classification
        if not state_val.is_valid and state_val.detected_issue:
            classification.reason = state_val.detected_issue
            classification.diagnostic_message = f"{classification.diagnostic_message} | {state_val.diagnostic_message}"
            classification.evidence.update(state_val.evidence)

        # 5. Cycle / Infinite Loop Detection
        sig = self._history.create_signature(
            failed_step,
            classification,
            fresh_snapshot.generation_id if fresh_snapshot else step_result.desktop_generation_id,
        )
        if self._history.is_cyclic_loop(sig):
            logger.warning("Cyclic failure loop detected for signature: %s", sig.signature_key())
            self._history.record_replan(
                step=failed_step,
                classification=classification,
                status=ReplanStatus.LOOP_DETECTED,
                desktop_generation_id=fresh_snapshot.generation_id if fresh_snapshot else step_result.desktop_generation_id,
            )
            return PlanRepairResult(
                is_success=False,
                repaired_plan=None,
                revision_id=self._history.total_replans,
                replan_reason=ReplanReason.CYCLIC_LOOP_DETECTED,
                failure_reason=f"Cyclic failure loop detected for step '{step_id}' without forward progress",
                failure_code="CYCLIC_LOOP_DETECTED",
            )

        # 6. Centralized Recovery Policy Evaluation
        decision: RecoveryDecision = self._policy.decide_recovery(
            step=failed_step,
            classification=classification,
            history=self._history,
            checkpoint=latest_chk,
            state_validation=state_val,
            fresh_snapshot=fresh_snapshot,
        )

        if decision.is_terminal or decision.decision == RecoveryStrategy.ABORT_FAIL_CLOSED:
            logger.warning("Recovery decision is TERMINAL: %s", decision.diagnostic_message)
            self._history.record_replan(
                step=failed_step,
                classification=classification,
                status=ReplanStatus.EXHAUSTED if decision.reason == ReplanReason.RECOVERY_BUDGET_EXHAUSTED else ReplanStatus.TERMINATED,
                desktop_generation_id=fresh_snapshot.generation_id if fresh_snapshot else step_result.desktop_generation_id,
            )
            return PlanRepairResult(
                is_success=False,
                repaired_plan=None,
                revision_id=self._history.total_replans,
                replan_reason=decision.reason,
                failure_reason=decision.diagnostic_message,
                failure_code=decision.reason.value,
            )

        # 7. Apply Plan Repair or Backtracking Transformation
        next_revision = self._history.total_replans + 1

        if decision.decision == RecoveryStrategy.BACKTRACK_TO_CHECKPOINT and decision.checkpoint is not None:
            # Execute bounded backtracking
            repair_result = self._backtracking.backtrack_to_checkpoint(
                current_plan=current_plan,
                failed_step=failed_step,
                checkpoint=decision.checkpoint,
                completed_step_ids=completed_step_ids,
                classification=classification,
                fresh_snapshot=fresh_snapshot,
                revision_id=next_revision,
            )
        else:
            # Execute DAG splicing / perception rotation
            classification.suggested_strategy = decision.decision
            repair_result = self._repair_engine.repair_plan(
                current_plan=current_plan,
                failed_step=failed_step,
                completed_step_ids=completed_step_ids,
                classification=classification,
                fresh_snapshot=fresh_snapshot,
                revision_id=next_revision,
            )

        if not repair_result.is_success or repair_result.repaired_plan is None:
            logger.error("Plan transformation failed: %s", repair_result.failure_reason)
            return repair_result

        # 8. Validate Repaired Plan Structural Integrity
        val_result = self._validator.validate_repaired_plan(
            repaired_plan=repair_result.repaired_plan,
            completed_step_ids=set(repair_result.preserved_step_ids),
        )
        if not val_result.is_valid:
            logger.error("Repaired plan failed validation: %s", val_result.error_message)
            return PlanRepairResult(
                is_success=False,
                repaired_plan=None,
                revision_id=next_revision,
                replan_reason=classification.reason,
                failure_reason=f"Repaired plan validation failed: {val_result.error_message}",
                failure_code=val_result.error_code or "INVALID_REPAIRED_PLAN",
                diagnostics={"validation_diagnostics": val_result.diagnostics},
            )

        # 9. Record Successful Replan Event in Audit Trail
        status = ReplanStatus.BACKTRACKED if decision.decision == RecoveryStrategy.BACKTRACK_TO_CHECKPOINT else ReplanStatus.RESUMED
        self._history.record_replan(
            step=failed_step,
            classification=classification,
            repaired_plan_id=repair_result.repaired_plan.plan_id,
            preserved_step_ids=repair_result.preserved_step_ids,
            inserted_step_ids=[s.step_id for s in repair_result.inserted_steps],
            removed_step_ids=repair_result.removed_step_ids,
            desktop_generation_id=fresh_snapshot.generation_id if fresh_snapshot else step_result.desktop_generation_id,
            status=status,
            metadata=repair_result.diagnostics,
        )

        logger.info(
            "Successfully repaired plan %s -> %s (rev %d, +%d steps, status=%s)",
            current_plan.plan_id,
            repair_result.repaired_plan.plan_id,
            next_revision,
            len(repair_result.inserted_steps),
            status.value,
        )

        return repair_result
