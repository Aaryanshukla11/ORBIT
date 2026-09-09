"""Unit tests for HierarchicalGoalDecomposer."""

import pytest
from orbit.runtime.cognitive.decomposer import HierarchicalGoalDecomposer
from orbit.runtime.cognitive.models import StructuredObjective


@pytest.mark.asyncio
async def test_linguistic_conjunction_splitting():
    decomposer = HierarchicalGoalDecomposer()
    obj = StructuredObjective(
        raw_prompt="Open calculator and then calculate 42 plus 58",
        user_goal="Calculate 42 plus 58",
        end_condition="calculator_shows_100",
    )

    plan = await decomposer.decompose(obj)
    assert len(plan.sub_objectives) == 2
    assert "Open calculator" in plan.sub_objectives[0].title
    assert "calculate 42 plus 58" in plan.sub_objectives[1].title


@pytest.mark.asyncio
async def test_numbered_list_splitting():
    decomposer = HierarchicalGoalDecomposer()
    obj = StructuredObjective(
        raw_prompt="1. Launch editor\n2. Write report\n3. Save file",
        user_goal="Create report file",
        end_condition="file_saved",
    )

    plan = await decomposer.decompose(obj)
    assert len(plan.sub_objectives) == 3
    assert plan.sub_objectives[0].title == "Launch editor"
    assert plan.sub_objectives[1].title == "Write report"
    assert plan.sub_objectives[2].title == "Save file"


@pytest.mark.asyncio
async def test_single_atomic_goal():
    decomposer = HierarchicalGoalDecomposer()
    obj = StructuredObjective(
        raw_prompt="Click the submit button",
        user_goal="Click submit button",
        end_condition="button_clicked",
    )

    plan = await decomposer.decompose(obj)
    assert len(plan.sub_objectives) == 1
    assert plan.sub_objectives[0].title == "Click submit button"


@pytest.mark.asyncio
async def test_explicit_subtasks_from_objective():
    decomposer = HierarchicalGoalDecomposer()
    obj = StructuredObjective(
        raw_prompt="Complex compound task",
        user_goal="Complete compound task",
        end_condition="task_complete",
        subtasks=["Phase A: Research", "Phase B: Compile", "Phase C: Deliver"],
    )

    plan = await decomposer.decompose(obj)
    assert len(plan.sub_objectives) == 3
    assert "Phase A: Research" in plan.sub_objectives[0].title
    assert "Phase C: Deliver" in plan.sub_objectives[2].title
