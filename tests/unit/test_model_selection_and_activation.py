"""Comprehensive Unit Tests for Model Selection, Activation, and Safe Switching (Milestone M1.9 Step 3).

Covers:
1. Select discovered healthy model.
2. Reject unknown model.
3. Reject unavailable model.
4. Reject unreachable runtime.
5. Reject cloud model with missing credentials.
6. Activate valid local model.
7. Activate valid cloud configuration.
8. Prevent invalid lifecycle transitions.
9. Switch A -> B successfully.
10. Preserve A when B activation fails.
11. Preserve A when B throws an exception.
12. Reject concurrent inconsistent activation.
13. Generation increments after switch.
14. Stale generation detection.
15. No active model behavior.
16. Capability metadata validation.
17. Event emission correctness.
18. Secret redaction.
19. Runtime adapter interface consistency.
20. Health degradation handling.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from orbit.contracts.events import EventType, RuntimeEvent
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.models.adapters import (
    AdapterCapabilityStatus,
    CloudRuntimeAdapter,
    LocalRuntimeAdapter,
    ModelRuntimeAdapter,
    create_runtime_adapter,
)
from orbit.runtime.models.manager import (
    CapabilityMismatchError,
    CloudAuthRequiredError,
    ModelManager,
    ModelNotFoundError,
    ModelSwitchError,
    ModelUnavailableError,
    NoActiveModelError,
    ProviderNotFoundError,
    ProviderUnhealthyError,
    StaleModelGenerationError,
)
from orbit.runtime.models.models import (
    ActiveModelSession,
    CloudAuthStatus,
    CloudProviderKind,
    ModelActivationRequest,
    ModelActivationResult,
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSelectionRequest,
    ModelSelectionResult,
    ModelSelectionStatus,
    ModelSessionStatus,
    ModelSourceType,
    ModelStatus,
    ModelSwitchPolicy,
    ModelSwitchResult,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry
from orbit.runtime.model_providers.base import ModelProvider
from orbit.runtime.model_providers.cloud import CloudModelProvider


class MockTestProvider(ModelProvider):
    """Configurable mock provider for testing unit scenarios."""

    def __init__(
        self,
        provider_kind: ModelProviderKind = ModelProviderKind.OLLAMA,
        endpoint: str = "http://127.0.0.1:11434",
        health_status: ProviderHealthStatus = ProviderHealthStatus.HEALTHY,
        load_success: bool = True,
        generate_response: str = "mock completion output",
    ) -> None:
        self._kind = provider_kind
        self._endpoint = endpoint
        self._health_status = health_status
        self._load_success = load_success
        self._generate_response = generate_response
        self.load_calls: List[str] = []
        self.generate_calls: List[str] = []

    @property
    def provider_kind(self) -> ModelProviderKind:
        return self._kind

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self._kind,
            status=self._health_status,
            endpoint=self._endpoint,
            latency_ms=12.5 if self._health_status == ProviderHealthStatus.HEALTHY else None,
            diagnostic_message="Mock health diagnostic",
        )

    async def discover_models(self) -> List[ModelDescriptor]:
        return []

    async def get_model(self, provider_model_name: str) -> Optional[ModelDescriptor]:
        return None

    async def get_model_status(self, provider_model_name: str) -> ModelStatus:
        return ModelStatus.READY

    async def generate(self, provider_model_name: str, request: ModelGenerateRequest) -> ModelGenerateResponse:
        self.generate_calls.append(provider_model_name)
        return ModelGenerateResponse(
            model_id=f"{self._kind.value}:{provider_model_name}",
            content=self._generate_response,
            done=True,
            total_duration_ms=45.0,
        )

    async def chat(self, provider_model_name: str, request: ModelChatRequest) -> ModelGenerateResponse:
        return ModelGenerateResponse(
            model_id=f"{self._kind.value}:{provider_model_name}",
            content=self._generate_response,
            done=True,
            total_duration_ms=50.0,
        )

    async def load_model(self, provider_model_name: str) -> bool:
        self.load_calls.append(provider_model_name)
        if not self._load_success:
            raise RuntimeError(f"Simulated load failure for {provider_model_name}")
        return True

    async def unload_model(self, provider_model_name: str) -> bool:
        return True

    async def shutdown(self) -> None:
        pass


def make_test_descriptor(
    model_id: str,
    provider: ModelProviderKind = ModelProviderKind.OLLAMA,
    status: ModelStatus = ModelStatus.READY,
    capabilities: Optional[Set[ModelCapability]] = None,
) -> ModelDescriptor:
    provider_name = model_id.split(":", 1)[1] if ":" in model_id else model_id
    return ModelDescriptor(
        model_id=model_id,
        provider=provider,
        provider_model_name=provider_name,
        display_name=provider_name,
        status=status,
        capabilities=capabilities or {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
        context_window=8192,
        parameter_size="7B",
    )


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture
def mock_ollama() -> MockTestProvider:
    return MockTestProvider(provider_kind=ModelProviderKind.OLLAMA)


@pytest.fixture
def model_manager(registry: ModelRegistry, mock_ollama: MockTestProvider, event_bus: EventBus) -> ModelManager:
    manager = ModelManager(
        registry=registry,
        providers=[mock_ollama],
        event_bus=event_bus,
    )
    return manager


# -----------------------------------------------------------------------------
# 1. Select Discovered Healthy Model
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_select_discovered_healthy_model(model_manager: ModelManager, registry: ModelRegistry):
    m = make_test_descriptor("ollama:qwen2.5:latest", status=ModelStatus.READY)
    await registry.register_model(m)

    res = await model_manager.select_model("ollama:qwen2.5:latest")
    assert res.is_successful is True
    assert res.status == ModelSelectionStatus.SELECTED
    assert res.descriptor is not None
    assert res.descriptor.model_id == "ollama:qwen2.5:latest"


# -----------------------------------------------------------------------------
# 2. Reject Unknown Model
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reject_unknown_model(model_manager: ModelManager):
    res = await model_manager.select_model("ollama:nonexistent:latest")
    assert res.is_successful is False
    assert res.status == ModelSelectionStatus.MODEL_NOT_FOUND
    assert res.failure_reason == "MODEL_NOT_FOUND"


# -----------------------------------------------------------------------------
# 3. Reject Unavailable Model
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reject_unavailable_model(model_manager: ModelManager, registry: ModelRegistry):
    m = make_test_descriptor("ollama:offline-model:7b", status=ModelStatus.UNAVAILABLE)
    await registry.register_model(m)

    res = await model_manager.select_model("ollama:offline-model:7b")
    assert res.is_successful is False
    assert res.status == ModelSelectionStatus.MODEL_UNAVAILABLE
    assert res.failure_reason == "MODEL_UNAVAILABLE"


# -----------------------------------------------------------------------------
# 4. Reject Unreachable Runtime
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reject_unreachable_runtime(registry: ModelRegistry, event_bus: EventBus):
    unhealthy_provider = MockTestProvider(
        provider_kind=ModelProviderKind.LM_STUDIO,
        health_status=ProviderHealthStatus.UNAVAILABLE,
    )
    mgr = ModelManager(registry=registry, providers=[unhealthy_provider], event_bus=event_bus)

    m = make_test_descriptor("lm_studio:mistral:7b", provider=ModelProviderKind.LM_STUDIO, status=ModelStatus.READY)
    await registry.register_model(m)

    # Selection checks provider registration, activation checks health probe
    act_res = await mgr.activate_model("lm_studio:mistral:7b")
    assert act_res.is_successful is False
    assert act_res.failure_reason == "RUNTIME_UNREACHABLE"


# -----------------------------------------------------------------------------
# 5. Reject Cloud Model with Missing Credentials
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reject_cloud_model_missing_credentials(registry: ModelRegistry, event_bus: EventBus):
    cloud_p = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key=None,  # Not configured
    )
    mgr = ModelManager(registry=registry, cloud_providers=[cloud_p], event_bus=event_bus)

    m = make_test_descriptor("openai:gpt-4o", provider=ModelProviderKind.CLOUD_OPENAI, status=ModelStatus.READY)
    await registry.register_model(m)

    res = await mgr.select_model("openai:gpt-4o")
    assert res.is_successful is False
    assert res.status == ModelSelectionStatus.AUTH_NOT_CONFIGURED
    assert res.failure_reason == "AUTH_NOT_CONFIGURED"


# -----------------------------------------------------------------------------
# 6. Activate Valid Local Model
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_activate_valid_local_model(model_manager: ModelManager, registry: ModelRegistry):
    m = make_test_descriptor("ollama:qwen2.5:latest", status=ModelStatus.READY)
    await registry.register_model(m)

    res = await model_manager.activate_model("ollama:qwen2.5:latest")
    assert res.is_successful is True
    assert res.generation >= 1
    assert res.active_session is not None
    assert res.active_session.active_model_id == "ollama:qwen2.5:latest"
    assert model_manager.is_model_active() is True
    assert model_manager.get_active_model_id() == "ollama:qwen2.5:latest"


# -----------------------------------------------------------------------------
# 7. Activate Valid Cloud Configuration
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_activate_valid_cloud_configuration(registry: ModelRegistry, event_bus: EventBus):
    cloud_p = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-test-valid-mock-key",
    )
    mgr = ModelManager(registry=registry, cloud_providers=[cloud_p], event_bus=event_bus)

    m = make_test_descriptor("openai:gpt-4o", provider=ModelProviderKind.CLOUD_OPENAI, status=ModelStatus.READY)
    await registry.register_model(m)

    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        res = await mgr.activate_model("openai:gpt-4o")
        assert res.is_successful is True
        assert res.active_session is not None
        assert res.active_session.active_model_id == "openai:gpt-4o"
        assert res.active_session.provider_id == ModelProviderKind.CLOUD_OPENAI


# -----------------------------------------------------------------------------
# 8. Prevent Invalid Lifecycle Transitions
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prevent_invalid_lifecycle_transitions(model_manager: ModelManager, registry: ModelRegistry):
    m = make_test_descriptor("ollama:failed-model:7b", status=ModelStatus.INCOMPATIBLE)
    await registry.register_model(m)

    res = await model_manager.select_model("ollama:failed-model:7b")
    assert res.is_successful is False
    assert res.status == ModelSelectionStatus.MODEL_INCOMPATIBLE


# -----------------------------------------------------------------------------
# 9. Switch A -> B Successfully
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_switch_a_to_b_successfully(model_manager: ModelManager, registry: ModelRegistry):
    mA = make_test_descriptor("ollama:model-a:7b", status=ModelStatus.READY)
    mB = make_test_descriptor("ollama:model-b:7b", status=ModelStatus.READY)
    await registry.register_model(mA)
    await registry.register_model(mB)

    # Activate A
    res_a = await model_manager.activate_model("ollama:model-a:7b")
    assert res_a.is_successful is True
    gen_a = res_a.generation

    # Switch to B
    switch_res = await model_manager.switch_model("ollama:model-b:7b")
    assert switch_res.is_successful is True
    assert switch_res.switched is True
    assert switch_res.previous_model_id == "ollama:model-a:7b"
    assert switch_res.active_model_id == "ollama:model-b:7b"
    assert switch_res.generation == gen_a + 1
    assert model_manager.get_active_model_id() == "ollama:model-b:7b"


# -----------------------------------------------------------------------------
# 10. Preserve A When B Activation Fails (Safe Rollback)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_preserve_a_when_b_fails(model_manager: ModelManager, registry: ModelRegistry):
    mA = make_test_descriptor("ollama:model-a:7b", status=ModelStatus.READY)
    await registry.register_model(mA)

    # Activate A
    res_a = await model_manager.activate_model("ollama:model-a:7b")
    assert res_a.is_successful is True
    gen_a = res_a.generation

    # Attempt switch to unknown model B
    switch_res = await model_manager.switch_model("ollama:nonexistent-b:7b")
    assert switch_res.is_successful is False
    assert switch_res.switched is False

    # Invariant: Model A must still be active and unchanged
    assert model_manager.get_active_model_id() == "ollama:model-a:7b"
    assert model_manager.get_active_generation() == gen_a
    assert model_manager.is_model_active() is True


# -----------------------------------------------------------------------------
# 11. Preserve A When B Throws Exception During Preparation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_preserve_a_when_b_throws_exception(registry: ModelRegistry, event_bus: EventBus):
    class FlakyProvider(MockTestProvider):
        async def load_model(self, provider_model_name: str) -> bool:
            if provider_model_name == "crash-model":
                raise RuntimeError("Hardware allocation crashed!")
            return True

    flaky_p = FlakyProvider(provider_kind=ModelProviderKind.OLLAMA)
    mgr = ModelManager(registry=registry, providers=[flaky_p], event_bus=event_bus)

    mA = make_test_descriptor("ollama:stable-model:7b", status=ModelStatus.READY)
    mB = make_test_descriptor("ollama:crash-model", status=ModelStatus.READY)
    await registry.register_model(mA)
    await registry.register_model(mB)

    # Activate A
    act_a = await mgr.activate_model("ollama:stable-model:7b")
    assert act_a.is_successful is True
    gen_a = act_a.generation

    # Switch to B (should fail gracefully and roll back)
    switch_res = await mgr.switch_model("ollama:crash-model")
    assert switch_res.is_successful is False
    assert switch_res.failure_reason == "MODEL_NOT_READY"

    # Invariant: A remains active
    assert mgr.get_active_model_id() == "ollama:stable-model:7b"
    assert mgr.get_active_generation() == gen_a


# -----------------------------------------------------------------------------
# 12. Reject Concurrent Inconsistent Activation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reject_concurrent_inconsistent_activation(model_manager: ModelManager, registry: ModelRegistry):
    mA = make_test_descriptor("ollama:concurrent-a:7b", status=ModelStatus.READY)
    mB = make_test_descriptor("ollama:concurrent-b:7b", status=ModelStatus.READY)
    await registry.register_model(mA)
    await registry.register_model(mB)

    # Run two switches simultaneously
    results = await asyncio.gather(
        model_manager.switch_model("ollama:concurrent-a:7b"),
        model_manager.switch_model("ollama:concurrent-b:7b"),
        return_exceptions=False,
    )

    # Both must resolve cleanly without tearing or partial state
    active_id = model_manager.get_active_model_id()
    assert active_id in ("ollama:concurrent-a:7b", "ollama:concurrent-b:7b")
    assert model_manager.get_active_session() is not None
    assert model_manager.get_active_session().active_model_id == active_id


# -----------------------------------------------------------------------------
# 13. Generation Increments After Switch
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generation_increments_after_switch(model_manager: ModelManager, registry: ModelRegistry):
    m1 = make_test_descriptor("ollama:model-1", status=ModelStatus.READY)
    m2 = make_test_descriptor("ollama:model-2", status=ModelStatus.READY)
    m3 = make_test_descriptor("ollama:model-3", status=ModelStatus.READY)
    await registry.register_model(m1)
    await registry.register_model(m2)
    await registry.register_model(m3)

    act1 = await model_manager.activate_model("ollama:model-1")
    g1 = act1.generation

    sw2 = await model_manager.switch_model("ollama:model-2")
    g2 = sw2.generation
    assert g2 == g1 + 1

    sw3 = await model_manager.switch_model("ollama:model-3")
    g3 = sw3.generation
    assert g3 == g2 + 1


# -----------------------------------------------------------------------------
# 14. Stale Generation Detection
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_generation_detection(model_manager: ModelManager, registry: ModelRegistry):
    m1 = make_test_descriptor("ollama:model-1", status=ModelStatus.READY)
    m2 = make_test_descriptor("ollama:model-2", status=ModelStatus.READY)
    await registry.register_model(m1)
    await registry.register_model(m2)

    act1 = await model_manager.activate_model("ollama:model-1")
    old_gen = act1.generation

    # Valid inference under old generation
    resp = await model_manager.generate("Hello", expected_generation=old_gen)
    assert resp.content == "mock completion output"

    # Switch model to advance generation
    await model_manager.switch_model("ollama:model-2")

    # Stale inference request must be rejected
    with pytest.raises(StaleModelGenerationError) as exc_info:
        await model_manager.generate("Hello after switch", expected_generation=old_gen)
    assert "Stale model generation" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 15. No Active Model Behavior
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_active_model_behavior(model_manager: ModelManager):
    assert model_manager.is_model_active() is False
    assert model_manager.get_active_session() is None

    with pytest.raises(NoActiveModelError):
        await model_manager.generate("Test prompt")

    with pytest.raises(NoActiveModelError):
        await model_manager.chat([ModelChatMessage(role="user", content="Hi")])


# -----------------------------------------------------------------------------
# 16. Capability Metadata Validation & Mismatch Rejection
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_capability_metadata_validation(model_manager: ModelManager, registry: ModelRegistry):
    # Text-only model
    text_model = make_test_descriptor(
        "ollama:text-only:7b",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
        status=ModelStatus.READY,
    )
    await registry.register_model(text_model)

    # Request requiring VISION
    req = ModelSelectionRequest(
        model_id="ollama:text-only:7b",
        required_capabilities={ModelCapability.VISION},
    )
    res = await model_manager.select_model(req)
    assert res.is_successful is False
    assert res.status == ModelSelectionStatus.CAPABILITY_MISMATCH
    assert res.failure_reason == "CAPABILITY_MISMATCH"


# -----------------------------------------------------------------------------
# 17. Event Emission Correctness
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_event_emission_correctness(model_manager: ModelManager, registry: ModelRegistry, event_bus: EventBus):
    captured_events: List[RuntimeEvent] = []

    def record_evt(e: RuntimeEvent):
        captured_events.append(e)

    for et in EventType:
        event_bus.subscribe(et, record_evt)

    m1 = make_test_descriptor("ollama:evt-model-1", status=ModelStatus.READY)
    m2 = make_test_descriptor("ollama:evt-model-2", status=ModelStatus.READY)
    await registry.register_model(m1)
    await registry.register_model(m2)

    await model_manager.activate_model("ollama:evt-model-1")
    await model_manager.switch_model("ollama:evt-model-2")
    await model_manager.deactivate_active_model()

    event_types = [e.event_type for e in captured_events]
    assert EventType.MODEL_SELECTION_REQUESTED in event_types
    assert EventType.MODEL_ACTIVATION_STARTED in event_types
    assert EventType.MODEL_ACTIVATED in event_types
    assert EventType.MODEL_SWITCH_STARTED in event_types
    assert EventType.MODEL_SWITCH_SUCCEEDED in event_types
    assert EventType.MODEL_DEACTIVATED in event_types


# -----------------------------------------------------------------------------
# 18. Secret Redaction
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_secret_redaction(registry: ModelRegistry, event_bus: EventBus):
    secret_key = "sk-super-secret-production-token-12345"
    cloud_p = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key=secret_key,
    )
    captured_events: List[RuntimeEvent] = []

    def record_evt(e: RuntimeEvent):
        captured_events.append(e)

    for et in EventType:
        event_bus.subscribe(et, record_evt)

    mgr = ModelManager(registry=registry, cloud_providers=[cloud_p], event_bus=event_bus)
    m = make_test_descriptor("openai:gpt-4o", provider=ModelProviderKind.CLOUD_OPENAI, status=ModelStatus.READY)
    await registry.register_model(m)

    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        await mgr.activate_model("openai:gpt-4o")

    # Invariant: Secret key MUST NOT appear anywhere in events, payloads, or session
    session = mgr.get_active_session()
    assert session is not None
    session_dump = session.model_dump_json()
    assert secret_key not in session_dump

    for evt in captured_events:
        evt_json = evt.model_dump_json()
        assert secret_key not in evt_json


# -----------------------------------------------------------------------------
# 19. Runtime Adapter Interface Consistency
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_runtime_adapter_interface_consistency(mock_ollama: MockTestProvider):
    desc = make_test_descriptor("ollama:qwen2.5:latest")
    adapter = create_runtime_adapter(desc, mock_ollama)

    assert isinstance(adapter, LocalRuntimeAdapter)
    assert adapter.model_id == "ollama:qwen2.5:latest"
    assert adapter.get_model_info() == desc

    # Test generate
    gen_resp = await adapter.generate(ModelGenerateRequest(prompt="Test prompt"))
    assert gen_resp.content == "mock completion output"

    # Test chat
    chat_resp = await adapter.chat(ModelChatRequest(messages=[ModelChatMessage(role="user", content="Hi")]))
    assert chat_resp.content == "mock completion output"

    # Test health check
    health = await adapter.health_check()
    assert health.status == ProviderHealthStatus.HEALTHY

    # Test cancel request
    cancel_ok = await adapter.cancel_request("req_123")
    assert cancel_ok is True


# -----------------------------------------------------------------------------
# 20. Health Degradation Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_health_degradation_handling(model_manager: ModelManager, registry: ModelRegistry, mock_ollama: MockTestProvider):
    desc = make_test_descriptor("ollama:degraded-test:7b")
    await registry.register_model(desc)

    await model_manager.activate_model("ollama:degraded-test:7b")
    adapter = model_manager.get_active_runtime()
    assert adapter is not None
    assert adapter.get_capability_status() == AdapterCapabilityStatus.SUPPORTED

    # Provider health degrades
    mock_ollama._health_status = ProviderHealthStatus.DEGRADED
    health = await model_manager.get_model_health("ollama:degraded-test:7b")
    assert health.status == ProviderHealthStatus.DEGRADED

    # Adapter reflects degraded/partially supported status
    cap_status = adapter.get_capability_status()
    assert cap_status == AdapterCapabilityStatus.PARTIALLY_SUPPORTED
