"""Integration tests for Phase 1 Foundation components wired into AgentExecutionLoop."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.task_completion.models import TaskCompletionStatus
from orbit.runtime.world_model.model import AgentWorldModel


@pytest.mark.asyncio
async def test_phase1_runtime_feasibility_gate_blocks_locked_desktop():
    # Mock observer returning observation
    mock_obs = CurrentStateObservation(
        active_process_name="explorer.exe",
        active_window_title="Desktop",
    )
    mock_observer = MagicMock()
    mock_observer.capture_observation = AsyncMock(return_value=mock_obs)
    mock_observer.observe = AsyncMock(return_value=mock_obs)

    # World model with locked desktop
    locked_wm = AgentWorldModel(is_desktop_locked=True)

    loop = AgentExecutionLoop(
        observer=mock_observer,
        world_model=locked_wm,
    )
    # Ensure world_model retains locked state when run() starts
    loop._runtime_feasibility_evaluator._check_network = False

    # Force world_model to stay locked by monkeypatching or testing evaluator
    res = await loop.run(prompt="Open notepad and type hello")

    # Should be rejected cleanly
    assert res.is_success is False
    assert res.final_status == TaskCompletionStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_phase1_captcha_detection_blocks_execution():
    # Mock observer returning captcha in OCR
    captcha_obs = CurrentStateObservation(
        ocr_tokens=["Please", "verify", "you", "are", "human"],
    )
    mock_observer = MagicMock()
    mock_observer.capture_observation = AsyncMock(return_value=captcha_obs)
    mock_observer.observe = AsyncMock(return_value=captcha_obs)

    loop = AgentExecutionLoop(
        observer=mock_observer,
    )
    loop._runtime_feasibility_evaluator._check_network = False

    res = await loop.run(prompt="Complete registration form")

    assert res.is_success is False
    assert res.failure_code == "RUNTIME_ENVIRONMENT_INFEASIBLE"
    assert "CAPTCHA" in res.failure_reason
