"""Comprehensive M1.6 Production Hardening Regression Suite.

Validates the complete closure of:
1. P1-HARDENING-1: Missing TargetIntent fails closed; legacy synthetic fallback cannot be reached accidentally.
2. P1-HARDENING-2: Direct WebSocket pointer and keyboard commands enforce workspace geometry,
   desktop generation consistency, and human takeover preemption, guaranteeing ZERO OS dispatches on rejection.
"""

import asyncio
import json
import time
from typing import Any, Dict
from unittest.mock import AsyncMock
import pytest
from starlette.testclient import TestClient

from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedElement
from orbit.adapters.registry import CapabilityRegistry
from orbit.config import AdapterMode, RuntimeConfig
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.commands import (
    BaseCommand,
    ClickPointerPayload,
    CommandType,
    MovePointerPayload,
    PointerButtonPayload,
    SubmitTaskPayload,
    TypeTextPayload,
)
from orbit.contracts.events import EventType, RuntimeEvent
from orbit.contracts.runtime import SystemState, TaskStatus
from orbit.gateway.app import create_app
from orbit.gateway.session_manager import SessionManager
from orbit.gateway.websocket_manager import WebSocketConnection, WebSocketManager
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.orchestrator import OrbitOrchestrator


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def hardening_env():
    event_bus = EventBus()
    registry = CapabilityRegistry()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()
    tkv = MockHumanTakeoverAdapter()
    sft = MockSafetyCoordinator()

    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)
    registry.register(CapabilityType.HUMAN_TAKEOVER, tkv)
    registry.register(CapabilityType.SAFETY, sft)

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    session_mgr = SessionManager()
    ws_mgr = WebSocketManager(orchestrator=orch, session_manager=session_mgr, event_bus=event_bus)

    return orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr


# ============================================================================
# P1-HARDENING-1: Missing TargetIntent & Synthetic Isolation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_production_task_missing_target_intent_fails_closed_zero_pointer_dispatches(hardening_env):
    """Requirement 1: Autonomous production task submitted without target intent fails closed with 0 pointer events."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    # Submit task without target_intent and without synthetic dev flags
    task = await orch.submit_task(
        session_id="sess_prod_01",
        prompt="Click submit button without metadata",
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.FAILED
    assert final_task.error is not None
    assert final_task.error.code == "TARGET_INTENT_REQUIRED"
    assert "target_intent" in final_task.error.message.lower()

    # Invariant: ZERO pointer dispatches, ZERO clicks, ZERO synthetic coordinates invented
    assert len(ptr.click_history) == 0
    assert len(ptr.move_history) == 1  # only initial position
    assert len(kbd.typed_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_explicit_synthetic_development_plan_requires_explicit_opt_in(hardening_env):
    """Requirement 2: Synthetic plan executes ONLY when explicitly opted in via metadata."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    # 1. Without flag -> FAILS CLOSED
    task_rejected = await orch.submit_task(
        session_id="sess_dev_reject",
        prompt="Execute dev task without flag",
    )
    for _ in range(50):
        t = await orch.task_manager.get_task(task_rejected.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)
    t_rej = await orch.task_manager.get_task(task_rejected.task_id)
    assert t_rej.status == TaskStatus.FAILED
    assert t_rej.error.code == "TARGET_INTENT_REQUIRED"
    assert len(ptr.click_history) == 0

    # 2. With explicit flag -> ALLOWED for test harness
    task_optin = await orch.submit_task(
        session_id="sess_dev_allowed",
        prompt="Execute dev test with explicit flag",
        context={"is_synthetic_development": True},
    )
    for _ in range(50):
        t = await orch.task_manager.get_task(task_optin.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)
    t_opt = await orch.task_manager.get_task(task_optin.task_id)
    assert t_opt.status == TaskStatus.COMPLETED
    assert len(ptr.click_history) == 1

    await orch.shutdown()


# ============================================================================
# P1-HARDENING-2: WebSocket Direct Pointer Command Security Tests
# ============================================================================

@pytest.mark.asyncio
async def test_websocket_move_pointer_valid_coordinates_accepted(hardening_env):
    """Requirement 3: Valid MOVE_POINTER coordinates within workspace bounds succeed."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    ws_mock = AsyncMock()
    conn = WebSocketConnection("conn_test_01", "sess_ws_01", ws_mock)

    cmd = BaseCommand(command_id="cmd_m1", command_type=CommandType.MOVE_POINTER, session_id="sess_ws_01")
    payload = MovePointerPayload(x=600, y=400)

    await ws_mgr._dispatch_command(conn, cmd, payload)

    assert len(ptr.move_history) >= 2
    assert ptr.move_history[-1].x == 600
    assert ptr.move_history[-1].y == 400

    await orch.shutdown()


@pytest.mark.asyncio
async def test_websocket_click_pointer_valid_coordinates_accepted(hardening_env):
    """Requirement 4: Valid CLICK_POINTER coordinates succeed through workspace validation."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    ws_mock = AsyncMock()
    conn = WebSocketConnection("conn_test_02", "sess_ws_02", ws_mock)

    cmd = BaseCommand(command_id="cmd_c1", command_type=CommandType.CLICK_POINTER, session_id="sess_ws_02")
    payload = ClickPointerPayload(x=700, y=500, button="left", count=1)

    await ws_mgr._dispatch_command(conn, cmd, payload)

    assert len(ptr.click_history) == 1
    assert ptr.click_history[0]["x"] == 700
    assert ptr.click_history[0]["y"] == 500
    assert ptr.click_history[0]["button"] == "left"

    await orch.shutdown()


