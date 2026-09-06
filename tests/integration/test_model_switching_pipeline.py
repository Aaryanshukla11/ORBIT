"""Integration tests for end-to-end model switching pipeline (Milestone M1.9 Step 4)."""

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
    ModelGenerateRequest,
    ModelProviderKind,
)
from orbit.runtime.models.registry import ModelRegistry


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def multi_model_registry() -> ModelRegistry:
    reg = ModelRegistry()
    m1 = ModelDescriptor(
        model_id="mock:pipeline-model-1",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-p1",
        display_name="Pipeline Model 1",
        capabilities={ModelCapability.TEXT_GENERATION},
    )
    m2 = ModelDescriptor(
        model_id="mock:pipeline-model-2",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-p2",
        display_name="Pipeline Model 2",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
    )
    m3 = ModelDescriptor(
        model_id="mock:pipeline-model-3",
        provider=ModelProviderKind.CLOUD_OPENAI,
        provider_model_name="mock-p3",
        display_name="Pipeline Model 3",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.VISION},
    )
    reg._models[m1.model_id] = m1
    reg._models[m2.model_id] = m2
    reg._models[m3.model_id] = m3
    return reg


@pytest.mark.asyncio
async def test_multi_step_model_switching_pipeline(event_bus: EventBus, multi_model_registry: ModelRegistry):
    session_mgr = ModelSessionManager(registry=multi_model_registry, event_bus=event_bus)
    event_log = []

    async def log_event(evt: RuntimeEvent):
        event_log.append(evt)

    event_bus.subscribe(None, log_event)

    # Step 1: Activate M1
    res1 = await session_mgr.activate_model("mock:pipeline-model-1")
    assert res1.is_successful
    assert session_mgr.get_active_generation() == 1

    gen1 = await session_mgr.generate(ModelGenerateRequest(prompt="Hello", expected_generation=1))
    assert gen1.done

    # Step 2: Switch to M2
    res2 = await session_mgr.switch_model("mock:pipeline-model-2")
    assert res2.is_successful
    assert res2.switched
    assert session_mgr.get_active_generation() == 2
    assert session_mgr.get_active_model().model_id == "mock:pipeline-model-2"

    gen2 = await session_mgr.generate(ModelGenerateRequest(prompt="Hello", expected_generation=2))
    assert gen2.done

    # Step 3: Switch to M3
    res3 = await session_mgr.switch_model("mock:pipeline-model-3")
    assert res3.is_successful
    assert res3.switched
    assert session_mgr.get_active_generation() == 3
    assert session_mgr.get_active_model().model_id == "mock:pipeline-model-3"

    # Step 4: Shutdown
    await session_mgr.shutdown()
    assert not session_mgr.is_model_active()
    assert session_mgr.get_active_model() is None
