"""Integration tests for production pointer execution inside ORBIT runtime lifecycle."""

import asyncio
import pytest

from orbit.adapters.factory import create_capability_registry
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_pointer_movement_action_lifecycle():
    """Test executing a pointer action through canonical PrimitiveExecutionController with ProductionPointerAdapter."""
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

    # Execute a single pointer move action via canonical controller
    primitive_action = AbstractAction(
        action_id="act_move_01",
        action_type=AbstractActionType.CLICK,
        parameters={"button": "none"},
        target=SemanticTarget(name="test_target", role="point"),
        expected_effect="Move pointer to (500, 300)",
    )
    obj = StructuredObjective(
        raw_prompt="Move pointer",
        user_goal="Move pointer to (500, 300)",
        end_condition="pointer_moved",
    )
    pre_obs = CurrentStateObservation()
    cancel_source = CancellationSource()

    async def mock_grounding(target, obs):
        return (500, 300)

    post_obs = CurrentStateObservation(
        observation_id="obs_post_move_01",
        perceived_elements_count=1,
    )
    async def mock_observe(objective):
        return post_obs

    res = await orchestrator.primitive_controller.execute_primitive(
        action=primitive_action,
        pre_observation=pre_obs,
        objective=obj,
        grounding_fn=mock_grounding,
        observe_fn=mock_observe,
        cancel_token=cancel_source.token,
    )

    assert res.execution_outcome.dispatch_success is True
    assert res.execution_outcome.expected_effect_observed is True

    health = await ptr_adapter.get_health()
    assert health.details["action_counter"]["verified_movements"] >= 1

    await orchestrator.shutdown()
    assert ptr_adapter.is_ready is False