@pytest.mark.asyncio
async def test_websocket_pointer_reserved_appbar_dock_collision_rejected(hardening_env):
    """Requirement 5: Coordinates inside reserved AppBar dock are rejected with ZERO OS events."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    # Register AppBar docking on the right edge with size 480px (canvas is x: [0..1440), dock: [1440..1920))
    await wsp.register_appbar(edge="right", size=480)

    ws_mock = AsyncMock()
    conn = WebSocketConnection("conn_test_03", "sess_ws_03", ws_mock)

    # 1. MOVE_POINTER into dock (x=1600 is inside dock)
    move_cmd = {
        "command_id": "cmd_mov_dock",
        "command_type": "MOVE_POINTER",
        "session_id": "sess_ws_03",
        "payload": {"x": 1600, "y": 500},
    }
    await ws_mgr._process_inbound_text(conn, json.dumps(move_cmd))

    # Assert error enqueued
    assert not conn.outbound_queue.empty()
    err_json = await conn.outbound_queue.get()
    err_evt = json.loads(err_json)
    assert err_evt["event_type"] == "ERROR"
    assert "RESERVED" in err_evt["payload"]["code"] or "RESERVED" in err_evt["payload"]["message"]

    # ZERO pointer movements to 1600
    assert all(pos.x != 1600 for pos in ptr.move_history)

    # 2. CLICK_POINTER into dock (x=1500)
    click_cmd = {
        "command_id": "cmd_clk_dock",
        "command_type": "CLICK_POINTER",
        "session_id": "sess_ws_03",
        "payload": {"x": 1500, "y": 500},
    }
    await ws_mgr._process_inbound_text(conn, json.dumps(click_cmd))

    assert not conn.outbound_queue.empty()
    err_json = await conn.outbound_queue.get()
    err_evt = json.loads(err_json)
    assert err_evt["event_type"] == "ERROR"
    assert "RESERVED" in err_evt["payload"]["code"] or "RESERVED" in err_evt["payload"]["message"]

    # ZERO clicks in history
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_websocket_pointer_out_of_bounds_rejected(hardening_env):
    """Requirement 6: Out-of-bounds coordinates are rejected with ZERO OS events."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    ws_mock = AsyncMock()
    conn = WebSocketConnection("conn_test_04", "sess_ws_04", ws_mock)

    # Negative coordinates
    move_cmd = {
        "command_id": "cmd_mov_oob",
        "command_type": "MOVE_POINTER",
        "session_id": "sess_ws_04",
        "payload": {"x": -500, "y": -500},
    }
    await ws_mgr._process_inbound_text(conn, json.dumps(move_cmd))

    err_json = await conn.outbound_queue.get()
    err_evt = json.loads(err_json)
    assert err_evt["event_type"] == "ERROR"
    assert "OUT_OF_BOUNDS" in err_evt["payload"]["code"] or "OUT_OF_BOUNDS" in err_evt["payload"]["message"]
    assert all(pos.x >= 0 and pos.y >= 0 for pos in ptr.move_history)

    await orch.shutdown()


