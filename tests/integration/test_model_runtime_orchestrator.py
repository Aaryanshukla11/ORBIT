"""Integration tests for OrbitOrchestrator and ModelSessionManager coordination (Milestone M1.9 Step 4)."""

import asyncio
import pytest
import pytest_asyncio

from orbit.contracts.events import EventType, RuntimeEvent
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime import (
    ActiveModelContext,
    ModelActivationStatus,
    ModelSessionManager,
    ModelSwitchPolicy,
)
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
)
from orbit.runtime.models.registry import ModelRegistry
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def test_registry() -> ModelRegistry:
    reg = ModelRegistry()
    desc_a = ModelDescriptor(
        model_id="mock:orchestrator-model-a",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-orch-a",
        display_name="Orchestrator Model A",
        capabilities={ModelCapability.TEXT_GENERATION},
    )
    desc_b = ModelDescriptor(
        model_id="mock:orchestrator-model-b",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-orch-b",
        display_name="Orchestrator Model B",
        capabilities={ModelCapability.TEXT_GENERATION},
    )
    reg._models[desc_a.model_id] = desc_a
    reg._models[desc_b.model_id] = desc_b
    return reg


@pytest.mark.asyncio
async def test_orchestrator_model_session_manager_wiring(event_bus: EventBus, test_registry: ModelRegistry):
    session_mgr = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        model_session_manager=session_mgr,
    )
    await orchestrator.initialize()

    # Initial state
    assert orchestrator.model_session_manager is session_mgr
    assert orchestrator.active_model_context is None
    assert not orchestrator.is_task_executing

    # Activate Model A via session manager
    act_res = await session_mgr.activate_model("mock:orchestrator-model-a")
    assert act_res.is_successful

    # Query through orchestrator
    active_ctx = orchestrator.active_model_context
    assert active_ctx is not None
    assert active_ctx.model_id == "mock:orchestrator-model-a"
    assert active_ctx.generation == 1

    await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_task_execution_prevents_unsafe_switch(event_bus: EventBus, test_registry: ModelRegistry):
    session_mgr = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        model_session_manager=session_mgr,
    )
    await orchestrator.initialize()

    # Activate Model A
    await session_mgr.activate_model("mock:orchestrator-model-a")
    assert orchestrator.active_model_context.model_id == "mock:orchestrator-model-a"

    # Simulate an active background task in orchestrator
    dummy_task = asyncio.create_task(asyncio.sleep(0.5))
    orchestrator._active_execution_tasks["task-123"] = dummy_task

    # Now orchestrator reports is_task_executing = True
    assert orchestrator.is_task_executing

    # Attempt model switch with default policy
    switch_res = await session_mgr.switch_model("mock:orchestrator-model-b")
    assert not switch_res.is_successful
    assert switch_res.status == ModelActivationStatus.ACTIVE_TASK_CONFLICT
    assert switch_res.failure_reason == "ACTIVE_TASK_CONFLICT"

    # Invariant: Active model context remains Model A
    assert orchestrator.active_model_context.model_id == "mock:orchestrator-model-a"
    assert orchestrator.active_model_context.generation == 1

    # Cleanup dummy task
    dummy_task.cancel()
    orchestrator._active_execution_tasks.clear()
    await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_deterministic_execution_without_active_model(event_bus: EventBus):
    orchestrator = OrbitOrchestrator(event_bus=event_bus)
    await orchestrator.initialize()

    # No model active
    assert orchestrator.active_model_context is None

    # Deterministic capabilities (targeting, verification, etc.) are available
    assert orchestrator.target_locator is not None
    assert orchestrator.action_verifier is not None
    assert orchestrator.system_state.value == "IDLE"

    await orchestrator.shutdown()
