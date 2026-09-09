"""Unit tests for Capability-Aware Agent Execution Loop and Cognitive Decision Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.mark.asyncio
async def test_agent_loop_early_rejects_unfeasible_portrait_goal():
    """Agent Loop rejects unfeasible portrait goal early without faking physical execution."""
    loop = AgentExecutionLoop()

    # Mock interpreter to return structured objective for boy portrait
    loop._interpreter = MagicMock()
    loop._interpreter.interpret = AsyncMock(
        return_value=StructuredObjective(
            raw_prompt="Open Paint and draw a portrait of a boy",
            user_goal="Open Paint and draw a portrait of a boy",
            end_condition="canvas_has_boy_portrait",
            parameters={"app_name": "Paint", "action_type": "draw", "shape": "portrait_of_boy"},
        )
    )

    result = await loop.run(prompt="Open Paint and draw a portrait of a boy")

    # Feasibility gate rejected early: no fake cube drawn, 0 actions taken
    assert result.is_success is False
    assert result.total_steps == 0
    assert result.final_status == TaskCompletionStatus.UNSUPPORTED
    assert result.failure_code == "GOAL_NOT_FEASIBLY_EXECUTABLE"
    assert "NOT FEASIBLY EXECUTABLE" in result.failure_reason


@pytest.mark.asyncio
async def test_cognitive_engine_rule4_aborts_on_unfeasible_drawing_intent():
    """Decision Engine Rule 4 returns ABORT_UNACHIEVABLE when requested drawing exceeds capabilities."""
    engine = CognitiveDecisionEngine()

    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "portrait_of_boy"},
    )
    obs = CurrentStateObservation(
        observation_id="obs_paint_active",
        active_window_title="Untitled - Paint",
        target_app_exists=True,
        target_app_is_active=True,
        canvas_status="READY_FOR_DRAWING",
    )

    decision = await engine.decide_next_step(objective=obj, observation=obs)

    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.ABORT_UNACHIEVABLE
    assert "Drawing goal unachievable" in decision.decision_summary


@pytest.mark.asyncio
async def test_cognitive_engine_rule4_permits_feasible_cube_drawing():
    """Decision Engine Rule 4 returns DRAW_STROKES for supported geometric shape."""
    engine = CognitiveDecisionEngine()

    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Open Paint and draw a cube",
        end_condition="canvas_has_cube",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "cube"},
    )
    obs = CurrentStateObservation(
        observation_id="obs_paint_active",
        active_window_title="Untitled - Paint",
        target_app_exists=True,
        target_app_is_active=True,
        canvas_status="READY_FOR_DRAWING",
    )

    decision = await engine.decide_next_step(objective=obj, observation=obs)

    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.DRAW_STROKES
    assert decision.next_action.parameters.get("shape") == "cube"
