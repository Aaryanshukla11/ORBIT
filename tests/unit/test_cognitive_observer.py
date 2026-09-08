"""Unit tests for the Current State Observer in the Cognitive Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.cognitive.observer import CurrentStateObserver


@pytest.mark.asyncio
async def test_observe_basic():
    observer = CurrentStateObserver()
    objective = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Draw cube in Paint",
        end_condition="canvas_has_cube_drawing",
        target_entities=["mspaint", "canvas"],
        parameters={"app_name": "mspaint", "action_type": "draw", "shape": "cube"},
    )

    obs = await observer.observe(objective)
    assert isinstance(obs, CurrentStateObservation)
    assert obs.timestamp_utc is not None
    assert obs.canvas_status is not None


@pytest.mark.asyncio
async def test_observe_with_mock_observation_capability():
    mock_obs_cap = MagicMock()
    mock_frame = MagicMock()
    mock_frame.resolution.width = 1920
    mock_frame.resolution.height = 1080
    mock_obs_cap.capture_screen = AsyncMock(return_value=mock_frame)

    observer = CurrentStateObserver(observation=mock_obs_cap)
    objective = StructuredObjective(
        raw_prompt="Open Notepad",
        user_goal="Open Notepad",
        end_condition="notepad_is_open",
        target_entities=["notepad"],
        parameters={"app_name": "notepad"},
    )

    obs = await observer.observe(objective)
    assert "1920x1080" in obs.screen_summary
