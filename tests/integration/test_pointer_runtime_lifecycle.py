"""Integration tests for production pointer execution inside OrbitOrchestrator runtime lifecycle."""

import asyncio
import pytest

from orbit.adapters.factory import create_capability_registry
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.contracts.events import EventType
from orbit.contracts.runtime import Action, ActionStage, ActionTier
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_pointer_movement_action_lifecycle():
    """Test OrbitOrchestrator executing a pointer_move action with ProductionPointerAdapter."""
    config = RuntimeConfig(
        adapter_mode=AdapterMode.MOCK,
        capability_overrides={
            CapabilityType.OBSERVATION: AdapterMode.PRODUCTION,
            CapabilityType.POINTER: AdapterMode.PRODUCTION,
        },
    )

    event_bus = EventBus()
    registry = create_capability_registry(config)

    # Use simulated readback for deterministic integration execution
    ptr_adapter = registry.resolve(CapabilityType.POINTER)
    assert isinstance(ptr_adapter, ProductionPointerAdapter)
    ptr_adapter._cursorpos_override = lambda: (500, 300)
    ptr_adapter._sendinput_override = lambda n, ptr, sz: 1

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )

    await orchestrator.initialize()
    assert ptr_adapter.is_ready is True

    emitted_events = []
    event_bus.subscribe(None, lambda evt: emitted_events.append(evt))

    # Execute a single pointer_move action
    action = Action(
        action_id="act_move_01",
        task_id="task_move_test",
        action_type="pointer_move",
        tier=ActionTier.TIER_1_SAFE,
        parameters={"x": 500, "y": 300},
    )

    cancel_source = CancellationSource()
    await orchestrator._execute_action(
        session_id="sess_move_01",
        action=action,
        cancel_token=cancel_source.token,
    )

    assert action.stage == ActionStage.COMPLETED
    assert action.verification is not None
    assert action.verification.status.value == "PASSED"

    # Verify action stage events were emitted
    action_events = [e for e in emitted_events if e.event_type == EventType.ACTION_STAGE_CHANGED]
    stages = [e.payload["stage"] for e in action_events]
    assert ActionStage.DISPATCHED.value in stages
    assert ActionStage.EXECUTING.value in stages
    assert ActionStage.VERIFYING.value in stages
    assert ActionStage.COMPLETED.value in stages

    health = await ptr_adapter.get_health()
    assert health.details["action_counter"]["verified_movements"] >= 1

    await orchestrator.shutdown()
    assert ptr_adapter.is_ready is False
