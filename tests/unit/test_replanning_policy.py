"""Unit tests for Recovery Policy Engine (M1.8 Step 4)."""

import pytest
from orbit.runtime.planning.models import DeferredGroundingRequirement, PlanActionType, PlanStep
from orbit.runtime.replanning.history import ReplanHistoryTracker
from orbit.runtime.replanning.models import (
    ExecutionCheckpoint,
    FailureCategory,
    FailureClassification,
    RecoveryPolicyConfig,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.replanning.recovery_policy import RecoveryPolicyEngine
from orbit.runtime.task_understanding.models import TargetReference
from orbit.runtime.targeting.models import TargetStrategy


@pytest.fixture
def policy_engine() -> RecoveryPolicyEngine:
    config = RecoveryPolicyConfig(
        max_target_resolution_attempts=3,
        max_global_replans=3,
        max_step_replans=2,
        allow_backtracking=True,
    )
    return RecoveryPolicyEngine(config=config)


@pytest.fixture
def history(policy_engine) -> ReplanHistoryTracker:
    return ReplanHistoryTracker(budget=policy_engine.config)


@pytest.fixture
def sample_step() -> PlanStep:
    return PlanStep(
        step_id="step_edit",
        step_index=1,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click edit canvas",
        target=TargetReference(semantic_type="ui_control", identifier="Canvas"),
    )


def test_decide_terminal_on_takeover(policy_engine, history, sample_step):
    cl = FailureClassification(
        category=FailureCategory.TERMINAL,
        reason=ReplanReason.HUMAN_TAKEOVER,
        is_recoverable=False,
        diagnostic_message="Takeover active",
        suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
        step_id=sample_step.step_id,
        action_type=sample_step.action_type,
    )

    decision = policy_engine.decide_recovery(sample_step, cl, history)
    assert decision.is_terminal is True
    assert decision.decision == RecoveryStrategy.ABORT_FAIL_CLOSED
    assert decision.reason == ReplanReason.HUMAN_TAKEOVER


def test_decide_target_not_found_with_multimodal_fallback(policy_engine, history):
    step = PlanStep(
        step_id="step_btn",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Paint Brush",
        deferred_grounding=DeferredGroundingRequirement(
            target_reference=TargetReference(semantic_type="ui_control", identifier="Brush"),
            strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.OCR_TEXT],
        ),
    )
    cl = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.TARGET_NOT_FOUND,
        is_recoverable=True,
        diagnostic_message="Element not found",
        suggested_strategy=RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY,
        step_id=step.step_id,
        action_type=step.action_type,
    )

    decision = policy_engine.decide_recovery(step, cl, history)
    assert decision.decision == RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY
    assert not decision.is_terminal


def test_decide_target_ambiguous_fails_closed_without_fallbacks(policy_engine, history, sample_step):
    # Step has no multimodal alternatives
    cl = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.TARGET_AMBIGUOUS,
        is_recoverable=True,
        diagnostic_message="Ambiguous targets",
        suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
        step_id=sample_step.step_id,
        action_type=sample_step.action_type,
    )

    decision = policy_engine.decide_recovery(sample_step, cl, history)
    assert decision.is_terminal is True
    assert decision.decision == RecoveryStrategy.ABORT_FAIL_CLOSED


def test_decide_window_moved_reobserves(policy_engine, history, sample_step):
    cl = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.WINDOW_MOVED,
        is_recoverable=True,
        diagnostic_message="Window moved",
        suggested_strategy=RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION,
        step_id=sample_step.step_id,
        action_type=sample_step.action_type,
    )

    decision = policy_engine.decide_recovery(sample_step, cl, history)
    assert decision.decision == RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION
    assert not decision.is_terminal


def test_decide_verification_failure_triggers_backtracking_if_checkpoint_available(policy_engine, history, sample_step):
    chk = ExecutionCheckpoint(
        checkpoint_id="chk_0",
        step_id="step_open",
        step_index=0,
        completed_step_ids=["step_open"],
        application_name="Paint",
    )
    cl = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.VERIFICATION_FAILED,
        is_recoverable=True,
        diagnostic_message="Canvas pixel state unchanged",
        suggested_strategy=RecoveryStrategy.SPLICED_PRECURSOR_STEPS,
        step_id=sample_step.step_id,
        action_type=sample_step.action_type,
    )

    decision = policy_engine.decide_recovery(sample_step, cl, history, checkpoint=chk)
    assert decision.decision == RecoveryStrategy.BACKTRACK_TO_CHECKPOINT
    assert decision.checkpoint.checkpoint_id == "chk_0"
    assert not decision.is_terminal


def test_decide_budget_exhaustion_terminates(policy_engine, history, sample_step):
    cl = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.TARGET_NOT_FOUND,
        is_recoverable=True,
        diagnostic_message="Element not found",
        suggested_strategy=RecoveryStrategy.REFOCUS_APPLICATION,
        step_id=sample_step.step_id,
        action_type=sample_step.action_type,
    )

    # Exhaust step budget
    history.record_replan(sample_step, cl)
    history.record_replan(sample_step, cl)

    decision = policy_engine.decide_recovery(sample_step, cl, history)
    assert decision.is_terminal is True
    assert decision.decision == RecoveryStrategy.ABORT_FAIL_CLOSED
    assert decision.reason == ReplanReason.RECOVERY_BUDGET_EXHAUSTED
