"""Unit tests for Unified AI-Native AgentExecutionLoop in ORBIT."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.contracts.capabilities import (
    KeyboardCapability,
    ObservationCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine, OrbitDecisionEngine
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.agent.contracts import ActionOutcomeContract
from orbit.runtime.cognitive.models import (
    AbstractAction,
    AbstractActionType,
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    OutcomeStatus,
    SemanticTarget,
    StructuredObjective,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetIntent,
    TargetResolutionResult,
    TargetResolutionStatus,
)
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.fixture
def mock_capabilities():
    ws = MagicMock(spec=WorkspaceCapability)
    ws.launch_process = AsyncMock(return_value={"pid": 1234})
    ws.set_focus_window = AsyncMock(return_value=True)

    ptr = MagicMock(spec=PointerCapability)
    ptr.move_to = AsyncMock()
    ptr.click = AsyncMock()
    ptr.press_down = AsyncMock()
    ptr.release_up = AsyncMock()

    kb = MagicMock(spec=KeyboardCapability)
    kb.type_text = AsyncMock()
    kb.press_key = AsyncMock()
    kb.release_key = AsyncMock()

    obs = MagicMock(spec=ObservationCapability)
    obs.capture_screen = AsyncMock(return_value=MagicMock(frame_id="frame_1", resolution=MagicMock(model_dump=lambda: {}), format="raw"))

    bbox = TargetBoundingBox(left=400, top=300, right=500, bottom=400)
    safe_pt = SafeActionPoint(x=450, y=350, bounding_box=bbox, desktop_generation_id=1)
    ev = TargetEvidence(source="UI_AUTOMATION", identifier="button_1", name="Button")
    resolved = ResolvedTarget(
        target_id="tgt_1",
        bounding_box=bbox,
        safe_point=safe_pt,
        confidence=0.95,
        evidence=ev,
        observation_id="obs_1",
        desktop_generation_id=1,
    )

    locator = MagicMock(spec=EvidenceBasedTargetLocator)
    locator.locate_target = AsyncMock(
        return_value=TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=resolved,
        )
    )

    return {
        "workspace": ws,
        "pointer": ptr,
        "keyboard": kb,
        "observation": obs,
        "locator": locator,
    }


@pytest.mark.asyncio
async def test_agent_execution_loop_completes_deterministic_goal(mock_capabilities):
    # Simulated observation progression:
    # 1. Paint not running
    # 2. Paint opened and focused with blank canvas
    # 3. Canvas drawn on and non-blank
    obs_seq = [
        CurrentStateObservation(
            observation_id="obs_paint_init",
            target_app_exists=False,
            target_app_is_active=False,
            canvas_status="TARGET_NOT_OPEN",
            screen_summary="Desktop",
        ),
        CurrentStateObservation(
            observation_id="obs_paint_open",
            target_app_exists=True,
            target_app_is_active=True,
            active_window_title="Paint",
            canvas_status="BLANK",
            screen_summary="Paint Canvas Blank",
            visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
        ),
        CurrentStateObservation(
            observation_id="obs_paint_drawn",
            target_app_exists=True,
            target_app_is_active=True,
            active_window_title="Paint",
            canvas_status="NON_BLANK",
            screen_summary="Paint Canvas with Car Drawing",
            visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
        ),
    ]
    call_count = [0]
    def _obs_call(obj):
        idx = min(call_count[0], len(obs_seq) - 1)
        call_count[0] += 1
        return obs_seq[idx]

    obs_mock = MagicMock(spec=CurrentStateObserver)
    obs_mock.observe = AsyncMock(side_effect=_obs_call)

    from orbit.runtime.cognitive.agent_planner import AgentPlanner, PlanDirective
    planner = MagicMock(spec=AgentPlanner)
    dir_launch = PlanDirective(
        directive_id="dir_launch_paint",
        objective_id="obj_paint",
        subgoal_id="sub_1",
        subgoal_title="open paint",
        preferred_primitives=[AbstractActionType.LAUNCH_APPLICATION],
        semantic_targets=[SemanticTarget(name="mspaint", role="application")],
        expected_outcome=ActionOutcomeContract(expected_state_transition="paint_open"),
        creative_payload={"application_name": "mspaint"},
    )
    dir_draw = PlanDirective(
        directive_id="dir_draw_car",
        objective_id="obj_paint",
        subgoal_id="sub_2",
        subgoal_title="draw a car",
        preferred_primitives=[AbstractActionType.DRAW_STROKES],
        semantic_targets=[SemanticTarget(name="canvas", role="canvas")],
        expected_outcome=ActionOutcomeContract(expected_state_transition="car_drawn"),
        creative_payload={"strokes": [[(0.2, 0.2), (0.8, 0.8)]]},
    )
    def _mock_plan(objective, subgoal, **kwargs):
        if "draw" in subgoal.title.lower() or "car" in subgoal.title.lower() or "canvas" in subgoal.title.lower():
            return dir_draw, MagicMock(is_feasible=True)
        return dir_launch, MagicMock(is_feasible=True)

    planner.plan_subgoal = MagicMock(side_effect=_mock_plan)

    goal_verifier = MagicMock()
    async def _verify_goal(**kwargs):
        cur = kwargs.get("current_observation")
        is_done = cur is not None and getattr(cur, "canvas_status", "") == "NON_BLANK"
        return MagicMock(is_satisfied=is_done, is_completed=is_done, status=TaskCompletionStatus.COMPLETED if is_done else TaskCompletionStatus.IN_PROGRESS)

    goal_verifier.verify_goal_achievement = AsyncMock(side_effect=_verify_goal)

    loop = AgentExecutionLoop(
        observer=obs_mock,
        planner=planner,
        goal_verifier=goal_verifier,
        workspace=mock_capabilities["workspace"],
        pointer=mock_capabilities["pointer"],
        keyboard=mock_capabilities["keyboard"],
        observation=mock_capabilities["observation"],
        target_locator=mock_capabilities["locator"],
        budget=ExecutionBudget(max_total_actions=10),
    )

    # Test running "open paint and draw a car"
    res: AgentExecutionResult = await loop.run("open paint and draw a car")
    assert res.is_success is True
    assert res.total_steps >= 2
    assert mock_capabilities["pointer"].move_to.await_count > 0


@pytest.mark.asyncio
async def test_agent_execution_loop_respects_cancellation(mock_capabilities):
    loop = AgentExecutionLoop(
        workspace=mock_capabilities["workspace"],
        pointer=mock_capabilities["pointer"],
        keyboard=mock_capabilities["keyboard"],
        observation=mock_capabilities["observation"],
        target_locator=mock_capabilities["locator"],
    )

    cancel_source = CancellationSource()
    cancel_source.cancel("Operator interrupted")

    res: AgentExecutionResult = await loop.run(
        "draw a cube in paint",
        cancel_token=cancel_source.token,
    )
    assert res.is_success is False
    assert res.final_status == TaskCompletionStatus.CANCELLED
    assert "Cancelled" in (res.failure_reason or "")


@pytest.mark.asyncio
async def test_agent_execution_loop_prevents_static_coordinates_in_actions():
    # Enforce architectural invariant: LLM action parameters cannot contain static (x, y) coordinates
    with pytest.raises(ValueError):
        AbstractAction(
            action_type=AbstractActionType.CLICK_ELEMENT,
            target=SemanticTarget(name="button"),
            parameters={"x": 500, "y": 300},
        )