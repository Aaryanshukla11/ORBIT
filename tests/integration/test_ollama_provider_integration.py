"""Integration tests for OllamaProvider with realistic HTTP responses (Milestone M1.9 Step 1).

Validates:
- Real Ollama API response parsing (/api/tags, /api/version, /api/generate, /api/chat)
- Parameter size, quantization, context length, and capabilities extraction
- HTTP error codes and timeout recovery
"""

from __future__ import annotations

import json
import httpx
import pytest

from orbit.runtime.models.models import (
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelGenerateRequest,
    ModelProviderKind,
    ModelStatus,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.ollama import (
    OllamaModelNotFoundError,
    OllamaProvider,
    OllamaProviderError,
    OllamaUnavailableError,
)

SAMPLE_TAGS_RESPONSE = {
    "models": [
        {
            "name": "qwen2.5:latest",
            "model": "qwen2.5:latest",
            "modified_at": "2026-08-30T15:03:52.5331466+05:30",
            "size": 4683087332,
            "digest": "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e",
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": "qwen2",
                "families": ["qwen2"],
                "parameter_size": "7.6B",
                "quantization_level": "Q4_K_M",
                "context_length": 32768,
                "embedding_length": 3584,
            },
            "capabilities": ["completion", "tools"],
        },
        {
            "name": "llama3.2-vision:latest",
            "model": "llama3.2-vision:latest",
            "modified_at": "2026-08-29T01:42:26.1708541+05:30",
            "size": 7816589186,
            "digest": "6f2f9757ae97e8a3f8ea33d6adb2b11d93d9a35bef277cd2c0b1b5af8e8d0b1e",
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": "mllama",
                "families": ["mllama"],
                "parameter_size": "10.7B",
                "quantization_level": "Q4_K_M",
                "context_length": 131072,
                "embedding_length": 4096,
            },
            "capabilities": ["vision", "completion"],
        },
    ]
}

SAMPLE_VERSION_RESPONSE = {"version": "0.3.14"}

SAMPLE_GENERATE_RESPONSE = {
    "model": "qwen2.5:latest",
    "created_at": "2026-09-07T00:00:00.000Z",
    "response": "ORBIT autonomous execution verified.",
    "done": True,
    "total_duration": 450000000,  # 450ms
    "load_duration": 50000000,
    "prompt_eval_count": 12,
    "eval_count": 18,
}

SAMPLE_CHAT_RESPONSE = {
    "model": "qwen2.5:latest",
    "created_at": "2026-09-07T00:00:00.000Z",
    "message": {
        "role": "assistant",
        "content": "Hello! I am ready to assist with desktop tasks.",
    },
    "done": True,
    "total_duration": 320000000,  # 320ms
    "prompt_eval_count": 15,
    "eval_count": 22,
}


def mock_transport_handler(request: httpx.Request) -> httpx.Response:
    url_path = request.url.path
    if url_path == "/api/version":
        return httpx.Response(200, json=SAMPLE_VERSION_RESPONSE)
    elif url_path == "/api/tags":
        return httpx.Response(200, json=SAMPLE_TAGS_RESPONSE)
    elif url_path == "/api/generate":
        body = json.loads(request.content.decode("utf-8"))
        if body.get("model") == "nonexistent":
            return httpx.Response(404, json={"error": "model 'nonexistent' not found"})
        return httpx.Response(200, json=SAMPLE_GENERATE_RESPONSE)
    elif url_path == "/api/chat":
        return httpx.Response(200, json=SAMPLE_CHAT_RESPONSE)
    return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def mock_ollama_client() -> httpx.AsyncClient:
    transport = httpx.MockTransport(mock_transport_handler)
    return httpx.AsyncClient(base_url="http://mock-ollama:11434", transport=transport)


