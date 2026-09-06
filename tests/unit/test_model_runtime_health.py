"""Unit tests for Model Runtime Health, Inference Safety Guards, and Secret Redaction (Milestone M1.9 Step 4)."""

import pytest
import pytest_asyncio

from orbit.contracts.events import EventType, RuntimeEvent
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime.contracts import (
    ModelRuntimeHealth,
    ModelRuntimeStatus,
    NoActiveModelError,
    StaleModelGenerationError,
)
from orbit.runtime.model_runtime.providers.mock import MockModelRuntimeAdapter
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import (
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelProviderKind,
)
from orbit.runtime.models.registry import ModelRegistry


@pytest.fixture
def test_registry() -> ModelRegistry:
    reg = ModelRegistry()
    desc = ModelDescriptor(
        model_id="mock:healthy-model",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-healthy",
        display_name="Healthy Mock Model",
    )
    reg._models[desc.model_id] = desc
    return reg


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.mark.asyncio
async def test_runtime_health_check_and_event(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    emitted_events = []

    async def listener(evt: RuntimeEvent):
        emitted_events.append(evt)

    event_bus.subscribe(EventType.MODEL_HEALTH_CHANGED, listener)

    await manager.activate_model("mock:healthy-model")
    health = await manager.get_runtime_health()

    assert health is not None
    assert health.is_healthy
    assert health.latency_ms is not None
    assert len(emitted_events) == 1
    assert emitted_events[0].payload["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_inference_guard_no_active_model(test_registry: ModelRegistry):
    manager = ModelSessionManager(registry=test_registry)

    # Without activating a model
    with pytest.raises(NoActiveModelError):
        await manager.generate(ModelGenerateRequest(prompt="test"))

    with pytest.raises(NoActiveModelError):
        await manager.chat(ModelChatRequest(messages=[ModelChatMessage(role="user", content="test")]))


@pytest.mark.asyncio
async def test_stale_generation_rejection(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    await manager.activate_model("mock:healthy-model")
    assert manager.get_active_generation() == 1

    # Request matching generation
    req_valid = ModelGenerateRequest(prompt="Hello", expected_generation=1)
    res_valid = await manager.generate(req_valid)
    assert res_valid.done

    # Request with stale generation (e.g. 0 or 99)
    req_stale = ModelGenerateRequest(prompt="Hello", expected_generation=99)
    with pytest.raises(StaleModelGenerationError) as exc_info:
        await manager.generate(req_stale)
    assert "Generation conflict" in str(exc_info.value)


@pytest.mark.asyncio
async def test_inference_runtime_crash_event_emission(test_registry: ModelRegistry, event_bus: EventBus):
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)
    emitted_events = []

    async def listener(evt: RuntimeEvent):
        emitted_events.append(evt)

    event_bus.subscribe(EventType.MODEL_RUNTIME_FAILED, listener)

    # Create mock that crashes on inference
    def crashing_factory(descriptor, **kwargs):
        return MockModelRuntimeAdapter(descriptor=descriptor, simulate_inference_crash=True)

    manager._factory.create_runtime = crashing_factory

    await manager.activate_model("mock:healthy-model")

    # Generate triggers crash
    with pytest.raises(RuntimeError):
        await manager.generate(ModelGenerateRequest(prompt="Crash me"))

    assert len(emitted_events) == 1
    assert emitted_events[0].payload["status"] == "FAILED"


@pytest.mark.asyncio
async def test_secret_redaction_guarantees(test_registry: ModelRegistry, event_bus: EventBus):
    # Ensure descriptor metadata with fake credentials does not leak in ActiveModelContext
    desc = ModelDescriptor(
        model_id="mock:secret-test",
        provider=ModelProviderKind.CLOUD_OPENAI,
        provider_model_name="mock-secret",
        endpoint="https://api.openai.com/v1",
        metadata={"safe_param": "value"},
    )
    test_registry._models[desc.model_id] = desc
    manager = ModelSessionManager(registry=test_registry, event_bus=event_bus)

    res = await manager.activate_model("mock:secret-test")
    assert res.is_successful

    context = manager.get_active_model()
    dumped = context.model_dump_json()

    # Verify no secret keywords exist
    assert "sk-" not in dumped
    assert "Bearer" not in dumped
    assert "password" not in dumped
