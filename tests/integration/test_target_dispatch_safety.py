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
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.state_machine import SystemState
from orbit.runtime.targeting import (
    TargetIntent,
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

    # Submit task with TargetIntent in context
    task = await orch.submit_task(
        session_id="sess_tgt_01",
        prompt="Click the search button",
        context={
            "target_intent": {
                "strategy": "ACCESSIBILITY_ELEMENT",
                "name": "Search Button",
            }
        },
    )

    # Wait for completion
    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED

    # Verify pointer clicked within the target element bounds
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

    task = await orch.submit_task(
        session_id="sess_missing_tgt",
        prompt="Click non-existent button",
        context={
            "target_intent": {
                "strategy": "ACCESSIBILITY_ELEMENT",
                "name": "NonExistentButton",
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED
    assert final_task.error is not None
    assert final_task.error.code == "TARGET_NOT_FOUND"

    # CRITICAL: Zero pointer clicks or movements dispatched
    assert len(ptr.click_history) == 0
    assert len(ptr.move_history) == 1  # Only initial starting point

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

    task = await orch.submit_task(
        session_id="sess_stale",
        prompt="Click OK on stale screen",
        context={
            "target_intent": {
                "strategy": "ACCESSIBILITY_ELEMENT",
                "name": "OK",
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED
    assert final_task.error.code == "TARGET_STALE_OBSERVATION"

    # CRITICAL: Zero pointer clicks dispatched
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_workspace_reserved_dock_collision_blocks_pointer_dispatch(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    # Register right appbar (width 400px; reserved 1520..1920)
    await wsp.register_appbar(edge="right", size=400)

    # Directly dispatch pointer action targeting inside dock area (x=1700, y=500)
    action = Action(
        action_id="act_dock_collision",
        task_id="task_dock_test",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={"x": 1700, "y": 500, "desktop_generation_id": wsp.desktop_generation_id},
    )

    cancel_token = CancellationSource().token
    with pytest.raises(RuntimeError, match="RESERVED_WORKSPACE_COLLISION"):
        await orch._execute_action("sess_test", action, cancel_token)

    assert action.stage == ActionStage.FAILED
    assert action.error is not None
    assert action.error.code == "RESERVED_WORKSPACE_COLLISION"

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
    action = Action(
        action_id="act_stale_gen",
        task_id="task_stale_gen",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={"x": 500, "y": 300, "desktop_generation_id": initial_gen},
    )

    cancel_token = CancellationSource().token
    with pytest.raises(RuntimeError, match="STALE_COORDINATE_CONTEXT"):
        await orch._execute_action("sess_test", action, cancel_token)

    assert action.stage == ActionStage.FAILED
    assert action.error.code == "STALE_COORDINATE_CONTEXT"
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_workspace_out_of_bounds_blocks_pointer_dispatch(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    action = Action(
        action_id="act_oob",
        task_id="task_oob",
        action_type="pointer_move",
        tier=ActionTier.TIER_1_SAFE,
        parameters={"x": -200, "y": 500, "desktop_generation_id": wsp.desktop_generation_id},
    )

    cancel_token = CancellationSource().token
    with pytest.raises(RuntimeError, match="OUT_OF_BOUNDS"):
        await orch._execute_action("sess_test", action, cancel_token)

    assert action.stage == ActionStage.FAILED
    assert action.error.code == "OUT_OF_BOUNDS"
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_human_takeover_preempts_before_pointer_dispatch(target_test_env):
    orch, obs, ptr, wsp, tkv = target_test_env
    await orch.initialize()

    # Trigger human takeover
    await orch.handle_human_takeover(reason="Physical user input detected", source="physical_mouse")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE


    action = Action(
        action_id="act_during_takeover",
        task_id="task_tkv_test",
        action_type="pointer_click",
        tier=ActionTier.TIER_2_CONSTRAINED,
        parameters={"x": 500, "y": 300, "desktop_generation_id": wsp.desktop_generation_id},
    )

    cancel_token = CancellationSource().token
    with pytest.raises(RuntimeError, match="Human takeover is currently active"):
        await orch._execute_action("sess_test", action, cancel_token)


    assert action.stage == ActionStage.FAILED
    assert action.error.code == "HUMAN_TAKEOVER_ACTIVE"
    assert len(ptr.click_history) == 0

    await orch.shutdown()
