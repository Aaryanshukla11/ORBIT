"""Integration tests for production observation within the OrbitOrchestrator runtime lifecycle."""

import asyncio
import pytest

from orbit.adapters.factory import create_capability_registry
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.contracts.events import EventType
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.gateway.session_manager import SessionManager
from orbit.runtime.task_manager import TaskManager


@pytest.mark.asyncio
async def test_orchestrator_with_production_observation_lifecycle():
    """Test OrbitOrchestrator executing tasks with real ProductionObservationAdapter."""
    # Configure production observation with mock actuation capabilities
    config = RuntimeConfig(
        adapter_mode=AdapterMode.MOCK,
        capability_overrides={
            CapabilityType.OBSERVATION: AdapterMode.PRODUCTION,
        },
    )

    event_bus = EventBus()
    registry = create_capability_registry(config)

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )
    task_manager = orchestrator.task_manager

    # Verify adapter registration
    obs_adapter = registry.resolve(CapabilityType.OBSERVATION)
    assert isinstance(obs_adapter, ProductionObservationAdapter)
    assert obs_adapter.adapter_mode == AdapterMode.PRODUCTION

    await orchestrator.initialize()
    assert obs_adapter.is_ready is True

    emitted_events = []
    event_bus.subscribe(None, lambda evt: emitted_events.append(evt))

    # Submit task requiring observation
    task = await orchestrator.submit_task(
        session_id="sess_prod_obs_01",
        prompt="Inspect desktop and perform action",
    )
    assert task.task_id is not None

    # Wait for completion
    for _ in range(50):
        t = await task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED

    # Verify real observation events were emitted
    event_types = [e.event_type for e in emitted_events]
    assert EventType.OBSERVATION_FRAME in event_types

    obs_events = [e for e in emitted_events if e.event_type == EventType.OBSERVATION_FRAME]
    assert len(obs_events) > 0
    frame_payload = obs_events[0].payload
    assert "frame_id" in frame_payload
    assert frame_payload["frame_id"].startswith("frame_")

    await orchestrator.shutdown()
    assert obs_adapter.is_ready is False
