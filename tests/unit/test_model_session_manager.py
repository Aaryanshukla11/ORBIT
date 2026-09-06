"""Unit tests for ModelSessionManager lifecycle and activation (Milestone M1.9 Step 4)."""

import pytest
import pytest_asyncio

from orbit.contracts.events import EventType, RuntimeEvent
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime.contracts import (
    ActiveModelContext,
    ModelActivationRequest,
    ModelActivationResult,
    ModelActivationStatus,
    ModelRuntimeHealth,
    ModelRuntimeKind,
    ModelRuntimeStatus,
)
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
)
from orbit.runtime.models.registry import ModelRegistry


@pytest.fixture
def test_registry() -> ModelRegistry:
    reg = ModelRegistry()
    desc_a = ModelDescriptor(
        model_id="mock:model-a",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-model-a",
        display_name="Mock Model A",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
        context_window=8192,
    )
    desc_b = ModelDescriptor(
        model_id="mock:model-b",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-model-b",
        display_name="Mock Model B",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.VISION},
        context_window=4096,
    )
    reg._models[desc_a.model_id] = desc_a
    reg._models[desc_b.model_id] = desc_b
    return reg


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.mark.asyncio
async def test_session_manager_initial_state(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)

    assert manager.get_active_model() is None
    assert manager.get_active_context() is None
    assert manager.get_active_generation() == 0
    assert not manager.is_model_active()
    assert manager.get_runtime_status() == ModelRuntimeStatus.STOPPED
    assert await manager.get_runtime_health() is None


@pytest.mark.asyncio
async def test_session_manager_successful_activation(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    emitted_events = []

    async def listener(evt: RuntimeEvent):
        emitted_events.append(evt)

    event_bus.subscribe(None, listener)

    # Activate Model A
    result = await manager.activate_model("mock:model-a")
    assert result.is_successful
    assert result.status == ModelActivationStatus.ACTIVATED
    assert result.generation == 1
    assert result.active_context is not None
    assert result.active_context.model_id == "mock:model-a"
    assert result.active_context.generation == 1
    assert result.active_context.runtime_status == ModelRuntimeStatus.ACTIVE

    # Manager properties
    assert manager.is_model_active()
    assert manager.get_active_generation() == 1
    assert manager.get_runtime_status() == ModelRuntimeStatus.ACTIVE

    # Event emissions
    event_types = [e.event_type for e in emitted_events]
    assert EventType.MODEL_ACTIVATION_STARTED in event_types
    assert EventType.MODEL_ACTIVATING in event_types
    assert EventType.MODEL_ACTIVATED in event_types


@pytest.mark.asyncio
async def test_session_manager_already_active(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    await manager.activate_model("mock:model-a")
    assert manager.get_active_generation() == 1

    # Reactivate same model
    res2 = await manager.activate_model("mock:model-a")
    assert res2.is_successful
    assert res2.status == ModelActivationStatus.ALREADY_ACTIVE
    assert res2.generation == 1  # Generation unchanged
    assert manager.get_active_generation() == 1


@pytest.mark.asyncio
async def test_session_manager_model_not_found(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    result = await manager.activate_model("mock:non-existent")

    assert not result.is_successful
    assert result.status == ModelActivationStatus.MODEL_NOT_FOUND
    assert result.failure_reason == "MODEL_NOT_FOUND"
    assert not manager.is_model_active()
    assert manager.get_active_generation() == 0


@pytest.mark.asyncio
async def test_session_manager_capability_constraint_rejection(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)

    # Model A lacks VISION capability
    req = ModelActivationRequest(
        model_id="mock:model-a",
        required_capabilities={ModelCapability.VISION},
    )
    result = await manager.activate_model(req)
    assert not result.is_successful
    assert result.status == ModelActivationStatus.SWITCH_REJECTED
    assert result.failure_reason == "CAPABILITY_MISMATCH"
    assert not manager.is_model_active()


@pytest.mark.asyncio
async def test_session_manager_shutdown(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    await manager.activate_model("mock:model-a")
    assert manager.is_model_active()

    await manager.shutdown_active_model()
    assert not manager.is_model_active()
    assert manager.get_active_model() is None
    assert manager.get_runtime_status() == ModelRuntimeStatus.STOPPED
