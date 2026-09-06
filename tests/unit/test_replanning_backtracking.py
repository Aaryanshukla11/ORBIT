"""Unit tests for Bounded Backtracking Engine (M1.8 Step 4)."""

import pytest
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanActionType, PlanStatus, PlanStep
from orbit.runtime.replanning.backtracking import BacktrackingEngine
from orbit.runtime.replanning.models import (
    ExecutionCheckpoint,
    FailureCategory,
    FailureClassification,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.task_understanding.models import TargetReference


@pytest.fixture
def engine() -> BacktrackingEngine:
    return BacktrackingEngine(max_depth=2)


@pytest.fixture
def complex_plan() -> ExecutableTaskPlan:
    # A -> B -> C -> D
    step_a = PlanStep(
        step_id="step_A",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Open App",
        target=TargetReference(semantic_type="application", identifier="App"),
    )
    step_b = PlanStep(
        step_id="step_B",
        step_index=1,
        action_type=PlanActionType.FOCUS_APPLICATION,
        description="Focus App",
        target=TargetReference(semantic_type="application", identifier="App"),
        dependencies=["step_A"],
    )
    step_c = PlanStep(
        step_id="step_C",
        step_index=2,
        action_type=PlanActionType.ENTER_TEXT,
        description="Type text in field",
        dependencies=["step_B"],
    )
    step_d = PlanStep(
        step_id="step_D",
        step_index=3,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Save button",
        dependencies=["step_C"],
    )
    return ExecutableTaskPlan(
        plan_id="plan_complex",
        task_id="task_test",
        description="4-step plan",
        status=PlanStatus.VALID,
        steps=[step_a, step_b, step_c, step_d],
        step_dependencies={"step_A": [], "step_B": ["step_A"], "step_C": ["step_B"], "step_D": ["step_C"]},
    )


def test_backtrack_to_valid_checkpoint(engine, complex_plan):
    # Suppose step A and B succeeded.
    # Step C succeeded previously, but step D failed verification because the text in step C wasn't actually saved.
    # We backtrack to checkpoint B.
    chk_b = ExecutionCheckpoint(
        checkpoint_id="chk_B",
        step_id="step_B",
        step_index=1,
        completed_step_ids=["step_A", "step_B"],
        application_name="App",
    )

    failed_step_d = complex_plan.steps[3]
    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.VERIFICATION_FAILED,
        is_recoverable=True,
        diagnostic_message="Save verification failed",
        suggested_strategy=RecoveryStrategy.BACKTRACK_TO_CHECKPOINT,
        step_id="step_D",
        action_type=PlanActionType.ACTIVATE_CONTROL,
    )

    result = engine.backtrack_to_checkpoint(
        current_plan=complex_plan,
        failed_step=failed_step_d,
        checkpoint=chk_b,
        completed_step_ids={"step_A", "step_B", "step_C"},
        classification=classification,
        revision_id=2,
    )

    assert result.is_success is True
    assert result.repaired_plan is not None
    assert result.preserved_step_ids == ["step_A", "step_B"]
    assert result.backtracked_step_ids == ["step_C"]

    repaired = result.repaired_plan
    # Should have step_A, step_B, recovery_step, step_C, step_D
    assert len(repaired.steps) == 5
    dag = ActionDependencyGraph.from_plan(repaired)
    assert not dag.has_cycles()


def test_backtrack_without_checkpoint_fails_closed(engine, complex_plan):
    failed_step_d = complex_plan.steps[3]
    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.PREDECESSOR_INVALIDATED,
        is_recoverable=True,
        diagnostic_message="Predecessor state invalidated",
        suggested_strategy=RecoveryStrategy.BACKTRACK_TO_CHECKPOINT,
        step_id="step_D",
        action_type=PlanActionType.ACTIVATE_CONTROL,
    )

    result = engine.backtrack_to_checkpoint(
        current_plan=complex_plan,
        failed_step=failed_step_d,
        checkpoint=None,
        completed_step_ids={"step_A"},
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is False
    assert result.repaired_plan is None
    assert result.failure_code == "NO_CHECKPOINT"
