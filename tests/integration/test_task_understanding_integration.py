"""Integration tests for ORBIT Task Understanding with Orchestrator lifecycle (M1.8 Step 1)."""

import asyncio
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
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.task_understanding import TaskGoal, TaskUnderstandingStatus
from orbit.runtime.targeting.models import TargetIntent, TargetStrategy


def _make_snapshot(snapshot_id: str, generation_id: int, elements=None) -> ObservationSnapshot:
    from datetime import datetime, timezone
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

    return orch, obs, ptr, kbd, wsp, orch.task_manager


@pytest.mark.asyncio
async def test_orchestrator_understand_task_api(orchestrator_env):
    """Test direct orchestrator.understand_task() method."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    clicks_before = len(ptr.click_history)
    moves_before = len(ptr.move_history)
    typed_before = len(kbd.typed_history)

    result = orch.understand_task("Open Notepad and type Hello World")
    assert result.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(result.intents) == 2
    assert result.intents[0].goal == TaskGoal.OPEN_APPLICATION
    assert result.intents[1].goal == TaskGoal.WRITE_TEXT
    assert result.intents[1].constraints.content == "Hello World"

    # Assert zero OS interaction occurred during understanding
    assert len(ptr.click_history) == clicks_before
    assert len(ptr.move_history) == moves_before
    assert len(kbd.typed_history) == typed_before

    await orch.shutdown()


@pytest.mark.asyncio
async def test_natural_language_submission_attaches_understanding_and_fails_closed(orchestrator_env):
    """Test natural language task submitted without target_intent attaches understanding and halts safely."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    clicks_before = len(ptr.click_history)
    typed_before = len(kbd.typed_history)

    task = await orch.submit_task(
        session_id="sess_nl_1",
        prompt="Open Notepad and type 'Safe Test'",
        context={"understand_only": True},
    )

    # Wait for task to reach terminal state
    for _ in range(50):
        t = await task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED

    # Verify task understanding was attached to metadata
    assert "task_understanding" in final_task.metadata
    understanding_data = final_task.metadata["task_understanding"]
    assert understanding_data["status"] == TaskUnderstandingStatus.UNDERSTOOD.value
    assert len(understanding_data["intents"]) == 2

    # Verify fail-closed safety: ZERO pointer clicks or keyboard dispatches
    assert len(ptr.click_history) == clicks_before
    assert len(kbd.typed_history) == typed_before

    await orch.shutdown()


@pytest.mark.asyncio
async def test_ambiguous_task_submission_records_ambiguity_zero_dispatches(orchestrator_env):
    """Test ambiguous prompt submission attaches AMBIGUOUS status and halts with zero OS events."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    clicks_before = len(ptr.click_history)
    typed_before = len(kbd.typed_history)

    task = await orch.submit_task(
        session_id="sess_ambig",
        prompt="Open it and click the button",
    )

    for _ in range(50):
        t = await task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED
    assert "task_understanding" in final_task.metadata
    understanding_data = final_task.metadata["task_understanding"]
    assert understanding_data["status"] in {
        TaskUnderstandingStatus.AMBIGUOUS.value,
        TaskUnderstandingStatus.PARTIALLY_UNDERSTOOD.value,
    }
    assert len(understanding_data["unresolved_constraints"]) > 0

    assert len(ptr.click_history) == clicks_before
    assert len(kbd.typed_history) == typed_before

    await orch.shutdown()


@pytest.mark.asyncio
async def test_backward_compatibility_structured_target_intent(orchestrator_env):
    """Test that existing M1.7 structured TargetIntent tasks continue to execute cleanly."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    el_pre = ObservedElement(
        element_id="btn_submit",
        source="UI_AUTOMATION",
        name="SubmitButton",
        role="push button",
        bounds=BoundingBox(left=200, top=150, width=100, height=50),
        coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
        confidence=ObservationConfidence.CONFIRMED,
        is_focused=False,
    )
    el_post = ObservedElement(
        element_id="btn_submit",
        source="UI_AUTOMATION",
        name="SubmitButton",
        role="push button",
        bounds=BoundingBox(left=200, top=150, width=100, height=50),
        coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
        confidence=ObservationConfidence.CONFIRMED,
        is_focused=True,
    )

    obs.queue_mock_snapshot(_make_snapshot("snap_1", wsp.desktop_generation_id, elements=[el_pre]))
    obs.queue_mock_snapshot(_make_snapshot("snap_2", wsp.desktop_generation_id, elements=[el_post]))

    intent = {
        "strategy": "ACCESSIBILITY_ELEMENT",
        "name": "SubmitButton",
        "expected_outcome": {
            "outcome_type": "ELEMENT_STATE_CHANGED",
            "strategy": "ACCESSIBILITY_STATE_CHANGE",
            "target_id": "btn_submit",
            "expected_property": "is_focused",
            "expected_value": True,
        },
    }

    task = await orch.submit_task(
        session_id="sess_compat",
        prompt="Click SubmitButton",
        context={
            "target_intent": intent,
            "action_type": "pointer_click",
        },
    )

    for _ in range(50):
        t = await task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED
    assert len(ptr.click_history) == 1

    await orch.shutdown()
