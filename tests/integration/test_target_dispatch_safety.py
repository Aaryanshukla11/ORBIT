"""Integration tests for target resolution, pre-dispatch workspace validation gates, and safety preemption."""

import asyncio
from datetime import datetime, timezone
import pytest

from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import Action, ActionStage, ActionTier, TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.state_machine import SystemState
from orbit.runtime.targeting import (
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


@pytest.fixture
def target_test_env():
    bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    tkv = MockHumanTakeoverAdapter()
    wsp = MockWorkspaceAdapter()
    sft = MockSafetyCoordinator()

    reg = CapabilityRegistry()
    reg.register(CapabilityType.OBSERVATION, obs)
    reg.register(CapabilityType.POINTER, ptr)
    reg.register(CapabilityType.KEYBOARD, kbd)
    reg.register(CapabilityType.HUMAN_TAKEOVER, tkv)
    reg.register(CapabilityType.WORKSPACE, wsp)
    reg.register(CapabilityType.SAFETY, sft)

    orch = OrbitOrchestrator(
        event_bus=bus,
        registry=reg,
        clock=SystemClock(),
    )
    return orch, obs, ptr, wsp, tkv


@pytest.mark.asyncio
async def test_target_resolved_task_execution_flow(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    # Configure mock observation snapshot with a target button
    element = ObservedElement(
        element_id="el_search_btn",
        source="UI_AUTOMATION",
        name="Search Button",
        role="Button",
        control_type="Button",
        bounds=BoundingBox(left=600, top=350, width=150, height=45),
        is_enabled=True,
    )
    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_tgt_01",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        detected_elements=[element],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
    )

    action = AbstractAction(
        action_id="act_tgt_01",
        action_type=AbstractActionType.CLICK,
        parameters={"desktop_generation_id": wsp.desktop_generation_id},
        target=SemanticTarget(name="Search Button", role="Button"),
        expected_effect="Click Search Button",
    )
    obj = StructuredObjective(raw_prompt="Click Search Button", user_goal="Click Search Button", end_condition="done")
    cancel_token = CancellationSource().token

    target_intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Search Button")
    target_res = orch.target_locator.locate_target(snapshot=obs.mock_snapshot, intent=target_intent)
    assert target_res.status == TargetResolutionStatus.RESOLVED
    assert target_res.target is not None

    async def grounding_fn(tgt, o):
        res = orch.target_locator.locate_target(snapshot=obs.mock_snapshot, intent=target_intent)
        if res.status == TargetResolutionStatus.RESOLVED and res.target:
            return (res.target.action_point.x, res.target.action_point.y)
        return None

    post_obs = CurrentStateObservation(
        observation_id="obs_post_click",
        perceived_elements_count=1,
    )
    async def mock_observe(objective):
        return post_obs

    res = await orch.primitive_controller.execute_primitive(
        action=action,
        pre_observation=CurrentStateObservation(perceived_elements_count=0),
        objective=obj,
        grounding_fn=grounding_fn,
        observe_fn=mock_observe,
        cancel_token=cancel_token,
    )

    assert res.execution_outcome.dispatch_success is True
    assert len(ptr.click_history) == 1
    click = ptr.click_history[0]
    assert 600 <= click["x"] < 750
    assert 350 <= click["y"] < 395

    await orch.shutdown()


@pytest.mark.asyncio
async def test_target_resolution_failure_causes_zero_pointer_dispatches(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    # Empty elements in snapshot
    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_empty",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        detected_elements=[],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
    )

    action = AbstractAction(
        action_id="act_missing_tgt",
        action_type=AbstractActionType.CLICK,
        parameters={"desktop_generation_id": wsp.desktop_generation_id},
        target=SemanticTarget(name="NonExistentButton", role="Button"),
        expected_effect="Click NonExistentButton",
    )
    obj = StructuredObjective(raw_prompt="Click NonExistentButton", user_goal="Click NonExistentButton", end_condition="done")
    cancel_token = CancellationSource().token

    target_intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="NonExistentButton")
    target_res = orch.target_locator.locate_target(snapshot=obs.mock_snapshot, intent=target_intent)
    assert target_res.status == TargetResolutionStatus.NOT_FOUND

    async def missing_grounding(tgt, o):
        res = orch.target_locator.locate_target(snapshot=obs.mock_snapshot, intent=target_intent)
        if res.status == TargetResolutionStatus.RESOLVED and res.target:
            return (res.target.action_point.x, res.target.action_point.y)
        return None

    res = await orch.primitive_controller.execute_primitive(
        action=action,
        pre_observation=CurrentStateObservation(),
        objective=obj,
        grounding_fn=missing_grounding,
        cancel_token=cancel_token,
    )

    assert res.execution_outcome.dispatch_success is False
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_stale_observation_causes_zero_pointer_dispatches(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    element = ObservedElement(
        element_id="el_ok",
        source="UI_AUTOMATION",
        name="OK",
        role="Button",
        bounds=BoundingBox(left=200, top=200, width=50, height=30),
    )
    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_stale",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        detected_elements=[element],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.STALE,
        is_stale=True,
        invalidation_reason="TTL expired",
    )

    target_intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="OK")
    target_res = orch.target_locator.locate_target(snapshot=obs.mock_snapshot, intent=target_intent)
    assert target_res.status == TargetResolutionStatus.STALE_OBSERVATION

    action = AbstractAction(
        action_id="act_stale_tgt",
        action_type=AbstractActionType.CLICK,
        parameters={"desktop_generation_id": wsp.desktop_generation_id},
        target=SemanticTarget(name="OK", role="Button"),
        expected_effect="Click OK on stale screen",
    )
    obj = StructuredObjective(raw_prompt="Click OK", user_goal="Click OK", end_condition="done")
    cancel_token = CancellationSource().token

    async def stale_grounding(tgt, o):
        res = orch.target_locator.locate_target(snapshot=obs.mock_snapshot, intent=target_intent)
        if res.status == TargetResolutionStatus.RESOLVED and res.target:
            return (res.target.action_point.x, res.target.action_point.y)
        return None

    res = await orch.primitive_controller.execute_primitive(
        action=action,
        pre_observation=CurrentStateObservation(),
        objective=obj,
        grounding_fn=stale_grounding,
        cancel_token=cancel_token,
    )

    assert res.execution_outcome.dispatch_success is False
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_workspace_reserved_dock_collision_blocks_pointer_dispatch(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    # Register right appbar (width 400px; reserved 1520..1920)
    await wsp.register_appbar(edge="right", size=400)

    # Directly dispatch pointer action targeting inside dock area (x=1700, y=500)
    action = AbstractAction(
        action_id="act_dock_collision",
        action_type=AbstractActionType.CLICK,
        parameters={"desktop_generation_id": wsp.desktop_generation_id},
        target=SemanticTarget(name="dock_target", role="point"),
        expected_effect="Click inside dock area",
    )

    async def dock_grounding(tgt, obs):
        return (1700, 500)

    cancel_token = CancellationSource().token
    res = await orch.primitive_controller.execute_primitive(
        action=action,
        pre_observation=CurrentStateObservation(),
        objective=StructuredObjective(raw_prompt="Click", user_goal="Click", end_condition="done"),
        grounding_fn=dock_grounding,
        cancel_token=cancel_token,
    )

    assert res.execution_outcome.dispatch_success is False
    assert "RESERVED_WORKSPACE_COLLISION" in (res.execution_outcome.error_message or "")

    # CRITICAL: Zero clicks in dock area
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_workspace_stale_generation_blocks_pointer_dispatch(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    initial_gen = wsp.desktop_generation_id
    # Bump generation by registering and unregistering appbar
    await wsp.register_appbar(edge="right", size=200)
    current_gen = wsp.desktop_generation_id
    assert current_gen > initial_gen

    # Attempt action with stale generation
    action = AbstractAction(
        action_id="act_stale_gen",
        action_type=AbstractActionType.CLICK,
        parameters={"desktop_generation_id": initial_gen},
        target=SemanticTarget(name="stale_target", role="point"),
        expected_effect="Click with stale gen",
    )

    async def stale_gen_grounding(tgt, obs):
        return (500, 300)

    cancel_token = CancellationSource().token
    res = await orch.primitive_controller.execute_primitive(
        action=action,
        pre_observation=CurrentStateObservation(),
        objective=StructuredObjective(raw_prompt="Click", user_goal="Click", end_condition="done"),
        grounding_fn=stale_gen_grounding,
        cancel_token=cancel_token,
    )

    assert res.execution_outcome.dispatch_success is False
    assert "STALE_COORDINATE_CONTEXT" in (res.execution_outcome.error_message or "")
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_workspace_out_of_bounds_blocks_pointer_dispatch(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    action = AbstractAction(
        action_id="act_oob",
        action_type=AbstractActionType.CLICK,
        parameters={"desktop_generation_id": wsp.desktop_generation_id, "button": "none"},
        target=SemanticTarget(name="oob_target", role="point"),
        expected_effect="Move out of bounds",
    )

    async def oob_grounding(tgt, obs):
        return (-200, 500)

    cancel_token = CancellationSource().token
    res = await orch.primitive_controller.execute_primitive(
        action=action,
        pre_observation=CurrentStateObservation(),
        objective=StructuredObjective(raw_prompt="Move", user_goal="Move", end_condition="done"),
        grounding_fn=oob_grounding,
        cancel_token=cancel_token,
    )

    assert res.execution_outcome.dispatch_success is False
    assert "OUT_OF_BOUNDS" in (res.execution_outcome.error_message or "")
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_human_takeover_preempts_before_pointer_dispatch(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    # Trigger human takeover
    await orch.handle_human_takeover(reason="Physical user input detected", source="physical_mouse")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    action = AbstractAction(
        action_id="act_during_takeover",
        action_type=AbstractActionType.CLICK,
        parameters={"desktop_generation_id": wsp.desktop_generation_id},
        target=SemanticTarget(name="tkv_target", role="point"),
        expected_effect="Click during takeover",
    )

    def safety_gate_takeover(act, coords):
        if orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
            return False, "Pointer action blocked: Human takeover is currently active"
        return True, None

    async def tkv_grounding(tgt, obs):
        return (500, 300)

    cancel_token = CancellationSource().token
    res = await orch.primitive_controller.execute_primitive(
        action=action,
        pre_observation=CurrentStateObservation(),
        objective=StructuredObjective(raw_prompt="Click", user_goal="Click", end_condition="done"),
        grounding_fn=tkv_grounding,
        safety_gate_fn=safety_gate_takeover,
        cancel_token=cancel_token,
    )

    assert res.execution_outcome.dispatch_success is False
    assert "Human takeover is currently active" in (res.execution_outcome.error_message or "")
    assert len(ptr.click_history) == 0

    await orch.shutdown()
