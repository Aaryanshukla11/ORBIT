"""Integration tests for the closed-loop Cognitive Execution Loop with Layered Decision Hierarchy."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.loop import CognitiveExecutionLoop
from orbit.runtime.cognitive.models import (
    AbstractAction,
    AbstractActionType,
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.mark.asyncio
async def test_cognitive_execution_loop_multi_step_workflow():
    """Test full multi-step lifecycle: App Not Running -> Launch -> Focus -> Draw -> Complete."""
    mock_workspace = MagicMock()
    mock_workspace.launch_process = AsyncMock(return_value={"pid": 1234})
    mock_workspace.set_focus_window = AsyncMock(return_value=True)

    mock_pointer = MagicMock()
    mock_pointer.move_to = AsyncMock()
    mock_pointer.button_down = AsyncMock()
    mock_pointer.button_up = AsyncMock()

    mock_keyboard = MagicMock()
    mock_keyboard.type_text = AsyncMock()

    step_observations = [
        # Step 0: App not open
        CurrentStateObservation(
            active_window_title="Desktop",
            target_app_exists=False,
            target_app_is_active=False,
        ),
        # Step 1: App launched but not focused
        CurrentStateObservation(
            active_window_title="Desktop",
            target_app_exists=True,
            target_app_is_active=False,
        ),
        # Step 2: App active in foreground
        CurrentStateObservation(
            active_window_title="Untitled - Paint",
            target_app_exists=True,
            target_app_is_active=True,
            canvas_status="READY_FOR_DRAWING",
        ),
        # Step 3: Post drawing verification
        CurrentStateObservation(
            active_window_title="Untitled - Paint",
            target_app_exists=True,
            target_app_is_active=True,
            canvas_status="NON_BLANK",
        ),
    ]
    obs_idx = 0

    class MockObserver(CurrentStateObserver):
        async def observe(self, objective=None):
            nonlocal obs_idx
            curr = step_observations[min(obs_idx, len(step_observations) - 1)]
            obs_idx += 1
            return curr

    loop = CognitiveExecutionLoop(
        interpreter=LLMIntentInterpreter(),
        observer=MockObserver(),
        decision_engine=CognitiveDecisionEngine(),
        workspace=mock_workspace,
        pointer=mock_pointer,
        keyboard=mock_keyboard,
    )

    result = await loop.run(prompt="Open Paint and draw a cube")

    assert result.is_success
    assert result.final_status == TaskCompletionStatus.COMPLETED
    assert result.total_steps > 0
    # Ensure physical pointer drag actuation was called
    assert mock_pointer.button_down.call_count > 0
    assert mock_pointer.button_up.call_count > 0
    # Ensure step history has auditable decision summaries
    for step in result.step_history:
        assert step.decision.decision_summary != ""
        assert step.decision.decision_confidence > 0.0


@pytest.mark.asyncio
async def test_cognitive_execution_loop_repeated_action_budget_halt():
    """Test that repeating the same action without progress halts cleanly under budget."""
    mock_workspace = MagicMock()
    mock_workspace.launch_process = AsyncMock(return_value=None)  # launch always fails

    stuck_observation = CurrentStateObservation(
        active_window_title="Desktop",
        target_app_exists=False,
        target_app_is_active=False,
    )

    class StuckObserver(CurrentStateObserver):
        async def observe(self, objective=None):
            return stuck_observation

    budget = ExecutionBudget(max_repeated_actions_without_progress=2, no_progress_timeout_sec=5.0)
    loop = CognitiveExecutionLoop(
        interpreter=LLMIntentInterpreter(),
        observer=StuckObserver(),
        decision_engine=CognitiveDecisionEngine(),
        workspace=mock_workspace,
        budget=budget,
    )

    result = await loop.run(prompt="Open Notepad")
    assert not result.is_success
    assert result.final_status == TaskCompletionStatus.FAILED
    assert "REPEATED_ACTION_STAGNATION" in (result.failure_code or "")
