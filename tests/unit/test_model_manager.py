"""Unit tests for ModelManager (Milestone M1.9 Step 1).

Validates:
- Manager lifecycle
- Model discovery orchestration
- Active model switching and selection
- Transactional rollback invariants on failed model switching
- Health checking and generation dispatch
"""

from __future__ import annotations

from typing import List, Optional
import pytest

from orbit.runtime.models.manager import (
    ModelManager,
    ModelNotFoundError,
    ModelSwitchError,
    ProviderNotFoundError,
    ProviderUnhealthyError,
)
from orbit.runtime.models.models import (
    ModelChatMessage,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.base import ModelProvider


class MockTestProvider(ModelProvider):
    """Deterministic in-memory mock provider for unit testing."""

    def __init__(
        self,
        provider_kind: ModelProviderKind = ModelProviderKind.OLLAMA,
        endpoint: str = "http://127.0.0.1:11434",
        models: Optional[List[ModelDescriptor]] = None,
        health_status: ProviderHealthStatus = ProviderHealthStatus.HEALTHY,
        load_succeeds: bool = True,
    ) -> None:
        self._provider_kind = provider_kind
        self._endpoint = endpoint
        self._models = models or []
        self._health_status = health_status
        self._load_succeeds = load_succeeds
        self.load_calls: List[str] = []
        self.generate_calls: List[dict] = []
        self.chat_calls: List[dict] = []

    @property
    def provider_kind(self) -> ModelProviderKind:
        return self._provider_kind

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self._provider_kind,
            status=self._health_status,
            endpoint=self._endpoint,
            latency_ms=5.0 if self._health_status == ProviderHealthStatus.HEALTHY else None,
            diagnostic_message="Mock health",
        )

    async def discover_models(self) -> List[ModelDescriptor]:
        return list(self._models)

    async def get_model(self, provider_model_name: str) -> Optional[ModelDescriptor]:
        for m in self._models:
            if m.provider_model_name == provider_model_name:
                return m
        return None

    async def get_model_status(self, provider_model_name: str) -> ModelStatus:
        return ModelStatus.AVAILABLE

    async def generate(self, provider_model_name: str, request: ModelGenerateRequest) -> ModelGenerateResponse:
        self.generate_calls.append({"model": provider_model_name, "prompt": request.prompt})
        return ModelGenerateResponse(
            model_id=f"{self._provider_kind.value.lower()}:{provider_model_name}",
            content=f"Generated response for: {request.prompt}",
            done=True,
            total_duration_ms=10.0,
        )

    async def chat(self, provider_model_name: str, request: ModelChatRequest) -> ModelGenerateResponse:
        self.chat_calls.append({"model": provider_model_name, "messages": request.messages})
        return ModelGenerateResponse(
            model_id=f"{self._provider_kind.value.lower()}:{provider_model_name}",
            content="Chat assistant reply",
            done=True,
            total_duration_ms=15.0,
        )

    async def load_model(self, provider_model_name: str) -> bool:
        self.load_calls.append(provider_model_name)
        if not self._load_succeeds:
            raise RuntimeError(f"Simulated load failure for {provider_model_name}")
        return True

    async def unload_model(self, provider_model_name: str) -> bool:
        return True

    async def shutdown(self) -> None:
        pass


@pytest.fixture
def mock_models() -> List[ModelDescriptor]:
    return [
        ModelDescriptor(
            model_id="ollama:qwen2.5:7b",
            provider=ModelProviderKind.OLLAMA,
            provider_model_name="qwen2.5:7b",
            display_name="Qwen 2.5 7B",
            status=ModelStatus.AVAILABLE,
        ),
        ModelDescriptor(
            model_id="ollama:llama3:latest",
            provider=ModelProviderKind.OLLAMA,
            provider_model_name="llama3:latest",
            display_name="LLaMA 3",
            status=ModelStatus.AVAILABLE,
        ),
    ]


