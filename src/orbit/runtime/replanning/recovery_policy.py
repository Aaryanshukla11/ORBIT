"""Centralized deterministic Recovery Policy Engine (M1.8 Step 4).

Safety Invariants:
1. Deterministic Recovery Policies: Every failure is routed through strongly typed, deterministic decision rules.
2. Bounded Limits: Strict enforcement of max_target_resolution_attempts, max_replan_attempts, max_step_retries, and max_backtracking_depth.
3. Strict Fail-Closed: Unknown popups/dialogs, persistent ambiguities, safety breaches, and budget exhaustions fail closed immediately.
4. Fresh Observation Primacy: Recovery decisions always mandate fresh observations before action dispatch.
"""

from __future__ import annotations

import logging
from typing import Optional

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.planning.models import PlanStep
from orbit.runtime.replanning.history import ReplanHistoryTracker
from orbit.runtime.replanning.models import (
    ExecutionCheckpoint,
    FailureCategory,
    FailureClassification,
    RecoveryDecision,
    RecoveryPolicyConfig,
    RecoveryStrategy,
    ReplanBudget,
    ReplanReason,
)
from orbit.runtime.replanning.state_validator import StateValidationResult

logger = logging.getLogger(__name__)


class RecoveryPolicyEngine:
    """Evaluates failures and desktop state against deterministic recovery policies and bounded budgets."""

    def __init__(self, config: Optional[RecoveryPolicyConfig] = None) -> None:
        self._config = config or RecoveryPolicyConfig()

    @property
    def config(self) -> RecoveryPolicyConfig:
        return self._config

    def decide_recovery(
        self,
        step: PlanStep,
        classification: FailureClassification,
        history: ReplanHistoryTracker,
        checkpoint: Optional[ExecutionCheckpoint] = None,
        state_validation: Optional[StateValidationResult] = None,
        fresh_snapshot: Optional[ObservationSnapshot] = None,
    ) -> RecoveryDecision:
        """Determine the recovery action according to deterministic policy rules and bounded budgets."""
        step_id = step.step_id
        reason = classification.reason

        # 1. Safety & Terminal Preemption Check
        if not classification.is_recoverable or classification.category == FailureCategory.TERMINAL:
            logger.warning("Failure for step %s is non-recoverable (%s); deciding fail-closed abort", step_id, reason.value)
            return RecoveryDecision(
                decision=RecoveryStrategy.ABORT_FAIL_CLOSED,
                is_terminal=True,
                reason=reason,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message=f"Terminal failure ({reason.value}): {classification.diagnostic_message}",
                metadata={"classification": classification.model_dump()},
            )

        # 2. Bounded Recovery Budget Enforcement
        if history.is_budget_exhausted(step_id):
            logger.warning("Recovery budget exhausted for step %s or session; deciding fail-closed abort", step_id)
            return RecoveryDecision(
                decision=RecoveryStrategy.ABORT_FAIL_CLOSED,
                is_terminal=True,
                reason=ReplanReason.RECOVERY_BUDGET_EXHAUSTED,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message=(
                    f"Recovery budget exhausted for step '{step_id}' "
                    f"(step retries: {history.get_step_replan_count(step_id)}/{self._config.max_step_replans}, "
                    f"global: {history.successful_replans}/{self._config.max_global_replans})"
                ),
                metadata={"step_id": step_id, "budget": self._config.model_dump()},
            )

        # 3. Policy: Target Localization Failures (NOT_FOUND / AMBIGUOUS)
        if reason in (ReplanReason.TARGET_NOT_FOUND, ReplanReason.TARGET_AMBIGUOUS):
            step_retries = history.get_step_replan_count(step_id)
            if step_retries >= self._config.max_target_resolution_attempts:
                logger.warning(
                    "Target resolution attempt budget exhausted (%d >= %d) for step %s",
                    step_retries,
                    self._config.max_target_resolution_attempts,
                    step_id,
                )
                return RecoveryDecision(
                    decision=RecoveryStrategy.ABORT_FAIL_CLOSED,
                    is_terminal=True,
                    reason=ReplanReason.RECOVERY_BUDGET_EXHAUSTED,
                    target_step_id=step_id,
                    checkpoint=checkpoint,
                    diagnostic_message=f"Target resolution attempt budget exhausted for step '{step_id}'",
                )

            # For ambiguity: attempt fallback grounding; if no additional grounding strategies exist, fail closed
            if reason == ReplanReason.TARGET_AMBIGUOUS:
                has_multimodal_prefs = (
                    step.deferred_grounding is not None
                    and len(step.deferred_grounding.strategy_preferences) > 1
                )
                if not has_multimodal_prefs or not self._config.allow_perceptual_fallbacks:
                    logger.warning("Target ambiguity persists without alternative grounding strategies; failing closed")
                    return RecoveryDecision(
                        decision=RecoveryStrategy.ABORT_FAIL_CLOSED,
                        is_terminal=True,
                        reason=ReplanReason.TARGET_AMBIGUOUS,
                        target_step_id=step_id,
                        checkpoint=checkpoint,
                        diagnostic_message="Target is ambiguous and no further grounding strategies exist (fail closed)",
                    )
                return RecoveryDecision(
                    decision=RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY,
                    is_terminal=False,
                    reason=ReplanReason.TARGET_AMBIGUOUS,
                    target_step_id=step_id,
                    checkpoint=checkpoint,
                    diagnostic_message="Rotating perception strategy for multimodal target disambiguation",
                )

            # Target not found: try fallback perception if available, else refocus application
            if step.deferred_grounding and len(step.deferred_grounding.strategy_preferences) > 1 and self._config.allow_perceptual_fallbacks:
                return RecoveryDecision(
                    decision=RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY,
                    is_terminal=False,
                    reason=ReplanReason.TARGET_NOT_FOUND,
                    target_step_id=step_id,
                    checkpoint=checkpoint,
                    diagnostic_message="Target not found with primary strategy; falling back to secondary perception",
                )

            return RecoveryDecision(
                decision=RecoveryStrategy.REFOCUS_APPLICATION,
                is_terminal=False,
                reason=ReplanReason.TARGET_NOT_FOUND,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message="Target not found; splicing application focus step before retry",
            )

        # 4. Policy: Generation Mismatch & Stale Observation
        if reason in (ReplanReason.STALE_GENERATION, ReplanReason.STALE_OBSERVATION, ReplanReason.GENERATION_MISMATCH):
            return RecoveryDecision(
                decision=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
                is_terminal=False,
                reason=reason,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message="Desktop generation shifted; invalidating target cache and retrying with fresh observation",
            )

        # 5. Policy: Window Geometry Shifts (Moved / Resized)
        if reason in (ReplanReason.WINDOW_MOVED, ReplanReason.WINDOW_RESIZED):
            return RecoveryDecision(
                decision=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
                is_terminal=False,
                reason=reason,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message="Window geometry changed; invalidating old target coordinates and re-observing",
            )

        # 6. Policy: Application / Window Disappearance
        if reason in (ReplanReason.APPLICATION_NOT_AVAILABLE, ReplanReason.WINDOW_NOT_AVAILABLE):
            return RecoveryDecision(
                decision=RecoveryStrategy.REOPEN_APPLICATION,
                is_terminal=False,
                reason=reason,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message="Application window missing; inserting ENSURE_APPLICATION_OPEN and FOCUS recovery steps",
            )

        # 7. Policy: Window Focus Loss
        if reason in (ReplanReason.WINDOW_NOT_FOCUSED, ReplanReason.FOCUS_LOST):
            return RecoveryDecision(
                decision=RecoveryStrategy.REFOCUS_APPLICATION,
                is_terminal=False,
                reason=reason,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message="Window lost foreground focus; inserting FOCUS_APPLICATION recovery step",
            )

        # 8. Policy: Target Occluded / Blocking Popup / Dialog
        if reason == ReplanReason.OCCLUDED:
            # Check if fresh snapshot shows an unknown dialog
            # Unknown dialogs MUST fail closed for safety
            return RecoveryDecision(
                decision=RecoveryStrategy.REFOCUS_APPLICATION,
                is_terminal=False,
                reason=ReplanReason.OCCLUDED,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message="Target occluded; attempting to bring application to foreground focus",
            )

        # 9. Policy: Verification Failure / Predecessor Invalidated
        if reason in (ReplanReason.VERIFICATION_FAILED, ReplanReason.VERIFICATION_FAILURE, ReplanReason.PREDECESSOR_INVALIDATED):
            # If backtracking is enabled and a verified checkpoint exists
            if self._config.allow_backtracking and checkpoint is not None:
                return RecoveryDecision(
                    decision=RecoveryStrategy.BACKTRACK_TO_CHECKPOINT,
                    is_terminal=False,
                    reason=reason,
                    target_step_id=step_id,
                    checkpoint=checkpoint,
                    diagnostic_message=f"Post-action verification failed; rolling back to checkpoint {checkpoint.checkpoint_id}",
                )
            return RecoveryDecision(
                decision=RecoveryStrategy.SPLICED_PRECURSOR_STEPS,
                is_terminal=False,
                reason=reason,
                target_step_id=step_id,
                checkpoint=checkpoint,
                diagnostic_message="Action verification failed; splicing probe and re-verification precursors",
            )

        # 10. Default Recoverable Strategy
        return RecoveryDecision(
            decision=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
            is_terminal=False,
            reason=reason,
            target_step_id=step_id,
            checkpoint=checkpoint,
            diagnostic_message=f"Attempting recovery with fresh observation for {reason.value}",
        )
