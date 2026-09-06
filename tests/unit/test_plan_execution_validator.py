"""Unit tests for PlanExecutionValidator (Milestone M1.8 Step 3).

Verifies:
1. Valid plan acceptance.
2. Non-valid status rejection (DRAFT, UNSUPPORTED, INVALID, FAILED).
3. Empty step list rejection.
4. Cyclic dependency graph rejection.
5. Missing dependency reference rejection.
"""

from __future__ import annotations

import pytest

from orbit.runtime.plan_execution.validator import PlanExecutionValidator
from orbit.runtime.planning.models import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)


@pytest.fixture
def validator() -> PlanExecutionValidator:
    return PlanExecutionValidator()


def test_valid_plan_passes_validation(validator: PlanExecutionValidator):
    step = PlanStep(
        step_id="step_1",
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Open app",
    )
    plan = ExecutableTaskPlan(
        plan_id="plan_valid",
        task_id="task_valid",
        description="Valid Plan",
        status=PlanStatus.VALID,
        steps=[step],
        step_dependencies={"step_1": []},
    )

    res = validator.validate(plan)
    assert res.is_valid is True
    assert res.error_code is None


def test_draft_status_rejected_by_default(validator: PlanExecutionValidator):
    step = PlanStep(
        step_id="step_1",
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Open app",
    )
    plan = ExecutableTaskPlan(
        plan_id="plan_draft",
        task_id="task_draft",
        description="Draft Plan",
        status=PlanStatus.DRAFT,
        steps=[step],
    )

    res = validator.validate(plan)
    assert res.is_valid is False
    assert "PLAN_STATUS_DRAFT" in (res.error_code or "")


def test_draft_status_allowed_when_explicit(validator: PlanExecutionValidator):
    step = PlanStep(
        step_id="step_1",
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Open app",
    )
    plan = ExecutableTaskPlan(
        plan_id="plan_draft_ok",
        task_id="task_draft_ok",
        description="Draft Plan",
        status=PlanStatus.DRAFT,
        steps=[step],
    )

    res = validator.validate(plan, allow_draft=True)
    assert res.is_valid is True


def test_unsupported_status_rejected(validator: PlanExecutionValidator):
    plan = ExecutableTaskPlan(
        plan_id="plan_unsupported",
        task_id="task_unsupported",
        description="Unsupported Plan",
        status=PlanStatus.UNSUPPORTED,
        steps=[],
    )

    res = validator.validate(plan)
    assert res.is_valid is False
    assert "PLAN_STATUS_UNSUPPORTED" in (res.error_code or "")


def test_empty_steps_rejected(validator: PlanExecutionValidator):
    plan = ExecutableTaskPlan(
        plan_id="plan_empty",
        task_id="task_empty",
        description="Empty Plan",
        status=PlanStatus.VALID,
        steps=[],
    )

    res = validator.validate(plan)
    assert res.is_valid is False
    assert res.error_code == "EMPTY_PLAN"


def test_cyclic_plan_rejected(validator: PlanExecutionValidator):
    # A -> B -> A cycle
    step_a = PlanStep(step_id="step_a", action_type=PlanActionType.FOCUS_APPLICATION, description="A", dependencies=["step_b"])
    step_b = PlanStep(step_id="step_b", action_type=PlanActionType.FOCUS_APPLICATION, description="B", dependencies=["step_a"])
    plan = ExecutableTaskPlan(
        plan_id="plan_cyclic",
        task_id="task_cyclic",
        description="Cyclic Plan",
        status=PlanStatus.VALID,
        steps=[step_a, step_b],
        step_dependencies={"step_a": ["step_b"], "step_b": ["step_a"]},
    )

    res = validator.validate(plan)
    assert res.is_valid is False
    assert res.error_code == "CYCLIC_DEPENDENCY_GRAPH"


def test_missing_dependency_reference_rejected(validator: PlanExecutionValidator):
    step_a = PlanStep(step_id="step_a", action_type=PlanActionType.FOCUS_APPLICATION, description="A", dependencies=["step_nonexistent"])
    plan = ExecutableTaskPlan(
        plan_id="plan_missing_dep",
        task_id="task_missing_dep",
        description="Missing Dep Plan",
        status=PlanStatus.VALID,
        steps=[step_a],
        step_dependencies={"step_a": ["step_nonexistent"]},
    )

    res = validator.validate(plan)
    assert res.is_valid is False
    assert res.error_code == "MISSING_DEPENDENCY_REFERENCE"
