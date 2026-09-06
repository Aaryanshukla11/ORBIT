"""Unit tests for DAG plan repair and precursor step splicing (M1.8 Step 4)."""

import pytest
from orbit.runtime.planning.models import (
    DeferredGroundingRequirement,
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.replanning.models import (
    FailureCategory,
    FailureClassification,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.replanning.repair import PlanRepairEngine
from orbit.runtime.task_understanding.models import TargetReference
from orbit.runtime.targeting.models import TargetStrategy


@pytest.fixture
def repair_engine() -> PlanRepairEngine:
    return PlanRepairEngine()


@pytest.fixture
def baseline_plan() -> ExecutableTaskPlan:
    step_open = PlanStep(
        step_id="step_open",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Ensure Notepad is open",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
        dependencies=[],
    )
    step_locate = PlanStep(
        step_id="step_locate",
        step_index=1,
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
        description="Locate text area",
        target=TargetReference(semantic_type="text_area", identifier="Text Editor"),
        dependencies=["step_open"],
    )
    step_type = PlanStep(
        step_id="step_type",
        step_index=2,
        action_type=PlanActionType.ENTER_TEXT,
        description="Type Hello World",
        parameters={"text": "Hello World"},
        dependencies=["step_locate"],
    )
    return ExecutableTaskPlan(
        plan_id="plan_sample",
        task_id="task_sample",
        description="Open Notepad and write hello world",
        status=PlanStatus.VALID,
        steps=[step_open, step_locate, step_type],
        step_dependencies={
            "step_open": [],
            "step_locate": ["step_open"],
            "step_type": ["step_locate"],
        },
    )


def test_repair_by_inserting_focus(repair_engine: PlanRepairEngine, baseline_plan: ExecutableTaskPlan):
    """Repairing by inserting focus must preserve step_open and insert a focus precursor step."""
    failed_step = baseline_plan.steps[1]  # step_locate
    completed_step_ids = {"step_open"}
    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.WINDOW_NOT_FOCUSED,
        is_recoverable=True,
        diagnostic_message="Notepad is not focused",
        suggested_strategy=RecoveryStrategy.REFOCUS_APPLICATION,
        step_id="step_locate",
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
    )

    result = repair_engine.repair_plan(
        current_plan=baseline_plan,
        failed_step=failed_step,
        completed_step_ids=completed_step_ids,
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is True
    repaired_plan = result.repaired_plan
    assert repaired_plan is not None
    assert repaired_plan.plan_id == "plan_sample_rev1"

    # Step count increased by 1 (focus step added)
    assert len(repaired_plan.steps) == 4
    step_ids = [s.step_id for s in repaired_plan.steps]
    assert "step_open" in step_ids
    assert "step_locate" in step_ids
    assert "step_type" in step_ids

    # Preserved steps explicitly declared
    assert result.preserved_step_ids == ["step_open"]
    assert len(result.inserted_steps) == 1
    focus_step = result.inserted_steps[0]
    assert focus_step.action_type == PlanActionType.FOCUS_APPLICATION

    # Verify dependency wiring: step_locate now depends on focus_step
    locate_step_in_repaired = next(s for s in repaired_plan.steps if s.step_id == "step_locate")
    assert locate_step_in_repaired.dependencies == [focus_step.step_id]


def test_repair_by_perception_fallback(repair_engine: PlanRepairEngine, baseline_plan: ExecutableTaskPlan):
    """Repairing with perception fallback must update strategy preferences."""
    failed_step = baseline_plan.steps[1].model_copy(deep=True)
    failed_step.deferred_grounding = DeferredGroundingRequirement(
        target_reference=TargetReference(semantic_type="text_area", identifier="Text Editor"),
        strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.OCR_TEXT],
    )
    baseline_plan.steps[1] = failed_step

    completed_step_ids = {"step_open"}
    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.TARGET_NOT_FOUND,
        is_recoverable=True,
        diagnostic_message="Text Editor not found via accessibility",
        suggested_strategy=RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY,
        step_id="step_locate",
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
    )

    result = repair_engine.repair_plan(
        current_plan=baseline_plan,
        failed_step=failed_step,
        completed_step_ids=completed_step_ids,
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is True
    repaired_plan = result.repaired_plan
    assert repaired_plan is not None

    repaired_locate = next(s for s in repaired_plan.steps if s.step_id == "step_locate")
    assert repaired_locate.deferred_grounding is not None
    # Strategy preferences should have rotated [ACCESSIBILITY, OCR] -> [OCR, ACCESSIBILITY]
    assert repaired_locate.deferred_grounding.strategy_preferences[0] == TargetStrategy.OCR_TEXT


def test_repair_reopening_application(repair_engine: PlanRepairEngine, baseline_plan: ExecutableTaskPlan):
    """Repairing by reopening app splices both ENSURE_OPEN and FOCUS precursor steps."""
    failed_step = baseline_plan.steps[1]
    completed_step_ids = set()
    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.TARGET_NOT_FOUND,
        is_recoverable=True,
        diagnostic_message="App process died",
        suggested_strategy=RecoveryStrategy.REOPEN_APPLICATION,
        step_id="step_locate",
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
    )

    result = repair_engine.repair_plan(
        current_plan=baseline_plan,
        failed_step=failed_step,
        completed_step_ids=completed_step_ids,
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is True
    assert len(result.inserted_steps) == 2
    open_step = result.inserted_steps[0]
    focus_step = result.inserted_steps[1]
    assert open_step.action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert focus_step.action_type == PlanActionType.FOCUS_APPLICATION
    assert focus_step.dependencies == [open_step.step_id]


def test_repair_rejects_terminal_failure(repair_engine: PlanRepairEngine, baseline_plan: ExecutableTaskPlan):
    """Repair engine must reject terminal classifications with is_success=False."""
    failed_step = baseline_plan.steps[1]
    classification = FailureClassification(
        category=FailureCategory.TERMINAL,
        reason=ReplanReason.HUMAN_TAKEOVER,
        is_recoverable=False,
        diagnostic_message="Takeover active",
        suggested_strategy=RecoveryStrategy.ABORT_FAIL_CLOSED,
        failure_code="HUMAN_TAKEOVER",
        step_id="step_locate",
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
    )

    result = repair_engine.repair_plan(
        current_plan=baseline_plan,
        failed_step=failed_step,
        completed_step_ids={"step_open"},
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is False
    assert result.repaired_plan is None
    assert result.failure_code == "HUMAN_TAKEOVER"
