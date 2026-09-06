"""Unit tests for Strongly Typed Failure Classifier (M1.8 Step 4)."""

import pytest
from orbit.runtime.execution import ClosedLoopExecutionResult, ExecutionState
from orbit.runtime.plan_execution.models import (
    PlanStepExecutionResult,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning.models import DeferredGroundingRequirement, PlanActionType, PlanStep
from orbit.runtime.replanning.failure_classifier import FailureClassifier
from orbit.runtime.replanning.models import (
    FailureCategory,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.task_understanding.models import TargetReference
from orbit.runtime.targeting.models import ResolvedTarget, TargetStrategy
from orbit.runtime.verification.models import VerificationOutcome, VerificationResult, VerificationStrategy


@pytest.fixture
def classifier() -> FailureClassifier:
    return FailureClassifier()


@pytest.fixture
def sample_step() -> PlanStep:
    return PlanStep(
        step_id="step_click_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click search button",
        target=TargetReference(semantic_type="button", identifier="Search"),
    )


def test_classify_human_takeover_terminal(classifier, sample_step):
    step_result = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.CANCELLED,
        failure_code="HUMAN_TAKEOVER",
        failure_reason="Human takeover detected by watchdog",
        execution_result=ClosedLoopExecutionResult(
            final_state=ExecutionState.HUMAN_TAKEOVER,
            is_success=False,
            failure_reason="Operator mouse input detected",
        ),
    )

    cl = classifier.classify_failure(sample_step, step_result)
    assert cl.category == FailureCategory.TERMINAL
    assert cl.reason == ReplanReason.HUMAN_TAKEOVER
    assert not cl.is_recoverable
    assert cl.suggested_strategy == RecoveryStrategy.ABORT_FAIL_CLOSED
    assert "step_id" in cl.evidence
    assert cl.evidence["step_status"] == PlanStepExecutionStatus.CANCELLED.value


def test_classify_operator_cancel_terminal(classifier, sample_step):
    step_result = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.CANCELLED,
        failure_code="OPERATOR_CANCEL",
        failure_reason="Operator requested cancellation",
    )

    cl = classifier.classify_failure(sample_step, step_result)
    assert cl.category == FailureCategory.TERMINAL
    assert cl.reason in (ReplanReason.CANCELLED, ReplanReason.OPERATOR_CANCEL)
    assert not cl.is_recoverable
    assert cl.suggested_strategy == RecoveryStrategy.ABORT_FAIL_CLOSED


def test_classify_unsupported_action_terminal(classifier):
    unsupported_step = PlanStep(
        step_id="step_unsup",
        step_index=0,
        action_type=PlanActionType.UNSUPPORTED_ACTION,
        description="Prohibited system reboot",
    )
    step_result = PlanStepExecutionResult(
        step_id=unsupported_step.step_id,
        step_index=0,
        action_type=unsupported_step.action_type,
        status=PlanStepExecutionStatus.UNSUPPORTED,
        failure_code="UNSUPPORTED_ACTION",
        failure_reason="Action reboot is prohibited by safety policy",
    )

    cl = classifier.classify_failure(unsupported_step, step_result)
    assert cl.category == FailureCategory.TERMINAL
    assert cl.reason == ReplanReason.UNSUPPORTED_ACTION
    assert not cl.is_recoverable


def test_classify_workspace_collision_terminal(classifier, sample_step):
    step_result = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.FAILED,
        failure_code="WORKSPACE_BOUNDARY_COLLISION",
        failure_reason="Target coordinate (2500, 100) inside reserved dock boundary",
    )

    cl = classifier.classify_failure(sample_step, step_result)
    assert cl.category == FailureCategory.TERMINAL
    assert cl.reason == ReplanReason.WORKSPACE_COLLISION
    assert not cl.is_recoverable


