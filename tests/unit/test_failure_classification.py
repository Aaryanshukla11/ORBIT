"""Unit tests for deterministic failure classification in dynamic replanning (M1.8 Step 4)."""

import pytest
from orbit.runtime.execution.models import ClosedLoopExecutionResult, ExecutionState
from orbit.runtime.plan_execution.models import (
    CompiledRuntimeAction,
    PlanStepExecutionResult,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning.models import (
    DeferredGroundingRequirement,
    PlanActionType,
    PlanStep,
)
from orbit.runtime.replanning.analyzer import ExecutionFailureAnalyzer
from orbit.runtime.replanning.models import (
    FailureCategory,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.task_understanding.models import TargetReference
from orbit.runtime.targeting.models import TargetStrategy
from orbit.runtime.verification.models import (
    ActionVerificationResult,
    ObservationEvidenceSummary,
    VerificationOutcome,
    VerificationStrategy,
)


@pytest.fixture
def analyzer() -> ExecutionFailureAnalyzer:
    return ExecutionFailureAnalyzer()


@pytest.fixture
def sample_step() -> PlanStep:
    return PlanStep(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Submit Button",
        target=TargetReference(semantic_type="button", identifier="Submit"),
    )


def test_classify_human_takeover(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Human takeover must be classified strictly as TERMINAL / fail-closed."""
    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.CANCELLED,
        failure_reason="Human takeover active; execution preempted",
        failure_code="HUMAN_TAKEOVER",
        execution_result=ClosedLoopExecutionResult(
            task_id="t1",
            final_state=ExecutionState.HUMAN_TAKEOVER,
            is_success=False,
            is_action_dispatched=False,
            failure_reason="Human takeover",
            failure_code="HUMAN_TAKEOVER",
        ),
    )

    classification = analyzer.classify_failure(sample_step, step_res)
    assert classification.category == FailureCategory.TERMINAL
    assert classification.reason == ReplanReason.HUMAN_TAKEOVER
    assert classification.is_recoverable is False
    assert classification.suggested_strategy == RecoveryStrategy.ABORT_FAIL_CLOSED


def test_classify_operator_cancel(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Operator cancellation must be classified strictly as TERMINAL / fail-closed."""
    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.CANCELLED,
        failure_reason="Execution cancelled by operator",
        failure_code="OPERATOR_CANCEL",
    )

    classification = analyzer.classify_failure(sample_step, step_res)
    assert classification.category == FailureCategory.TERMINAL
    assert classification.reason == ReplanReason.OPERATOR_CANCEL
    assert classification.is_recoverable is False
    assert classification.suggested_strategy == RecoveryStrategy.ABORT_FAIL_CLOSED


def test_classify_unsupported_action(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Unsupported operations must be classified as TERMINAL."""
    unsupported_step = PlanStep(
        step_id="step_unsupported",
        step_index=0,
        action_type=PlanActionType.UNSUPPORTED_ACTION,
        description="Execute unknown hardware instruction",
    )
    step_res = PlanStepExecutionResult(
        step_id="step_unsupported",
        step_index=0,
        action_type=PlanActionType.UNSUPPORTED_ACTION,
        status=PlanStepExecutionStatus.UNSUPPORTED,
        failure_reason="Action UNSUPPORTED_ACTION is unsupported",
        failure_code="UNSUPPORTED_ACTION",
    )

    classification = analyzer.classify_failure(unsupported_step, step_res)
    assert classification.category == FailureCategory.TERMINAL
    assert classification.reason == ReplanReason.UNSUPPORTED_ACTION
    assert classification.is_recoverable is False


def test_classify_workspace_collision(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Safety gate workspace / dock boundary collisions must be classified as TERMINAL."""
    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.FAILED,
        failure_reason="Target coordinate out of bounds; collides with ORBIT dock area",
        failure_code="WORKSPACE_COLLISION",
    )

    classification = analyzer.classify_failure(sample_step, step_res)
    assert classification.category == FailureCategory.TERMINAL
    assert classification.reason == ReplanReason.WORKSPACE_COLLISION
    assert classification.is_recoverable is False


def test_classify_stale_generation(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Stale observation / generation invalidation must be RECOVERABLE."""
    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.FAILED,
        failure_reason="Desktop generation changed during target resolution (gen 1 != 2)",
        failure_code="STALE_OBSERVATION",
    )

    classification = analyzer.classify_failure(sample_step, step_res)
    assert classification.category == FailureCategory.RECOVERABLE
    assert classification.reason == ReplanReason.GENERATION_MISMATCH
    assert classification.is_recoverable is True
    assert classification.suggested_strategy == RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION


def test_classify_target_not_found(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Target not found must be RECOVERABLE with perception fallback or refocusing."""
    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.FAILED,
        failure_reason="Target 'Submit' not found in active observation frame",
        failure_code="TARGET_NOT_FOUND",
    )

    classification = analyzer.classify_failure(sample_step, step_res)
    assert classification.category == FailureCategory.RECOVERABLE
    assert classification.reason == ReplanReason.TARGET_NOT_FOUND
    assert classification.is_recoverable is True


def test_classify_target_not_found_with_multiple_strategies(analyzer: ExecutionFailureAnalyzer):
    """Target not found on step with multiple fallback strategies suggests FALLBACK_PERCEPTION_STRATEGY."""
    step = PlanStep(
        step_id="step_fallback",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Save",
        deferred_grounding=DeferredGroundingRequirement(
            target_reference=TargetReference(semantic_type="button", identifier="Save"),
            strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.OCR_TEXT],
        ),
    )
    step_res = PlanStepExecutionResult(
        step_id="step_fallback",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.FAILED,
        failure_reason="Target element not found via accessibility",
        failure_code="TARGET_NOT_FOUND",
    )

    classification = analyzer.classify_failure(step, step_res)
    assert classification.is_recoverable is True
    assert classification.reason == ReplanReason.TARGET_NOT_FOUND
    assert classification.suggested_strategy == RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY


def test_classify_window_not_focused(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Window not in foreground must suggest REFOCUS_APPLICATION."""
    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.FAILED,
        failure_reason="Application window is not foreground focused",
        failure_code="WINDOW_NOT_FOCUSED",
    )

    classification = analyzer.classify_failure(sample_step, step_res)
    assert classification.category == FailureCategory.RECOVERABLE
    assert classification.reason == ReplanReason.WINDOW_NOT_FOCUSED
    assert classification.is_recoverable is True
    assert classification.suggested_strategy == RecoveryStrategy.REFOCUS_APPLICATION


def test_classify_verification_failure(analyzer: ExecutionFailureAnalyzer, sample_step: PlanStep):
    """Post-action verification failure must be RECOVERABLE with spliced recovery precursor."""
    step_res = PlanStepExecutionResult(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        status=PlanStepExecutionStatus.FAILED,
        failure_reason="Verification failed: expected focus property to become True",
        failure_code="VERIFICATION_FAILURE",
        verification_result=ActionVerificationResult(
            outcome=VerificationOutcome.VERIFIED_FAILURE,
            strategy_used=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            confidence=0.9,
            pre_generation_id=1,
            post_generation_id=2,
            pre_evidence=ObservationEvidenceSummary(
                snapshot_id="snap_1",
                desktop_generation_id=1,
                timestamp_ns=1000,
                is_stale=False,
            ),
        ),
    )

    classification = analyzer.classify_failure(sample_step, step_res)
    assert classification.category == FailureCategory.RECOVERABLE
    assert classification.reason == ReplanReason.VERIFICATION_FAILURE
    assert classification.is_recoverable is True
    assert classification.suggested_strategy == RecoveryStrategy.SPLICED_PRECURSOR_STEPS
