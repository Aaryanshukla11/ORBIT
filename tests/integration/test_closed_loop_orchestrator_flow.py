"""Integration tests for ORBIT M1.6 Step 3 Closed-Loop Execution flow via OrbitOrchestrator."""

import asyncio
from datetime import datetime, timezone
import pytest
import time

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
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.execution import ExecutionPolicy
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.targeting import TargetIntent, TargetStrategy
from orbit.runtime.verification import ExpectedOutcome, ExpectedOutcomeType, VerificationStrategy


def _make_snapshot(snapshot_id: str, generation_id: int, elements=None) -> ObservationSnapshot:
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


@pytest.fixture
def orchestrator_env():
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
    return orch, obs, ptr, wsp, tkv, bus


@pytest.mark.asyncio
async def test_orchestrator_closed_loop_verified_task_flow(orchestrator_env):
    """Verify task submission with target_intent runs through closed-loop engine and completes."""
    orch, obs, ptr, wsp, tkv, bus = orchestrator_env
    await orch.initialize()

    el_pre = ObservedElement(
        element_id="btn_confirm",
        source="MSAA",
        name="Confirm",
        role="Button",
        bounds=BoundingBox(left=500, top=400, width=120, height=45),
        is_focused=False,
    )
    el_post = ObservedElement(
        element_id="btn_confirm",
        source="MSAA",
        name="Confirm",
        role="Button",
        bounds=BoundingBox(left=500, top=400, width=120, height=45),
        is_focused=True,
    )

    obs.queue_mock_snapshot(_make_snapshot("snap_1", wsp.desktop_generation_id, elements=[el_pre]))
    obs.queue_mock_snapshot(_make_snapshot("snap_2", wsp.desktop_generation_id, elements=[el_post]))

    intent = {
        "strategy": "ACCESSIBILITY_ELEMENT",
        "name": "Confirm",
        "expected_outcome": {
            "outcome_type": "ELEMENT_STATE_CHANGED",
            "strategy": "ACCESSIBILITY_STATE_CHANGE",
            "target_id": "btn_confirm",
            "expected_property": "is_focused",
            "expected_value": True,
        },
    }

    task = await orch.submit_task(
        session_id="sess_loop_01",
        prompt="Confirm transaction",
        context={"target_intent": intent},
    )

    # Wait for completion
    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED
    assert "execution_result" in final_task.metadata
    exec_res = final_task.metadata["execution_result"]
    assert exec_res["is_success"] is True
    assert exec_res["total_attempts"] == 1
    assert len(ptr.click_history) == 1

    await orch.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_closed_loop_retry_and_recovery_flow(orchestrator_env):
    """Verify task recovers from failed verification and succeeds on attempt 2."""
    orch, obs, ptr, wsp, tkv, bus = orchestrator_env
    await orch.initialize()

    # Attempt 1: pre (unfocused) -> post (unfocused) -> Verification fails
    # Attempt 2: pre (unfocused) -> post (focused) -> Verification succeeds
    el_unfocused = ObservedElement(element_id="btn_retry", source="MSAA", name="RetryBtn", role="Button", bounds=BoundingBox(left=300, top=300, width=90, height=40), is_focused=False)
    el_focused = ObservedElement(element_id="btn_retry", source="MSAA", name="RetryBtn", role="Button", bounds=BoundingBox(left=300, top=300, width=90, height=40), is_focused=True)

    obs.queue_mock_snapshot(_make_snapshot("s1", wsp.desktop_generation_id, elements=[el_unfocused]))
    obs.queue_mock_snapshot(_make_snapshot("s2", wsp.desktop_generation_id, elements=[el_unfocused]))
    obs.queue_mock_snapshot(_make_snapshot("s3", wsp.desktop_generation_id, elements=[el_unfocused]))
    obs.queue_mock_snapshot(_make_snapshot("s4", wsp.desktop_generation_id, elements=[el_focused]))

    intent = {
        "strategy": "ACCESSIBILITY_ELEMENT",
        "name": "RetryBtn",
        "expected_outcome": {
            "outcome_type": "ELEMENT_STATE_CHANGED",
            "strategy": "ACCESSIBILITY_STATE_CHANGE",
            "target_id": "btn_retry",
            "expected_property": "is_focused",
            "expected_value": True,
        },
    }

    policy = {"max_total_attempts": 3, "max_verification_retries": 2, "retry_backoff_base_ms": 5.0}

    task = await orch.submit_task(
        session_id="sess_loop_retry",
        prompt="Click retry button",
        context={"target_intent": intent, "execution_policy": policy},
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED
    exec_res = final_task.metadata["execution_result"]
    assert exec_res["is_success"] is True
    assert exec_res["total_attempts"] == 2
    assert exec_res["total_recoveries"] == 1
    assert len(ptr.click_history) == 2

    await orch.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_closed_loop_takeover_preemption(orchestrator_env):
    """Verify human takeover preempts closed-loop task execution safely."""
    orch, obs, ptr, wsp, tkv, bus = orchestrator_env
    await orch.initialize()

    el = ObservedElement(element_id="btn_t", source="MSAA", name="T", role="Button", bounds=BoundingBox(left=100, top=100, width=50, height=20))
    obs.mock_snapshot = _make_snapshot("snap_t", wsp.desktop_generation_id, elements=[el])

    # Trigger human takeover
    tkv.trigger_takeover()

    intent = {"strategy": "ACCESSIBILITY_ELEMENT", "name": "T"}

    task = await orch.submit_task(
        session_id="sess_takeover",
        prompt="Task under takeover",
        context={"target_intent": intent},
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_closed_loop_cancellation(orchestrator_env):
    """Verify cancellation terminates closed-loop execution."""
    orch, obs, ptr, wsp, tkv, bus = orchestrator_env
    await orch.initialize()

    el = ObservedElement(element_id="btn_c", source="MSAA", name="CancelMe", role="Button", bounds=BoundingBox(left=100, top=100, width=50, height=20))
    obs.mock_snapshot = _make_snapshot("snap_c", wsp.desktop_generation_id, elements=[el])

    intent = {"strategy": "ACCESSIBILITY_ELEMENT", "name": "CancelMe"}

    task = await orch.submit_task(
        session_id="sess_cancel",
        prompt="Task to cancel",
        context={"target_intent": intent},
    )

    # Immediately cancel task
    await orch.cancel_task(task.task_id, reason="Operator cancel")

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.CANCELLED

    await orch.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_synthetic_legacy_plan_compatibility(orchestrator_env):
    """Verify non-target tasks still execute through legacy synthetic plan without regression."""
    orch, obs, ptr, wsp, tkv, bus = orchestrator_env
    await orch.initialize()

    task = await orch.submit_task(
        session_id="sess_legacy",
        prompt="Legacy synthetic plan task",
        context={"is_synthetic_development": True},
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED
    assert len(ptr.click_history) == 1
    assert ptr.click_history[0]["x"] == 500
    assert ptr.click_history[0]["y"] == 300

    await orch.shutdown()