@pytest.mark.asyncio
async def test_ollama_provider_health_check_success(mock_ollama_client: httpx.AsyncClient):
    """Verify Ollama health check parses version and records healthy status."""
    provider = OllamaProvider(endpoint="http://mock-ollama:11434", client=mock_ollama_client)
    health = await provider.health_check()

    assert health.status == ProviderHealthStatus.HEALTHY
    assert health.version_info == "Ollama v0.3.14"
    assert health.latency_ms is not None
    assert health.provider == ModelProviderKind.OLLAMA


@pytest.mark.asyncio
async def test_ollama_provider_discover_models(mock_ollama_client: httpx.AsyncClient):
    """Verify Ollama discover_models accurately parses models and metadata."""
    provider = OllamaProvider(endpoint="http://mock-ollama:11434", client=mock_ollama_client)
    models = await provider.discover_models()

    assert len(models) == 2

    # Model 1: Qwen 2.5
    qwen = next(m for m in models if m.provider_model_name == "qwen2.5:latest")
    assert qwen.model_id == "ollama:qwen2.5:latest"
    assert qwen.parameter_size == "7.6B"
    assert qwen.quantization_level == "Q4_K_M"
    assert qwen.context_window == 32768
    assert qwen.family == "qwen2"
    assert ModelCapability.TOOL_CALLING in qwen.capabilities
    assert ModelCapability.TEXT_GENERATION in qwen.capabilities

    # Model 2: LLaMA 3.2 Vision
    vision = next(m for m in models if m.provider_model_name == "llama3.2-vision:latest")
    assert vision.model_id == "ollama:llama3.2-vision:latest"
    assert vision.parameter_size == "10.7B"
    assert vision.context_window == 131072
    assert ModelCapability.VISION in vision.capabilities


@pytest.mark.asyncio
async def test_ollama_provider_generate(mock_ollama_client: httpx.AsyncClient):
    """Verify text generation parses content, duration, and token metrics."""
    provider = OllamaProvider(endpoint="http://mock-ollama:11434", client=mock_ollama_client)
    resp = await provider.generate(
        "qwen2.5:latest",
        ModelGenerateRequest(prompt="Test prompt"),
    )

    assert resp.content == "ORBIT autonomous execution verified."
    assert resp.model_id == "ollama:qwen2.5:latest"
    assert resp.total_duration_ms == 450.0
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 18


@pytest.mark.asyncio
async def test_ollama_provider_chat(mock_ollama_client: httpx.AsyncClient):
    """Verify chat endpoint parses message content and metrics."""
    provider = OllamaProvider(endpoint="http://mock-ollama:11434", client=mock_ollama_client)
    resp = await provider.chat(
        "qwen2.5:latest",
        ModelChatRequest(messages=[ModelChatMessage(role="user", content="Hi")]),
    )

    assert "ready to assist" in resp.content
    assert resp.model_id == "ollama:qwen2.5:latest"
    assert resp.total_duration_ms == 320.0


@pytest.mark.asyncio
async def test_ollama_provider_nonexistent_model_raises_404(mock_ollama_client: httpx.AsyncClient):
    """Verify requesting nonexistent model raises OllamaModelNotFoundError."""
    provider = OllamaProvider(endpoint="http://mock-ollama:11434", client=mock_ollama_client)
    with pytest.raises(OllamaModelNotFoundError):
        await provider.generate("nonexistent", ModelGenerateRequest(prompt="test"))


@pytest.mark.asyncio
async def test_ollama_provider_connection_refused_handling():
    """Verify offline Ollama endpoint fails honestly with UNAVAILABLE health."""
    # Use invalid localhost port that is guaranteed not listening
    provider = OllamaProvider(endpoint="http://127.0.0.1:59999", connect_timeout=0.5)
    health = await provider.health_check()

    assert health.status == ProviderHealthStatus.UNAVAILABLE
    assert "connection refused" in (health.diagnostic_message or "").lower() or "connect" in (health.diagnostic_message or "").lower()

    with pytest.raises(OllamaUnavailableError):
        await provider.discover_models()

    await provider.shutdown()
