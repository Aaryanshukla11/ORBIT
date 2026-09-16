"""Integration test for fresh desktop observation in AgentExecutionLoop (Step 3).

Verifies that:
1. DesktopObservation is captured freshly before reasoning.
2. After an action executes, a brand-new observation is captured for state transition verification.
3. No stale observations are recycled across action boundaries.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.contracts.capabilities import (
    KeyboardCapability,
    ObservationCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.models.common import BoundingBox
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.perception.models import (
    DesktopObservation,
    WindowObservation,
)
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.mark.asyncio
async def test_agent_fresh_observation_cycle():
    """Verify that AgentExecutionLoop calls observe() freshly before and after each action."""
    mock_perception = MagicMock(spec=DesktopPerceptionEngine)

    # Observation 1: Desktop, target app (Notepad) closed
    obs_1 = DesktopObservation(
        observation_id="obs_cycle_1",
        screen_width=1920,
        screen_height=1080,
        foreground_window=WindowObservation(
            hwnd=10,
            title="Desktop",
            window_class="Progman",
            is_foreground=True,
            is_visible=True,
            window_bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
            client_bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
        ),
        visible_windows=[],
    )

    # Observation 2: After Launch, Notepad open and active
    obs_2 = DesktopObservation(
        observation_id="obs_cycle_2",
        screen_width=1920,
        screen_height=1080,
        foreground_window=WindowObservation(
            hwnd=200,
            title="Untitled - Notepad",
            window_class="Notepad",
            is_foreground=True,
            is_visible=True,
            window_bounds=BoundingBox(left=100, top=100, width=800, height=600),
            client_bounds=BoundingBox(left=108, top=130, width=784, height=562),
            process_name="notepad.exe",
        ),
        visible_windows=[],
    )

    # Observation 3: Completed goal check
    obs_3 = DesktopObservation(
        observation_id="obs_cycle_3",
        screen_width=1920,
        screen_height=1080,
        foreground_window=obs_2.foreground_window,
        visible_windows=[obs_2.foreground_window],
    )

    # Return successive fresh observations
    mock_perception.observe = AsyncMock(side_effect=[obs_1, obs_2, obs_3])
    observer = CurrentStateObserver(perception_engine=mock_perception)

    mock_ws = MagicMock(spec=WorkspaceCapability)
    mock_ws.launch_process = AsyncMock(return_value={"pid": 1234})

    loop = AgentExecutionLoop(
        observer=observer,
        workspace=mock_ws,
        budget=ExecutionBudget(max_total_actions=5),
    )

    res: AgentExecutionResult = await loop.run("Open Notepad")

    # Verify that observe() was called multiple times (fresh observation cycle)
    assert mock_perception.observe.call_count >= 2
    assert len(res.step_history) > 0

    # Step 0 observed before action
    step0 = res.step_history[0]
    assert step0.action_dispatched.action_type == AbstractActionType.LAUNCH_APPLICATION
    assert step0.post_observation.active_window_title == "Untitled - Notepad"
    assert step0.post_observation.active_window_hwnd == 200