@pytest.mark.asyncio
async def test_model_manager_discovery(mock_models: List[ModelDescriptor]):
    """Verify ModelManager discover_models populates registry."""
    provider = MockTestProvider(models=mock_models)
    manager = ModelManager(providers=[provider])

    result = await manager.discover_models()
    assert result.total_discovered == 2
    assert len(result.successful_providers) == 1
    assert result.successful_providers[0] == ModelProviderKind.OLLAMA

    models = await manager.list_models()
    assert len(models) == 2


@pytest.mark.asyncio
async def test_model_manager_set_active_model_success(mock_models: List[ModelDescriptor]):
    """Verify switching active model succeeds and updates status."""
    provider = MockTestProvider(models=mock_models)
    manager = ModelManager(providers=[provider])
    await manager.discover_models()

    assert manager.get_active_model_id() is None

    ok = await manager.set_active_model("ollama:qwen2.5:7b")
    assert ok is True
    assert manager.get_active_model_id() == "ollama:qwen2.5:7b"
    
    active = await manager.get_active_model()
    assert active is not None
    assert active.model_id == "ollama:qwen2.5:7b"
    assert active.status == ModelStatus.LOADED
    assert "qwen2.5:7b" in provider.load_calls


@pytest.mark.asyncio
async def test_model_manager_switch_nonexistent_model_raises(mock_models: List[ModelDescriptor]):
    """Verify switching to nonexistent model raises ModelNotFoundError and leaves active model unchanged."""
    provider = MockTestProvider(models=mock_models)
    manager = ModelManager(providers=[provider])
    await manager.discover_models()
    await manager.set_active_model("ollama:qwen2.5:7b")

    with pytest.raises(ModelNotFoundError):
        await manager.set_active_model("ollama:non_existent_model")

    # Invariant: active model remains qwen2.5:7b
    assert manager.get_active_model_id() == "ollama:qwen2.5:7b"


@pytest.mark.asyncio
async def test_model_manager_switch_unhealthy_provider_raises(mock_models: List[ModelDescriptor]):
    """Verify switching to model on unhealthy provider raises ProviderUnhealthyError with rollback."""
    provider = MockTestProvider(models=mock_models, health_status=ProviderHealthStatus.UNAVAILABLE)
    manager = ModelManager(providers=[provider])
    await manager.registry.register_models(mock_models)

    with pytest.raises(ProviderUnhealthyError):
        await manager.set_active_model("ollama:qwen2.5:7b")

    assert manager.get_active_model_id() is None


@pytest.mark.asyncio
async def test_model_manager_switch_load_failure_rolls_back(mock_models: List[ModelDescriptor]):
    """Verify load failure during switch triggers rollback to previous active model."""
    provider = MockTestProvider(models=mock_models, load_succeeds=True)
    manager = ModelManager(providers=[provider])
    await manager.discover_models()

    # Step 1: Successfully activate Model A
    await manager.set_active_model("ollama:qwen2.5:7b")
    assert manager.get_active_model_id() == "ollama:qwen2.5:7b"

    # Step 2: Configure provider to fail loading for Model B
    provider._load_succeeds = False

    with pytest.raises(ModelSwitchError):
        await manager.set_active_model("ollama:llama3:latest")

    # Transactional Invariant: previous active model remains active!
    assert manager.get_active_model_id() == "ollama:qwen2.5:7b"
    active = await manager.get_active_model()
    assert active is not None
    assert active.model_id == "ollama:qwen2.5:7b"


@pytest.mark.asyncio
async def test_model_manager_generate_and_chat(mock_models: List[ModelDescriptor]):
    """Verify text generation and chat routing through active model."""
    provider = MockTestProvider(models=mock_models)
    manager = ModelManager(providers=[provider])
    await manager.discover_models()
    await manager.set_active_model("ollama:qwen2.5:7b")

    # Generate
    gen_resp = await manager.generate("Explain ORBIT runtime architecture")
    assert "Generated response for: Explain ORBIT" in gen_resp.content
    assert len(provider.generate_calls) == 1

    # Chat
    chat_resp = await manager.chat([
        ModelChatMessage(role="user", content="Hello ORBIT"),
    ])
    assert chat_resp.content == "Chat assistant reply"
    assert len(provider.chat_calls) == 1