def test_classify_target_not_found_recoverable(classifier, sample_step):
    step_result = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.FAILED,
        failure_code="TARGET_NOT_FOUND",
        failure_reason="No matching button found with name 'Search'",
    )

    cl = classifier.classify_failure(sample_step, step_result)
    assert cl.category == FailureCategory.RECOVERABLE
    assert cl.reason == ReplanReason.TARGET_NOT_FOUND
    assert cl.is_recoverable
    assert cl.suggested_strategy == RecoveryStrategy.REFOCUS_APPLICATION


def test_classify_target_ambiguous_with_fallback_strategy(classifier):
    step = PlanStep(
        step_id="step_ambig",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Save button",
        deferred_grounding=DeferredGroundingRequirement(
            target_reference=TargetReference(semantic_type="button", identifier="Save"),
            strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.OCR_TEXT],
        ),
    )
    step_result = PlanStepExecutionResult(
        step_id=step.step_id,
        step_index=0,
        action_type=step.action_type,
        status=PlanStepExecutionStatus.FAILED,
        failure_code="TARGET_AMBIGUOUS",
        failure_reason="Multiple elements matched identifier 'Save'",
    )

    cl = classifier.classify_failure(step, step_result)
    assert cl.category == FailureCategory.RECOVERABLE
    assert cl.reason == ReplanReason.TARGET_AMBIGUOUS
    assert cl.is_recoverable
    assert cl.suggested_strategy == RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY


def test_classify_generation_mismatch(classifier, sample_step):
    step_result = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.FAILED,
        failure_code="STALE_GENERATION",
        failure_reason="Desktop generation changed from 10 to 11",
        desktop_generation_id=10,
    )

    cl = classifier.classify_failure(sample_step, step_result)
    assert cl.category == FailureCategory.RECOVERABLE
    assert cl.reason in (ReplanReason.STALE_GENERATION, ReplanReason.GENERATION_MISMATCH)
    assert cl.is_recoverable
    assert cl.suggested_strategy == RecoveryStrategy.RETRY_WITH_FRESH_OBSERVATION


def test_classify_window_moved_and_resized(classifier, sample_step):
    step_res_moved = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.FAILED,
        failure_code="WINDOW_MOVED",
        failure_reason="Target window moved from (100, 100) to (300, 300)",
    )
    cl_moved = classifier.classify_failure(sample_step, step_res_moved)
    assert cl_moved.reason == ReplanReason.WINDOW_MOVED
    assert cl_moved.is_recoverable

    step_res_resized = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.FAILED,
        failure_code="WINDOW_RESIZED",
        failure_reason="Target window resized from (800x600) to (1024x768)",
    )
    cl_resized = classifier.classify_failure(sample_step, step_res_resized)
    assert cl_resized.reason == ReplanReason.WINDOW_RESIZED
    assert cl_resized.is_recoverable


def test_classify_verification_failure(classifier, sample_step):
    from orbit.runtime.verification.models import ObservationEvidenceSummary

    step_result = PlanStepExecutionResult(
        step_id=sample_step.step_id,
        step_index=0,
        action_type=sample_step.action_type,
        status=PlanStepExecutionStatus.FAILED,
        failure_code="VERIFICATION_FAILED",
        failure_reason="Post-action state verification failed to detect text entry",
        verification_result=VerificationResult(
            outcome=VerificationOutcome.VERIFIED_FAILURE,
            confidence=0.95,
            strategy_used=VerificationStrategy.OBSERVATION_STATE_DELTA,
            pre_generation_id=1,
            post_generation_id=2,
            failure_reason="Expected text 'Hello' not present in target window",
            pre_evidence=ObservationEvidenceSummary(
                snapshot_id="snap_1",
                desktop_generation_id=1,
                timestamp_ns=1000,
                is_stale=False,
            ),
        ),
    )

    cl = classifier.classify_failure(sample_step, step_result)
    assert cl.category == FailureCategory.RECOVERABLE
    assert cl.reason in (ReplanReason.VERIFICATION_FAILED, ReplanReason.VERIFICATION_FAILURE)
    assert cl.is_recoverable
    assert "verification" in cl.evidence
    assert cl.evidence["verification"]["outcome"] == VerificationOutcome.VERIFIED_FAILURE.value
