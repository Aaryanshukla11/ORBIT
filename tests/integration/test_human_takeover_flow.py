"""Integration tests for human takeover detection, preemption and release."""

import asyncio
import pytest

from orbit.contracts.events import EventType
from orbit.contracts.runtime import SystemState, TaskStatus
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.mark.asyncio
async def test_human_takeover_preemption(
    orchestrator: OrbitOrchestrator,
    mock_takeover,
    mock_safety,
    event_bus,
):
    await orchestrator.initialize()
    assert orchestrator.system_state == SystemState.IDLE

    emitted_events = []
    event_bus.subscribe(None, lambda evt: emitted_events.append(evt))

    # Trigger physical human takeover via mock hook
    mock_takeover.trigger_takeover()

    # Allow event loop to process takeover handler
    await asyncio.sleep(0.05)

    assert orchestrator.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE
    assert mock_safety.stop_count >= 1

    # Verify takeover event was emitted
    takeover_events = [e for e in emitted_events if e.event_type == EventType.TAKEOVER_EVENT]
    assert len(takeover_events) >= 1
    assert takeover_events[-1].payload["is_active"] is True

    # Release takeover
    released = await orchestrator.release_takeover()
    assert released is True
    assert orchestrator.system_state == SystemState.IDLE

    await orchestrator.shutdown()
