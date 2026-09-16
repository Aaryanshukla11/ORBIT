"""Integration tests for Human Takeover preemption across OrbitOrchestrator and capabilities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.mocks import MockKeyboardAdapter, MockObservationAdapter, MockPointerAdapter
from orbit.adapters.production.production_safety import ProductionSafetyCoordinator
from orbit.adapters.takeover.adapter import ProductionHumanTakeoverAdapter
from orbit.adapters.takeover.classifier import (
    InputDevice,
    InputEventType,
    InputSource,
    TakeoverEvidence,
)
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.events import EventType, RuntimeEvent
from orbit.contracts.runtime import SystemState, TaskStatus
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.mark.asyncio
async def test_takeover_preempts_active_execution_and_sanitizes():
    event_bus = EventBus()
    registry = CapabilityRegistry()

    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    sft = ProductionSafetyCoordinator(registry=registry)
    tkv = ProductionHumanTakeoverAdapter(enable_live_hooks=False)

    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.SAFETY, sft)
    registry.register(CapabilityType.HUMAN_TAKEOVER, tkv)

    orchestrator = OrbitOrchestrator(event_bus=event_bus, registry=registry)

    # Initialize capabilities manually for mock/test setup
    await obs.initialize()
    await ptr.initialize()
    await kbd.initialize()
    await sft.initialize()
    orchestrator._system_sm.transition_to(SystemState.IDLE)

    events = []
    event_bus.subscribe(None, lambda e: events.append(e))

    # Hold a synthetic mouse button and keyboard key to verify sanitization
    await ptr.press_down("left")
    await kbd.press_key("ctrl")
    assert ptr.button_states.get("left") is True
    assert kbd._key_states.get("ctrl") is True

    # Submit a task
    task = await orchestrator.submit_task("sess-1", "Test human takeover preemption")
    assert task.status == TaskStatus.CREATED

    # Trigger human takeover
    evidence = TakeoverEvidence(
        event_id=1,
        timestamp_ns=12345,
        device=InputDevice.MOUSE,
        event_type=InputEventType.LBUTTON_DOWN,
        source=InputSource.USER_PHYSICAL,
        should_trigger_takeover=True,
        reason="Physical mouse button interaction",
    )

    await orchestrator.handle_human_takeover(reason=evidence.reason, source="physical_mouse")

    # 1. System state is HUMAN_TAKEOVER_ACTIVE
    assert orchestrator.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    # 2. Hardware state is sanitized
    assert ptr.button_states.get("left") is False
    assert len(kbd._key_states) == 0

    # 3. Active task cancellation source was triggered
    cancel_src = orchestrator._active_cancellation_sources.get(task.task_id)
    assert cancel_src is not None
    assert cancel_src.is_cancelled is True

    # 4. TAKEOVER_EVENT was emitted
    tkv_events = [e for e in events if e.event_type == EventType.TAKEOVER_EVENT]
    assert len(tkv_events) >= 1
    assert tkv_events[0].payload["is_active"] is True

    # 5. New task submission fails while in takeover state
    new_task = await orchestrator.submit_task("sess-1", "Should fail due to active takeover")
    # Wait for execution to fail
    t_status = None
    for _ in range(25):
        await asyncio.sleep(0.02)
        t_status = await orchestrator.task_manager.get_task(new_task.task_id)
        if t_status and t_status.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            break
    assert t_status is not None
    assert t_status.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)

    # 6. Release takeover returns system to IDLE
    released = await orchestrator.release_takeover()
    assert released is True
    assert orchestrator.system_state == SystemState.IDLE
