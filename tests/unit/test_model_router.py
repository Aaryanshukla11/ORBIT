"""Unit tests for Hybrid ModelRouter in ORBIT."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import (
    ActiveModelContext,
    ModelActivationStatus,
    ModelNotFoundError,
    ModelRuntimeHealth,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    NoActiveModelError,
    RuntimeInitializationResult,
)
from orbit.runtime.model_runtime.router import (
    ModelRouter,
    ModelRoutingTier,
    PrivacyPolicy,
    RoutingPolicy,
)
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import (
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
)


class DummyRuntime(BaseModelRuntime):
    def __init__(self, descriptor: ModelDescriptor):
        super().__init__(descriptor)
        self._status = ModelRuntimeStatus.READY

    @property
    def runtime_kind(self) -> ModelRuntimeKind:
        return ModelRuntimeKind.LOCAL if self.descriptor.source_type == ModelSourceType.LOCAL_RUNTIME else ModelRuntimeKind.REMOTE

    async def initialize(self, timeout_seconds: float = 30.0, preload_weights: bool = True) -> RuntimeInitializationResult:
        self._status = ModelRuntimeStatus.READY
        return RuntimeInitializationResult(
            is_success=True,
            model_id=self.model_id,
            status=ModelRuntimeStatus.READY,
        )

    async def health_check(self) -> ModelRuntimeHealth:
        return ModelRuntimeHealth(model_id=self.model_id, status=ModelRuntimeStatus.READY, is_healthy=True)

    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        return ModelGenerateResponse(model_id=self.model_id, content=f"Generated from {self.model_id}: {request.prompt}")

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        return ModelGenerateResponse(model_id=self.model_id, content=f"Chat response from {self.model_id}")

    async def shutdown(self) -> None:
        self._status = ModelRuntimeStatus.STOPPED


@pytest.fixture
def mock_session_manager():
    sm = MagicMock(spec=ModelSessionManager)
    
    local_text_desc = ModelDescriptor(
        model_id="ollama:qwen2.5:7b",
        provider_model_name="qwen2.5:7b",
        display_name="Qwen 2.5 7B",
        provider=ModelProviderKind.OLLAMA,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        status=ModelStatus.READY,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
    )
    
    local_vision_desc = ModelDescriptor(
        model_id="ollama:llava:7b",
        provider_model_name="llava:7b",
        display_name="LLaVA 7B",
        provider=ModelProviderKind.OLLAMA,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        status=ModelStatus.READY,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION},
    )
    
    cloud_vision_desc = ModelDescriptor(
        model_id="openai:gpt-4o",
        provider_model_name="gpt-4o",
        display_name="GPT-4o",
        provider=ModelProviderKind.CLOUD_OPENAI,
        source_type=ModelSourceType.CLOUD_PROVIDER,
        status=ModelStatus.READY,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING},
    )

    runtimes = {
        "ollama:qwen2.5:7b": DummyRuntime(local_text_desc),
        "ollama:llava:7b": DummyRuntime(local_vision_desc),
        "openai:gpt-4o": DummyRuntime(cloud_vision_desc),
    }

    async def _list_all():
        return [local_text_desc, local_vision_desc, cloud_vision_desc]

    async def _get_or_create(model_id: str):
        if model_id in runtimes:
            return runtimes[model_id]
        raise ModelNotFoundError(f"Model {model_id} not found")

    sm.list_all_descriptors = AsyncMock(side_effect=_list_all)
    sm.get_or_create_runtime = AsyncMock(side_effect=_get_or_create)
    sm.get_active_runtime = MagicMock(return_value=runtimes["ollama:qwen2.5:7b"])
    return sm


@pytest.mark.asyncio
async def test_model_router_default_resolves_active(mock_session_manager):
    router = ModelRouter(session_manager=mock_session_manager)
    runtime = await router.resolve_runtime()
    assert runtime.model_id == "ollama:qwen2.5:7b"


@pytest.mark.asyncio
async def test_model_router_routes_vision_to_local_when_prefer_local(mock_session_manager):
    router = ModelRouter(session_manager=mock_session_manager)
    policy = RoutingPolicy(
        required_capabilities={ModelCapability.VISION},
        tier=ModelRoutingTier.PREFER_LOCAL,
    )
    runtime = await router.resolve_runtime(policy)
    assert runtime.model_id == "ollama:llava:7b"


@pytest.mark.asyncio
async def test_model_router_routes_vision_to_cloud_when_performance_tier(mock_session_manager):
    router = ModelRouter(session_manager=mock_session_manager)
    policy = RoutingPolicy(
        required_capabilities={ModelCapability.VISION},
        tier=ModelRoutingTier.PERFORMANCE_CLOUD,
    )
    runtime = await router.resolve_runtime(policy)
    assert runtime.model_id == "openai:gpt-4o"


@pytest.mark.asyncio
async def test_model_router_privacy_strictly_local_rejects_cloud(mock_session_manager):
    router = ModelRouter(session_manager=mock_session_manager)
    policy = RoutingPolicy(
        required_capabilities={ModelCapability.TOOL_CALLING},
        privacy=PrivacyPolicy(strictly_local=True, allow_cloud_transfer=False),
        fallback_enabled=False,
    )
    with pytest.raises(NoActiveModelError):
        await router.resolve_runtime(policy)


@pytest.mark.asyncio
async def test_model_router_generate_and_chat_dispatch(mock_session_manager):
    router = ModelRouter(session_manager=mock_session_manager)
    gen_resp = await router.generate(ModelGenerateRequest(prompt="Hello ORBIT"))
    assert "Hello ORBIT" in gen_resp.content

    chat_resp = await router.chat(ModelChatRequest(messages=[ModelChatMessage(role="user", content="Hi")]))
    assert "Chat response" in chat_resp.content
    assert len(router.get_routing_history()) >= 2
