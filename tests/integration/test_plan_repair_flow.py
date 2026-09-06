"""Integration tests for Plan Repair Engine flow (M1.8 Step 4)."""

import pytest
from orbit.runtime.planning.graph import ActionDependencyGraph
from orbit.runtime.planning.models import (
    DeferredGroundingRequirement,
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.replanning.failure_classifier import FailureClassifier
from orbit.runtime.replanning.models import (
    FailureCategory,
    FailureClassification,
    RecoveryStrategy,
    ReplanReason,
)
from orbit.runtime.replanning.repair import PlanRepairEngine
from orbit.runtime.replanning.validator import RepairedPlanValidator
from orbit.runtime.task_understanding.models import TargetReference
from orbit.runtime.targeting.models import TargetStrategy


@pytest.fixture
def repair_engine() -> PlanRepairEngine:
    return PlanRepairEngine()


@pytest.fixture
def validator() -> RepairedPlanValidator:
    return RepairedPlanValidator()


@pytest.fixture
def base_plan() -> ExecutableTaskPlan:
    step_1 = PlanStep(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Open Notepad",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
    )
    step_2 = PlanStep(
        step_id="step_2",
        step_index=1,
        action_type=PlanActionType.ENTER_TEXT,
        description="Type Hello",
        target=TargetReference(semantic_type="text_area", identifier="Text Editor"),
        dependencies=["step_1"],
    )
    step_3 = PlanStep(
        step_id="step_3",
        step_index=2,
        action_type=PlanActionType.SAVE_DOCUMENT,
        description="Save file",
        dependencies=["step_2"],
    )
    return ExecutableTaskPlan(
        plan_id="plan_base",
        task_id="task_base",
        description="Base 3-step plan",
        status=PlanStatus.VALID,
        steps=[step_1, step_2, step_3],
        step_dependencies={"step_1": [], "step_2": ["step_1"], "step_3": ["step_2"]},
    )


def test_repair_insert_focus_step(repair_engine, validator, base_plan):
    failed_step = base_plan.steps[1]  # step_2
    completed_step_ids = {"step_1"}

    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.WINDOW_NOT_FOCUSED,
        is_recoverable=True,
        diagnostic_message="Notepad is not foreground focused",
        suggested_strategy=RecoveryStrategy.REFOCUS_APPLICATION,
        step_id="step_2",
        action_type=PlanActionType.ENTER_TEXT,
    )

    result = repair_engine.repair_plan(
        current_plan=base_plan,
        failed_step=failed_step,
        completed_step_ids=completed_step_ids,
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is True
    assert result.repaired_plan is not None
    assert len(result.inserted_steps) == 1
    assert result.inserted_steps[0].action_type == PlanActionType.FOCUS_APPLICATION

    val_res = validator.validate_repaired_plan(result.repaired_plan, completed_step_ids)
    assert val_res.is_valid is True

    dag = ActionDependencyGraph.from_plan(result.repaired_plan)
    assert not dag.has_cycles()


def test_repair_reopen_application_splicing(repair_engine, validator, base_plan):
    failed_step = base_plan.steps[1]  # step_2
    completed_step_ids = {"step_1"}

    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.APPLICATION_NOT_AVAILABLE,
        is_recoverable=True,
        diagnostic_message="Notepad process terminated",
        suggested_strategy=RecoveryStrategy.REOPEN_APPLICATION,
        step_id="step_2",
        action_type=PlanActionType.ENTER_TEXT,
    )

    result = repair_engine.repair_plan(
        current_plan=base_plan,
        failed_step=failed_step,
        completed_step_ids=completed_step_ids,
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is True
    assert result.repaired_plan is not None
    # Spliced OPEN + FOCUS steps
    assert len(result.inserted_steps) == 2
    assert result.inserted_steps[0].action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert result.inserted_steps[1].action_type == PlanActionType.FOCUS_APPLICATION

    val_res = validator.validate_repaired_plan(result.repaired_plan, completed_step_ids)
    assert val_res.is_valid is True


def test_repair_perception_fallback_rotation(repair_engine, validator):
    step_locate = PlanStep(
        step_id="step_loc",
        step_index=0,
        action_type=PlanActionType.LOCATE_TARGET,
        description="Locate brush button",
        deferred_grounding=DeferredGroundingRequirement(
            target_reference=TargetReference(semantic_type="ui_control", identifier="Brush"),
            strategy_preferences=[TargetStrategy.ACCESSIBILITY_ELEMENT, TargetStrategy.OCR_TEXT, TargetStrategy.VISUAL_TEMPLATE],
        ),
    )
    plan = ExecutableTaskPlan(
        plan_id="plan_perc",
        task_id="task_perc",
        description="Perception plan",
        status=PlanStatus.VALID,
        steps=[step_locate],
        step_dependencies={"step_loc": []},
    )

    classification = FailureClassification(
        category=FailureCategory.RECOVERABLE,
        reason=ReplanReason.TARGET_NOT_FOUND,
        is_recoverable=True,
        diagnostic_message="No accessibility element matched",
        suggested_strategy=RecoveryStrategy.FALLBACK_PERCEPTION_STRATEGY,
        step_id="step_loc",
        action_type=PlanActionType.LOCATE_TARGET,
    )

    result = repair_engine.repair_plan(
        current_plan=plan,
        failed_step=step_locate,
        completed_step_ids=set(),
        classification=classification,
        revision_id=1,
    )

    assert result.is_success is True
    repaired_step = result.repaired_plan.steps[0]
    # Rotated: [OCR_TEXT, VISUAL_TEMPLATE, ACCESSIBILITY_ELEMENT]
    assert repaired_step.deferred_grounding.strategy_preferences[0] == TargetStrategy.OCR_TEXT
    assert repaired_step.deferred_grounding.strategy_preferences[1] == TargetStrategy.VISUAL_TEMPLATE
