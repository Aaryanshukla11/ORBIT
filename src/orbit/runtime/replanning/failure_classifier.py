"""Strongly typed Failure Classifier for runtime dynamic replanning (M1.8 Step 4).

Safety Invariants:
1. Zero silent failures: Every failure is classified into a strongly typed category with structured evidence.
2. Immediate Terminal Classification for Safety Breaches: Human takeover, user cancellation, workspace dock collisions,
   and prohibited/unsupported operations are strictly marked TERMINAL and fail closed.
3. Accurate Strategy Recommendation: Recoverable failures recommend the least-invasive valid repair strategy.
4. Structured Evidence Requirement: All classifications carry observable context (generation, codes, targets, diagnostics).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from orbit.runtime.execution import ClosedLoopExecutionResult, ExecutionState
from orbit.runtime.plan_execution.models import PlanStepExecutionResult, PlanStepExecutionStatus
from orbit.runtime.planning.models import PlanActionType, PlanStep
from orbit.runtime.replanning.models import (
    FailureCategory,
    FailureClassification,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.targeting.models import TargetResolutionStatus
from orbit.runtime.verification.models import VerificationOutcome

logger = logging.getLogger(__name__)


class FailureClassifier:
    """Deterministic classifier evaluating runtime step failures to decide recoverability."""

    def classify_failure(
        self,
        step: PlanStep,
        step_result: PlanStepExecutionResult,
    ) -> FailureClassification:
        """Classify a failed PlanStepExecutionResult into a strongly typed FailureClassification."""
        step_id = step.step_id
        action_type = step.action_type
        fail_code = step_result.failure_code or "UNKNOWN"
        fail_reason = step_result.failure_reason or "Unknown step execution failure"
        exec_res: Optional[ClosedLoopExecutionResult] = step_result.execution_result

        # Structured evidence dictionary
        evidence: Dict[str, Any] = {
            "step_id": step_id,
            "action_type": action_type.value,
            "failure_code": fail_code,
            "failure_reason": fail_reason,
            "step_status": step_result.status.value,
            "desktop_generation_id": step_result.desktop_generation_id,
            "is_dispatched": step_result.is_dispatched,
        }

        if step_result.resolved_target:
            coords = None
            if hasattr(step_result.resolved_target, "safe_point") and step_result.resolved_target.safe_point:
                coords = (step_result.resolved_target.safe_point.x, step_result.resolved_target.safe_point.y)
            elif hasattr(step_result.resolved_target, "point") and step_result.resolved_target.point:
                coords = (step_result.resolved_target.point.x, step_result.resolved_target.point.y)

            evidence["target"] = {
                "target_id": getattr(step_result.resolved_target, "target_id", None),
                "confidence": getattr(step_result.resolved_target, "confidence", 1.0),
                "coordinates": coords,
            }

        if step_result.verification_result:
            strat = getattr(step_result.verification_result, "strategy", None) or getattr(step_result.verification_result, "verifier_type", None) or getattr(step_result.verification_result, "strategy_used", None)
            v_reason = getattr(step_result.verification_result, "reason", None) or getattr(step_result.verification_result, "failure_reason", None)
            evidence["verification"] = {
                "outcome": step_result.verification_result.outcome.value,
                "confidence": step_result.verification_result.confidence,
                "strategy": strat.value if hasattr(strat, "value") else str(strat),
                "reason": v_reason,
            }

        # 1. Human Takeover Preemption Guard (TERMINAL)
        if (
            step_result.status == PlanStepExecutionStatus.CANCELLED
            and "takeover" in fail_reason.lower()
        ) or (exec_res and exec_res.final_state == ExecutionState.HUMAN_TAKEOVER) or fail_code == "HUMAN_TAKEOVER":
            return FailureClassification(
                category=FailureCategory.TERMINAL,
                reason=ReplanReason.HUMAN_TAKEOVER,
                is_recoverable=False,
                diagnostic_message="Human takeover active; execution immediately preempted fail-closed",
                suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
                failure_code="HUMAN_TAKEOVER",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 2. Operator Cancellation Guard (TERMINAL)
        if (
            step_result.status == PlanStepExecutionStatus.CANCELLED
            or (exec_res and exec_res.final_state == ExecutionState.CANCELLED)
            or fail_code in ("OPERATOR_CANCEL", "PLAN_CANCELLED", "CANCELLED")
        ):
            cancel_reason = ReplanReason.OPERATOR_CANCEL if fail_code == "OPERATOR_CANCEL" else ReplanReason.CANCELLED
            return FailureClassification(
                category=FailureCategory.TERMINAL,
                reason=cancel_reason,
                is_recoverable=False,
                diagnostic_message="Execution cancelled by operator; aborting plan fail-closed",
                suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
                failure_code="OPERATOR_CANCEL",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 3. Unsupported Action / Unsupported Recovery / Prohibited Constraints (TERMINAL)
        if (
            step_result.status == PlanStepExecutionStatus.UNSUPPORTED
            or action_type == PlanActionType.UNSUPPORTED_ACTION
            or "unsupported" in fail_code.lower()
            or "unsupported" in fail_reason.lower()
            or "prohibited" in fail_reason.lower()
        ):
            is_recovery_unsupported = "recovery" in fail_code.lower() or "recovery" in fail_reason.lower()
            reason = ReplanReason.UNSUPPORTED_RECOVERY if is_recovery_unsupported else ReplanReason.UNSUPPORTED_ACTION
            return FailureClassification(
                category=FailureCategory.TERMINAL,
                reason=reason,
                is_recoverable=False,
                diagnostic_message=f"Action or recovery '{action_type.value}' is unsupported or prohibited: {fail_reason}",
                suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
                failure_code="UNSUPPORTED_ACTION",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 4. Workspace Dock Boundary & Geometry Collisions (TERMINAL)
        if (
            "workspace" in fail_code.lower()
            or "dock" in fail_reason.lower()
            or "coordinate out of bounds" in fail_reason.lower()
            or "usable canvas" in fail_reason.lower()
        ):
            return FailureClassification(
                category=FailureCategory.TERMINAL,
                reason=ReplanReason.WORKSPACE_COLLISION,
                is_recoverable=False,
                diagnostic_message=f"Action rejected by workspace safety gate (boundary collision): {fail_reason}",
                suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
                failure_code="WORKSPACE_COLLISION",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 5. Recovery Budget / Loop Exhaustion (TERMINAL)
        if "budget_exhausted" in fail_code.lower() or "loop_detected" in fail_code.lower():
            return FailureClassification(
                category=FailureCategory.TERMINAL,
                reason=ReplanReason.RECOVERY_BUDGET_EXHAUSTED,
                is_recoverable=False,
                diagnostic_message=f"Recovery limit reached: {fail_reason}",
                suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
                failure_code="RECOVERY_BUDGET_EXHAUSTED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 6. Window / Application Not Available (RECOVERABLE)
        if (
            "window_not_available" in fail_code.lower()
            or "app_not_available" in fail_code.lower()
            or "application not open" in fail_reason.lower()
            or "window not found" in fail_reason.lower()
        ):
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=ReplanReason.APPLICATION_NOT_AVAILABLE,
                is_recoverable=True,
                diagnostic_message=f"Application window not available: {fail_reason}",
                suggested_strategy=RecoveryStrategy.REOPEN_APPLICATION,
                failure_code="APPLICATION_NOT_AVAILABLE",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 7. Window Geometry Changes (Moved / Resized / Focus Loss) (RECOVERABLE)
        if "window_moved" in fail_code.lower() or "window moved" in fail_reason.lower():
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=ReplanReason.WINDOW_MOVED,
                is_recoverable=True,
                diagnostic_message=f"Window moved during workflow: {fail_reason}",
                suggested_strategy=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
                failure_code="WINDOW_MOVED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        if "window_resized" in fail_code.lower() or "window resized" in fail_reason.lower():
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=ReplanReason.WINDOW_RESIZED,
                is_recoverable=True,
                diagnostic_message=f"Window resized during workflow: {fail_reason}",
                suggested_strategy=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
                failure_code="WINDOW_RESIZED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 8. Generation Invalidation & Stale Observation (RECOVERABLE)
        if (
            "stale" in fail_code.lower()
            or "generation" in fail_reason.lower()
            or "stale_observation" in fail_code.lower()
        ):
            stale_reason = ReplanReason.GENERATION_MISMATCH if fail_code in ("STALE_OBSERVATION", "GENERATION_MISMATCH") else ReplanReason.STALE_GENERATION
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=stale_reason,
                is_recoverable=True,
                diagnostic_message="Desktop generation shifted or observation snapshot TTL expired",
                suggested_strategy=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
                failure_code=fail_code if fail_code != "UNKNOWN" else "STALE_GENERATION",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 9. Target Occlusion / Blocking Dialogs (RECOVERABLE / INCONCLUSIVE)
        if "occluded" in fail_code.lower() or "blocked" in fail_reason.lower() or "popup" in fail_reason.lower():
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=ReplanReason.OCCLUDED,
                is_recoverable=True,
                diagnostic_message=f"Target control occluded or blocked: {fail_reason}",
                suggested_strategy=RecoveryStrategy.REFOCUS_APPLICATION,
                failure_code="OCCLUDED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 10. Visual / OCR Perception State Changes (RECOVERABLE)
        if "visual_state" in fail_code.lower() or "template" in fail_reason.lower():
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=ReplanReason.VISUAL_STATE_CHANGED,
                is_recoverable=True,
                diagnostic_message=f"Visual perception state changed: {fail_reason}",
                suggested_strategy=RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY,
                failure_code="VISUAL_STATE_CHANGED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        if "ocr_state" in fail_code.lower() or "ocr" in fail_reason.lower():
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=ReplanReason.OCR_STATE_CHANGED,
                is_recoverable=True,
                diagnostic_message=f"OCR anchor perception state changed: {fail_reason}",
                suggested_strategy=RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY,
                failure_code="OCR_STATE_CHANGED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 11. Target Localization Failures (RECOVERABLE)
        if "target" in fail_code.lower() or "not_found" in fail_code.lower() or "no accessible element" in fail_reason.lower():
            is_ambiguous = "ambiguous" in fail_reason.lower() or "ambiguous" in fail_code.lower()
            reason = ReplanReason.TARGET_AMBIGUOUS if is_ambiguous else ReplanReason.TARGET_NOT_FOUND
            strategy = (
                RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY
                if step.deferred_grounding and len(step.deferred_grounding.strategy_preferences) > 1
                else RecoveryStrategy.REFOCUS_APPLICATION
            )
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=reason,
                is_recoverable=True,
                diagnostic_message=f"Target localization failed ({reason.value}): {fail_reason}",
                suggested_strategy=strategy,
                failure_code=fail_code,
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 12. Action Verification Failures (RECOVERABLE)
        if (
            step_result.verification_result is not None
            and step_result.verification_result.outcome == VerificationOutcome.VERIFIED_FAILURE
        ) or "verification failed" in fail_reason.lower() or fail_code in ("VERIFICATION_FAILURE", "VERIFICATION_FAILED"):
            verif_reason = ReplanReason.VERIFICATION_FAILURE if fail_code == "VERIFICATION_FAILURE" else ReplanReason.VERIFICATION_FAILED
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=verif_reason,
                is_recoverable=True,
                diagnostic_message=f"Post-action verification failed: {fail_reason}",
                suggested_strategy=RecoveryStrategy.SPLICED_PRECURSOR_STEPS,
                failure_code=fail_code if fail_code != "UNKNOWN" else "VERIFICATION_FAILED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 13. Window Focus Loss / Inactive Application (RECOVERABLE)
        if (
            "not foreground" in fail_reason.lower()
            or "focus lost" in fail_reason.lower()
            or "not focused" in fail_reason.lower()
            or "foreground focus" in fail_reason.lower()
            or fail_code in ("WINDOW_NOT_FOCUSED", "FOCUS_LOST")
        ):
            return FailureClassification(
                category=FailureCategory.RECOVERABLE,
                reason=ReplanReason.WINDOW_NOT_FOCUSED,
                is_recoverable=True,
                diagnostic_message=f"Target window is not in foreground focus: {fail_reason}",
                suggested_strategy=RecoveryStrategy.REFOCUS_APPLICATION,
                failure_code="WINDOW_NOT_FOCUSED",
                step_id=step_id,
                action_type=action_type,
                raw_error=fail_reason,
                evidence=evidence,
            )

        # 14. Generic Recoverable Fallback
        return FailureClassification(
            category=FailureCategory.RECOVERABLE,
            reason=ReplanReason.ACTION_FAILED,
            is_recoverable=True,
            diagnostic_message=f"Action execution failed: {fail_reason}",
            suggested_strategy=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
            failure_code=fail_code,
            step_id=step_id,
            action_type=action_type,
            raw_error=fail_reason,
            evidence=evidence,
        )


# Backward compatibility alias
ExecutionFailureAnalyzer = FailureClassifier