@pytest.mark.asyncio
async def test_websocket_pointer_stale_generation_rejected(hardening_env):
    """Requirement 7: Coordinates submitted with stale desktop generation are rejected."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    # Advance generation by registering and unregistering AppBar
    await wsp.register_appbar(edge="right", size=300)
    current_gen = wsp.get_desktop_generation()
    assert current_gen > 0

    ws_mock = AsyncMock()
    conn = WebSocketConnection("conn_test_05", "sess_ws_05", ws_mock)

    # Send move with stale generation 0
    move_cmd = {
        "command_id": "cmd_mov_stale",
        "command_type": "MOVE_POINTER",
        "session_id": "sess_ws_05",
        "payload": {"x": 500, "y": 300, "expected_generation": 0},
    }
    await ws_mgr._process_inbound_text(conn, json.dumps(move_cmd))

    err_json = await conn.outbound_queue.get()
    err_evt = json.loads(err_json)
    assert err_evt["event_type"] == "ERROR"
    assert "STALE" in err_evt["payload"]["code"] or "STALE" in err_evt["payload"]["message"] or "GENERATION" in err_evt["payload"]["message"]
    assert len(ptr.move_history) == 1

    await orch.shutdown()


@pytest.mark.asyncio
async def test_websocket_pointer_and_keyboard_preempted_under_human_takeover(hardening_env):
    """Requirement 8: Direct commands are blocked during active Human Takeover with ZERO OS events."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    # Trigger human takeover
    await orch.handle_human_takeover("Physical user intervention")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    ws_mock = AsyncMock()
    conn = WebSocketConnection("conn_test_06", "sess_ws_06", ws_mock)

    # 1. MOVE_POINTER under takeover
    move_cmd = {
        "command_id": "cmd_mov_tkv",
        "command_type": "MOVE_POINTER",
        "session_id": "sess_ws_06",
        "payload": {"x": 500, "y": 300},
    }
    await ws_mgr._process_inbound_text(conn, json.dumps(move_cmd))
    err_1 = json.loads(await conn.outbound_queue.get())
    assert err_1["event_type"] == "ERROR"
    assert err_1["payload"]["code"] == "HUMAN_TAKEOVER_ACTIVE"

    # 2. CLICK_POINTER under takeover
    click_cmd = {
        "command_id": "cmd_clk_tkv",
        "command_type": "CLICK_POINTER",
        "session_id": "sess_ws_06",
        "payload": {"x": 500, "y": 300},
    }
    await ws_mgr._process_inbound_text(conn, json.dumps(click_cmd))
    err_2 = json.loads(await conn.outbound_queue.get())
    assert err_2["event_type"] == "ERROR"
    assert err_2["payload"]["code"] == "HUMAN_TAKEOVER_ACTIVE"

    # 3. TYPE_TEXT under takeover
    type_cmd = {
        "command_id": "cmd_typ_tkv",
        "command_type": "TYPE_TEXT",
        "session_id": "sess_ws_06",
        "payload": {"text": "Unauthorized input"},
    }
    await ws_mgr._process_inbound_text(conn, json.dumps(type_cmd))
    err_3 = json.loads(await conn.outbound_queue.get())
    assert err_3["event_type"] == "ERROR"
    assert err_3["payload"]["code"] == "HUMAN_TAKEOVER_ACTIVE"

    # Invariant: ZERO OS events dispatched
    assert len(ptr.move_history) == 1
    assert len(ptr.click_history) == 0
    assert len(kbd.typed_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_cancelled_execution_context_causes_zero_os_events(hardening_env):
    """Requirement 9: Cancelled execution tokens preempt dispatch immediately with ZERO OS events."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    intent = {"strategy": "ACCESSIBILITY_ELEMENT", "name": "TargetToCancel"}
    task = await orch.submit_task(
        session_id="sess_cancel_preempt",
        prompt="Cancel immediately",
        context={"target_intent": intent},
    )

    # Cancel immediately
    await orch.cancel_task(task.task_id, reason="Operator preemptive abort")

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.CANCELLED
    assert len(ptr.click_history) == 0
    assert len(ptr.move_history) == 1

    await orch.shutdown()


def _make_snapshot(snapshot_id: str, generation_id: int, elements=None) -> ObservationSnapshot:
    from datetime import datetime, timezone
    from orbit.adapters.observation.snapshot import CoordinateSpace, FreshnessState, ObservationConfidence
    return ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=generation_id,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        detected_elements=elements or [],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
    )


@pytest.mark.asyncio
async def test_production_closed_loop_execution_full_regression(hardening_env):
    """Requirement 10: Closed-loop target-directed execution functions correctly with verified target."""
    orch, obs, ptr, kbd, wsp, tkv, sft, event_bus, ws_mgr = hardening_env
    await orch.initialize()

    el = ObservedElement(
        element_id="btn_submit",
        source="MSAA",
        name="SubmitButton",
        role="Button",
        bounds=BoundingBox(left=500, top=400, width=100, height=40),
        is_focused=False,
    )
    obs.queue_mock_snapshot(_make_snapshot("snap_reg_1", wsp.get_desktop_generation(), elements=[el]))
    obs.queue_mock_snapshot(_make_snapshot("snap_reg_2", wsp.get_desktop_generation(), elements=[el]))

    intent = {
        "strategy": "ACCESSIBILITY_ELEMENT",
        "name": "SubmitButton",
        "expected_outcome": None,
    }

    task = await orch.submit_task(
        session_id="sess_reg_closed_loop",
        prompt="Click submit button",
        context={"target_intent": intent},
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED
    assert len(ptr.click_history) == 1
    # Bounding box is left=500, top=400, width=100, height=40 (x in [500..600], y in [400..440])
    assert 500 <= ptr.click_history[0]["x"] < 600
    assert 400 <= ptr.click_history[0]["y"] < 440
    assert ptr.click_history[0]["button"] == "left"

    await orch.shutdown()
