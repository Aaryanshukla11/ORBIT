"""Unit tests for BaseModelRuntime and provider adapters (Milestone M1.9 Step 4)."""

import pytest
import pytest_asyncio

from orbit.runtime.model_runtime.contracts import (
    ModelRuntimeCapability,
    ModelRuntimeHealth,
    ModelRuntimeInfo,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    RuntimeInitializationResult,
)
from orbit.runtime.model_runtime.factory import ModelRuntimeFactory, create_model_runtime
from orbit.runtime.model_runtime.providers.local import OllamaRuntimeAdapter
from orbit.runtime.model_runtime.providers.mock import MockModelRuntimeAdapter
from orbit.runtime.model_runtime.providers.remote import OpenAICompatibleRuntimeAdapter
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelChatRequest,
    ModelChatMessage,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
)


@pytest.fixture
def mock_descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        model_id="mock:test-model",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-model",
        display_name="Mock Test Model",
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT},
        context_window=4096,
        parameter_size="7B",
        quantization="Q4_K_M",
    )


@pytest.mark.asyncio
async def test_mock_runtime_lazy_initialization(mock_descriptor: ModelDescriptor):
    runtime = MockModelRuntimeAdapter(descriptor=mock_descriptor)
    # Lazy: should start UNINITIALIZED
    assert runtime.status == ModelRuntimeStatus.UNINITIALIZED
    assert not runtime.is_initialized
    assert runtime.model_id == "mock:test-model"

    # Info snapshot
    info = runtime.info
    assert info.model_id == "mock:test-model"
    assert info.status == ModelRuntimeStatus.UNINITIALIZED
    assert ModelCapability.TEXT_GENERATION in info.capabilities

    # Initialize
    res = await runtime.initialize()
    assert res.is_success
    assert res.status == ModelRuntimeStatus.READY
    assert runtime.is_initialized
    assert runtime.status == ModelRuntimeStatus.READY


@pytest.mark.asyncio
async def test_mock_runtime_inference_and_chat(mock_descriptor: ModelDescriptor):
    runtime = MockModelRuntimeAdapter(descriptor=mock_descriptor, default_response_text="Hello ORBIT")
    await runtime.initialize()

    # Generate
    gen_req = ModelGenerateRequest(prompt="Say hello")
    gen_resp = await runtime.generate(gen_req)
    assert gen_resp.content == "Hello ORBIT"
    assert gen_resp.done
    assert len(runtime.generated_requests) == 1

    # Chat
    chat_req = ModelChatRequest(
        messages=[ModelChatMessage(role="user", content="Hi!")]
    )
    chat_resp = await runtime.chat(chat_req)
    assert chat_resp.content == "Hello ORBIT"
    assert len(runtime.chat_requests) == 1

    # Shutdown
    await runtime.shutdown()
    assert runtime.status == ModelRuntimeStatus.STOPPED
    assert runtime.shutdown_called


@pytest.mark.asyncio
async def test_mock_runtime_simulated_init_failure(mock_descriptor: ModelDescriptor):
    runtime = MockModelRuntimeAdapter(
        descriptor=mock_descriptor,
        simulate_init_failure=True,
        init_failure_reason="GPU out of memory",
    )
    res = await runtime.initialize()
    assert not res.is_success
    assert res.status == ModelRuntimeStatus.FAILED
    assert "GPU out of memory" in (res.error_message or "")
    assert not runtime.is_initialized


@pytest.mark.asyncio
async def test_model_runtime_factory_resolution():
    factory = ModelRuntimeFactory()

    # Ollama descriptor
    ollama_desc = ModelDescriptor(
        model_id="ollama:qwen2.5:latest",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="qwen2.5:latest",
    )
    r1 = factory.create_runtime(ollama_desc)
    assert isinstance(r1, OllamaRuntimeAdapter)
    assert r1.runtime_kind == ModelRuntimeKind.LOCAL

    # Cloud descriptor
    cloud_desc = ModelDescriptor(
        model_id="cloud:gpt-4o",
        provider=ModelProviderKind.CLOUD_OPENAI,
        provider_model_name="gpt-4o",
        endpoint="https://api.openai.com/v1",
    )
    r2 = factory.create_runtime(cloud_desc)
    assert isinstance(r2, OpenAICompatibleRuntimeAdapter)
    assert r2.runtime_kind == ModelRuntimeKind.REMOTE

    # Mock descriptor
    mock_desc = ModelDescriptor(
        model_id="mock:demo",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="mock-demo",
    )
    r3 = factory.create_runtime(mock_desc)
    assert isinstance(r3, MockModelRuntimeAdapter)
