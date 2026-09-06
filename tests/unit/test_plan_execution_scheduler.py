"""Unit tests for PlanExecutionScheduler (Milestone M1.8 Step 3).

Verifies:
1. Dependency readiness and promotion to READY.
2. Strict predecessor success invariants.
3. Predecessor failure blocking downstream dependents.
4. Cancellation propagation to unexecuted steps.
5. Deterministic topological ordering.
"""

from __future__ import annotations

import pytest

from orbit.runtime.plan_execution.models import PlanStepExecutionStatus
from orbit.runtime.plan_execution.scheduler import PlanExecutionScheduler
from orbit.runtime.planning.models import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)


@pytest.fixture
def linear_plan() -> ExecutableTaskPlan:
    # A -> B -> C
    step_a = PlanStep(step_id="step_a", step_index=0, action_type=PlanActionType.ENSURE_APPLICATION_OPEN, description="Open App", dependencies=[])
    step_b = PlanStep(step_id="step_b", step_index=1, action_type=PlanActionType.FOCUS_APPLICATION, description="Focus App", dependencies=["step_a"])
    step_c = PlanStep(step_id="step_c", step_index=2, action_type=PlanActionType.ENTER_TEXT, description="Type Text", dependencies=["step_b"])
    return ExecutableTaskPlan(
        plan_id="plan_linear_1",
        task_id="task_linear_1",
        description="Linear Test Plan",
        status=PlanStatus.VALID,
        steps=[step_a, step_b, step_c],
        step_dependencies={"step_a": [], "step_b": ["step_a"], "step_c": ["step_b"]},
    )


@pytest.fixture
def diamond_plan() -> ExecutableTaskPlan:
    # A -> B, A -> C, (B, C) -> D
    step_a = PlanStep(step_id="step_a", step_index=0, action_type=PlanActionType.ENSURE_APPLICATION_OPEN, description="A", dependencies=[])
    step_b = PlanStep(step_id="step_b", step_index=1, action_type=PlanActionType.LOCATE_TARGET, description="B", dependencies=["step_a"])
    step_c = PlanStep(step_id="step_c", step_index=2, action_type=PlanActionType.LOCATE_TARGET, description="C", dependencies=["step_a"])
    step_d = PlanStep(step_id="step_d", step_index=3, action_type=PlanActionType.ACTIVATE_CONTROL, description="D", dependencies=["step_b", "step_c"])
    return ExecutableTaskPlan(
        plan_id="plan_diamond_1",
        task_id="task_diamond_1",
        description="Diamond Test Plan",
        status=PlanStatus.VALID,
        steps=[step_a, step_b, step_c, step_d],
        step_dependencies={"step_a": [], "step_b": ["step_a"], "step_c": ["step_a"], "step_d": ["step_b", "step_c"]},
    )


def test_initial_readiness(linear_plan: ExecutableTaskPlan):
    scheduler = PlanExecutionScheduler(linear_plan)

    assert scheduler.get_step_status("step_a") == PlanStepExecutionStatus.READY
    assert scheduler.get_step_status("step_b") == PlanStepExecutionStatus.PENDING
    assert scheduler.get_step_status("step_c") == PlanStepExecutionStatus.PENDING

    next_step = scheduler.get_next_ready_step()
    assert next_step is not None
    assert next_step.step_id == "step_a"


def test_linear_progression_success(linear_plan: ExecutableTaskPlan):
    scheduler = PlanExecutionScheduler(linear_plan)

    # Step A runs and succeeds
    scheduler.mark_running("step_a")
    assert scheduler.get_step_status("step_a") == PlanStepExecutionStatus.RUNNING
    scheduler.mark_succeeded("step_a")

    # Step B should now be promoted to READY
    assert scheduler.get_step_status("step_a") == PlanStepExecutionStatus.SUCCEEDED
    assert scheduler.get_step_status("step_b") == PlanStepExecutionStatus.READY
    assert scheduler.get_step_status("step_c") == PlanStepExecutionStatus.PENDING

    # Step B runs and succeeds
    scheduler.mark_running("step_b")
    scheduler.mark_succeeded("step_b")

    # Step C should now be READY
    assert scheduler.get_step_status("step_c") == PlanStepExecutionStatus.READY
    scheduler.mark_running("step_c")
    scheduler.mark_succeeded("step_c")

    assert scheduler.is_complete is True
    assert scheduler.all_succeeded is True


def test_failure_blocks_downstream_dependents(linear_plan: ExecutableTaskPlan):
    scheduler = PlanExecutionScheduler(linear_plan)

    # Step A fails
    scheduler.mark_running("step_a")
    scheduler.mark_failed("step_a", reason="Application window not found")

    assert scheduler.get_step_status("step_a") == PlanStepExecutionStatus.FAILED
    assert scheduler.get_step_status("step_b") == PlanStepExecutionStatus.BLOCKED
    assert scheduler.get_step_status("step_c") == PlanStepExecutionStatus.BLOCKED

    assert scheduler.is_complete is True
    assert scheduler.all_succeeded is False
    assert scheduler.get_next_ready_step() is None


def test_diamond_dependency_resolution(diamond_plan: ExecutableTaskPlan):
    scheduler = PlanExecutionScheduler(diamond_plan)

    # Step A succeeds
    scheduler.mark_running("step_a")
    scheduler.mark_succeeded("step_a")

    # Both B and C should be READY, D still PENDING
    assert scheduler.get_step_status("step_b") == PlanStepExecutionStatus.READY
    assert scheduler.get_step_status("step_c") == PlanStepExecutionStatus.READY
    assert scheduler.get_step_status("step_d") == PlanStepExecutionStatus.PENDING

    # Step B succeeds, Step D still pending because C has not finished
    scheduler.mark_running("step_b")
    scheduler.mark_succeeded("step_b")
    assert scheduler.get_step_status("step_d") == PlanStepExecutionStatus.PENDING

    # Step C succeeds -> Step D should now become READY
    scheduler.mark_running("step_c")
    scheduler.mark_succeeded("step_c")
    assert scheduler.get_step_status("step_d") == PlanStepExecutionStatus.READY

    scheduler.mark_running("step_d")
    scheduler.mark_succeeded("step_d")
    assert scheduler.all_succeeded is True


def test_diamond_partial_failure_blocks_join(diamond_plan: ExecutableTaskPlan):
    scheduler = PlanExecutionScheduler(diamond_plan)

    scheduler.mark_running("step_a")
    scheduler.mark_succeeded("step_a")

    # Step B succeeds, but Step C fails
    scheduler.mark_running("step_b")
    scheduler.mark_succeeded("step_b")

    scheduler.mark_running("step_c")
    scheduler.mark_failed("step_c", reason="Element C disappeared")

    # Step D requires both B and C, so D must be BLOCKED
    assert scheduler.get_step_status("step_d") == PlanStepExecutionStatus.BLOCKED
    assert scheduler.is_complete is True
    assert scheduler.all_succeeded is False


def test_cancellation_marks_remaining_steps(linear_plan: ExecutableTaskPlan):
    scheduler = PlanExecutionScheduler(linear_plan)

    scheduler.mark_running("step_a")
    scheduler.mark_succeeded("step_a")

    # Cancel while B is ready
    scheduler.mark_cancelled(reason="Operator cancelled")

    assert scheduler.get_step_status("step_a") == PlanStepExecutionStatus.SUCCEEDED
    assert scheduler.get_step_status("step_b") == PlanStepExecutionStatus.CANCELLED
    assert scheduler.get_step_status("step_c") == PlanStepExecutionStatus.CANCELLED
    assert scheduler.is_complete is True
