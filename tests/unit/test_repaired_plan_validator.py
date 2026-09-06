"""Unit tests for RepairedPlanValidator (M1.8 Step 4)."""

import pytest
from orbit.runtime.planning.models import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.replanning.validator import RepairedPlanValidator
from orbit.runtime.task_understanding.models import TargetReference


@pytest.fixture
def validator() -> RepairedPlanValidator:
    return RepairedPlanValidator()


def test_valid_repaired_plan_passes(validator: RepairedPlanValidator):
    """A valid repaired plan preserving completed steps must pass validation."""
    s1 = PlanStep(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Step 1",
        target=TargetReference(semantic_type="application", identifier="App"),
    )
    s2 = PlanStep(
        step_id="repair_focus",
        step_index=1,
        action_type=PlanActionType.FOCUS_APPLICATION,
        description="Refocus App",
        target=TargetReference(semantic_type="application", identifier="App"),
        dependencies=["step_1"],
    )
    s3 = PlanStep(
        step_id="step_2",
        step_index=2,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Step 2",
        target=TargetReference(semantic_type="button", identifier="Btn"),
        dependencies=["repair_focus"],
    )

    repaired_plan = ExecutableTaskPlan(
        plan_id="plan_rev1",
        task_id="task_1",
        description="Repaired plan",
        status=PlanStatus.VALID,
        steps=[s1, s2, s3],
        step_dependencies={
            "step_1": [],
            "repair_focus": ["step_1"],
            "step_2": ["repair_focus"],
        },
    )

    res = validator.validate_repaired_plan(repaired_plan, completed_step_ids={"step_1"})
    assert res.is_valid is True
    assert res.error_code is None


def test_repaired_plan_dropping_completed_step_fails(validator: RepairedPlanValidator):
    """Repaired plan that accidentally drops a previously completed step must fail fail-closed."""
    s2 = PlanStep(
        step_id="repair_focus",
        step_index=0,
        action_type=PlanActionType.FOCUS_APPLICATION,
        description="Refocus App",
        target=TargetReference(semantic_type="application", identifier="App"),
    )
    s3 = PlanStep(
        step_id="step_2",
        step_index=1,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Step 2",
        target=TargetReference(semantic_type="button", identifier="Btn"),
        dependencies=["repair_focus"],
    )

    # Missing step_1 from steps
    repaired_plan = ExecutableTaskPlan(
        plan_id="plan_rev1",
        task_id="task_1",
        description="Repaired plan missing completed step",
        status=PlanStatus.VALID,
        steps=[s2, s3],
        step_dependencies={"repair_focus": [], "step_2": ["repair_focus"]},
    )

    res = validator.validate_repaired_plan(repaired_plan, completed_step_ids={"step_1"})
    assert res.is_valid is False
    assert res.error_code == "COMPLETED_STEPS_DROPPED"
    assert "step_1" in res.error_message


def test_repaired_plan_with_cycle_fails(validator: RepairedPlanValidator):
    """Repaired plan with cyclic dependencies must fail validation."""
    s1 = PlanStep(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Step 1",
        target=TargetReference(semantic_type="application", identifier="App"),
        dependencies=["step_2"],  # Cycle!
    )
    s2 = PlanStep(
        step_id="step_2",
        step_index=1,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Step 2",
        target=TargetReference(semantic_type="button", identifier="Btn"),
        dependencies=["step_1"],  # Cycle!
    )

    cyclic_plan = ExecutableTaskPlan(
        plan_id="plan_cyclic",
        task_id="task_1",
        description="Cyclic repaired plan",
        status=PlanStatus.VALID,
        steps=[s1, s2],
        step_dependencies={"step_1": ["step_2"], "step_2": ["step_1"]},
    )

    res = validator.validate_repaired_plan(cyclic_plan, completed_step_ids=set())
    assert res.is_valid is False
    assert res.error_code in ("CYCLIC_DEPENDENCY_GRAPH", "CYCLIC_DEPENDENCY_DETECTED", "REPAIRED_PLAN_CYCLE_DETECTED")
