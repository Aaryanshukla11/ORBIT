"""Unit tests for replanning audit history, budget enforcement, and loop detection (M1.8 Step 4)."""

import pytest
from orbit.runtime.planning.models import PlanActionType, PlanStep
from orbit.runtime.replanning.history import ReplanHistoryTracker
from orbit.runtime.replanning.models import (
    FailureCategory,
    FailureClassification,
    RecoveryStrategy,
    ReplanBudget,
    ReplanReason,
    ReplanStatus,
)
from orbit.runtime.task_understanding.models import TargetReference


@pytest.fixture
def sample_step() -> PlanStep:
    return PlanStep(
        step_id="step_edit",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click text box",
        target=TargetReference(semantic_type="text_field", identifier="AddressBox"),
    )


@pytest.fixture
def sample_classification() -> FailureClassification:
    return FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.TARGET_NOT_FOUND,
        is_recoverable=True,
        diagnostic_message="AddressBox element not found in frame",
        suggested_strategy=RecoveryStrategy.REFOCUS_APPLICATION,
        failure_code="TARGET_NOT_FOUND",
        step_id="step_edit",
        action_type=PlanActionType.ACTIVATE_CONTROL,
    )


def test_replan_history_record_audit(sample_step: PlanStep, sample_classification: FailureClassification):
    """History tracker must record structured, timestamped replan records."""
    tracker = ReplanHistoryTracker()
    record = tracker.record_replan(
        step=sample_step,
        classification=sample_classification,
        repaired_plan_id="plan_1_rev1",
        preserved_step_ids=["step_open"],
        inserted_step_ids=["repair_focus_1"],
        removed_step_ids=[],
        desktop_generation_id=3,
        status=ReplanStatus.RESUMED,
    )

    assert record.revision_id == 1
    assert record.trigger_step_id == "step_edit"
    assert record.classification.reason == ReplanReason.TARGET_NOT_FOUND
    assert record.preserved_step_ids == ["step_open"]
    assert record.inserted_step_ids == ["repair_focus_1"]
    assert len(tracker.records) == 1
    assert tracker.total_replans == 1
    assert tracker.get_step_replan_count("step_edit") == 1


def test_global_budget_exhaustion(sample_step: PlanStep, sample_classification: FailureClassification):
    """Tracker must enforce global replan budget limits fail-closed."""
    budget = ReplanBudget(max_global_replans=2, max_step_replans=5)
    tracker = ReplanHistoryTracker(budget=budget)

    assert tracker.is_budget_exhausted() is False

    tracker.record_replan(sample_step, sample_classification)
    assert tracker.is_budget_exhausted() is False

    tracker.record_replan(sample_step, sample_classification)
    assert tracker.is_budget_exhausted() is True


def test_per_step_budget_exhaustion(sample_step: PlanStep, sample_classification: FailureClassification):
    """Tracker must enforce per-step replan limits fail-closed."""
    budget = ReplanBudget(max_global_replans=10, max_step_replans=2)
    tracker = ReplanHistoryTracker(budget=budget)

    assert tracker.is_budget_exhausted("step_edit") is False

    tracker.record_replan(sample_step, sample_classification)
    assert tracker.is_budget_exhausted("step_edit") is False

    tracker.record_replan(sample_step, sample_classification)
    assert tracker.is_budget_exhausted("step_edit") is True
    # Other steps should not be exhausted
    assert tracker.is_budget_exhausted("other_step") is False


def test_cyclic_loop_detection(sample_step: PlanStep, sample_classification: FailureClassification):
    """Tracker must detect repeating failure signatures and declare cyclic loop."""
    tracker = ReplanHistoryTracker()

    sig1 = tracker.create_signature(sample_step, sample_classification, desktop_generation_id=1)
    assert tracker.is_cyclic_loop(sig1) is False

    # Record first occurrence
    tracker.record_replan(sample_step, sample_classification, desktop_generation_id=1)

    # Check same signature again
    sig2 = tracker.create_signature(sample_step, sample_classification, desktop_generation_id=1)
    assert tracker.is_cyclic_loop(sig2) is True


def test_different_desktop_generation_not_cyclic_loop(sample_step: PlanStep, sample_classification: FailureClassification):
    """A failure on a different desktop generation is not an identical static loop."""
    tracker = ReplanHistoryTracker()

    # Record first occurrence on gen 1
    tracker.record_replan(sample_step, sample_classification, desktop_generation_id=1)

    # Check signature on gen 2
    sig_gen2 = tracker.create_signature(sample_step, sample_classification, desktop_generation_id=2)
    assert tracker.is_cyclic_loop(sig_gen2) is False
