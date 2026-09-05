"""Integration tests for orchestrator task execution pipeline."""

import asyncio
import pytest

from orbit.contracts.events import EventType, RuntimeEvent
from orbit.contracts.runtime import TaskStatus
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_task_execution_flow(
    orchestrator: OrbitOrchestrator,
    event_bus,
    mock_pointer,
    mock_keyboard,
    mock_observation,
):
    await orchestrator.initialize()

    emitted_events = []
    event_bus.subscribe(None, lambda evt: emitted_events.append(evt))

    task = await orchestrator.submit_task(
        session_id="sess_exec_01",
        prompt="Click search bar and type query",
    )
    assert task.task_id is not None

    # Wait for task completion
    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED

    # Verify mock capabilities were invoked
    assert len(mock_pointer.click_history) > 0
    assert len(mock_keyboard.typed_history) > 0
    assert mock_observation.capture_count > 0

    # Verify emitted events
    event_types = [e.event_type for e in emitted_events]
    assert EventType.TASK_STATE_CHANGED in event_types
    assert EventType.OBSERVATION_FRAME in event_types
    assert EventType.PLAN_UPDATED in event_types
    assert EventType.ACTION_STAGE_CHANGED in event_types

    await orchestrator.shutdown()
