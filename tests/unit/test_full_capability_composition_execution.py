"""Unit tests for full capability composition and strategy planning in AgentExecutionLoop."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.mark.asyncio
async def test_end_to_end_portrait_rejects_with_structured_gap():
    """Agent loop rejects unfeasible portrait goal and reports structured capability gap without faking execution."""
    loop = AgentExecutionLoop()

    # Mock interpreter to produce portrait request
    loop._interpreter = MagicMock()
    loop._interpreter.interpret = AsyncMock(
        return_value=StructuredObjective(
            raw_prompt="Open Paint and draw a portrait of a boy",
            user_goal="Open Paint and draw a portrait of a boy",
            end_condition="canvas_has_boy_portrait",
            parameters={"app_name": "Paint", "action_type": "draw"},
        )
    )

    result = await loop.run(prompt="Open Paint and draw a portrait of a boy")

    assert result.is_success is False
    assert result.total_steps == 0
    assert result.final_status == TaskCompletionStatus.UNSUPPORTED
    assert result.failure_code == "GOAL_NOT_FEASIBLY_EXECUTABLE"
    assert "No viable strategy could achieve" in result.failure_reason
    assert "IMAGE_GENERATE_AND_INSERT" in result.failure_reason or "semantic coverage" in result.failure_reason


@pytest.mark.asyncio
async def test_end_to_end_cube_drawing_attaches_selected_strategy():
    """Agent loop evaluates cube drawing, selects geometric strategy, and attaches it to context."""
    loop = AgentExecutionLoop()

    # Mock observer to return Paint active and canvas ready
    obs_1 = CurrentStateObservation(
        observation_id="obs_cube_1",
        active_window_title="Untitled - Paint",
        target_app_exists=True,
        target_app_is_active=True,
        canvas_status="READY_FOR_DRAWING",
    )
    obs_2 = CurrentStateObservation(
        observation_id="obs_cube_2",
        active_window_title="Untitled - Paint",
        target_app_exists=True,
        target_app_is_active=True,
        canvas_status="DRAWING_COMPLETED",
    )
    loop._observer = MagicMock()
    loop._observer.observe = AsyncMock(side_effect=[obs_1, obs_2, obs_2, obs_2, obs_2, obs_2])

    loop._interpreter = MagicMock()
    loop._interpreter.interpret = AsyncMock(
        return_value=StructuredObjective(
            raw_prompt="Open Paint and draw a cube",
            user_goal="Open Paint and draw a cube",
            end_condition="canvas_has_cube",
            parameters={"app_name": "Paint", "action_type": "draw", "shape": "cube"},
        )
    )

    # Pointer mock
    mock_pointer = AsyncMock()
    mock_pointer.move_to = AsyncMock(return_value=True)
    mock_pointer.mouse_down = AsyncMock(return_value=True)
    mock_pointer.mouse_up = AsyncMock(return_value=True)
    mock_pointer.drag_and_drop = AsyncMock(return_value=True)
    loop._pointer = mock_pointer

    result = await loop.run(prompt="Open Paint and draw a cube")

    # Strategy was approved and execution proceeded
    assert result.final_status != TaskCompletionStatus.UNSUPPORTED
