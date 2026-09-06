"""Unit tests for Model Descriptors, Capabilities, and Health Evaluator (Milestone M1.9 Step 1)."""

from __future__ import annotations

import asyncio
from datetime import datetime
import pytest

from orbit.runtime.models.capabilities import infer_capabilities, matches_capabilities
from orbit.runtime.models.health import HealthEvaluator, measure_roundtrip_latency
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)


def test_model_descriptor_valid_creation():
    """Verify valid model descriptor creation with full metadata."""
    desc = ModelDescriptor(
        model_id="ollama:qwen2.5:latest",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="qwen2.5:latest",
        display_name="Qwen 2.5 Latest",
        status=ModelStatus.AVAILABLE,
        capabilities={ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.TOOL_CALLING},
        context_window=32768,
        parameter_size="7.6B",
        quantization_level="Q4_K_M",
        family="qwen2",
        size_bytes=4683087332,
        digest="845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e",
        local_or_remote="local",
        endpoint="http://127.0.0.1:11434",
    )

    assert desc.model_id == "ollama:qwen2.5:latest"
    assert desc.provider == ModelProviderKind.OLLAMA
    assert desc.context_window == 32768
    assert desc.parameter_size == "7.6B"
    assert desc.quantization_level == "Q4_K_M"
    assert ModelCapability.TOOL_CALLING in desc.capabilities


def test_model_descriptor_invalid_id_raises():
    """Verify model_id without colon raises ValueError."""
    with pytest.raises(ValueError, match="model_id must be formatted"):
        ModelDescriptor(
            model_id="invalid_id_no_colon",
            provider=ModelProviderKind.OLLAMA,
            provider_model_name="test",
            display_name="Test",
        )


def test_model_descriptor_unknown_metadata_preserved_as_none():
    """Verify unknown parameters remain explicitly None without fabrication."""
    desc = ModelDescriptor(
        model_id="ollama:custom_model:v1",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="custom_model:v1",
        display_name="Custom Model",
    )

    assert desc.context_window is None
    assert desc.parameter_size is None
    assert desc.quantization_level is None
    assert desc.family is None
    assert desc.size_bytes is None
    assert desc.digest is None


def test_infer_capabilities_text_chat():
    """Verify text and chat capability inference."""
    caps = infer_capabilities(
        provider=ModelProviderKind.OLLAMA,
        raw_capabilities=["completion"],
        model_name="llama3:latest",
    )
    assert ModelCapability.TEXT_GENERATION in caps
    assert ModelCapability.CHAT in caps
    assert ModelCapability.VISION not in caps


def test_infer_capabilities_vision():
    """Verify vision capability inference for multimodal models."""
    caps = infer_capabilities(
        provider=ModelProviderKind.OLLAMA,
        raw_capabilities=["vision", "completion"],
        model_name="llama3.2-vision:latest",
        family="mllama",
    )
    assert ModelCapability.VISION in caps
    assert ModelCapability.TEXT_GENERATION in caps


def test_infer_capabilities_tools():
    """Verify tool calling capability inference."""
    caps = infer_capabilities(
        provider=ModelProviderKind.OLLAMA,
        raw_capabilities=["completion", "tools"],
        model_name="qwen2.5-coder:14b",
    )
    assert ModelCapability.TOOL_CALLING in caps
    assert ModelCapability.TEXT_GENERATION in caps


def test_infer_capabilities_reasoning():
    """Verify reasoning capability inference from model naming patterns."""
    caps = infer_capabilities(
        provider=ModelProviderKind.OLLAMA,
        raw_capabilities=["completion"],
        model_name="deepseek-r1:8b",
    )
    assert ModelCapability.REASONING in caps


def test_infer_capabilities_embeddings():
    """Verify embedding model capability inference."""
    caps = infer_capabilities(
        provider=ModelProviderKind.OLLAMA,
        raw_capabilities=["embedding"],
        model_name="nomic-embed-text:latest",
        family="nomic-bert",
    )
    assert ModelCapability.EMBEDDINGS in caps
    assert ModelCapability.CHAT not in caps


def test_matches_capabilities():
    """Verify capability filtering predicate."""
    desc = ModelDescriptor(
        model_id="ollama:model_tools",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="model_tools",
        display_name="Model Tools",
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_CALLING},
    )

    assert matches_capabilities(desc, [ModelCapability.CHAT]) is True
    assert matches_capabilities(desc, [ModelCapability.CHAT, ModelCapability.TOOL_CALLING]) is True
    assert matches_capabilities(desc, [ModelCapability.VISION]) is False
    assert matches_capabilities(desc, []) is True
    assert matches_capabilities(desc, None) is True


def test_health_evaluator_healthy():
    """Verify healthy status creation and latency tracking."""
    health = HealthEvaluator.create_healthy(
        provider=ModelProviderKind.OLLAMA,
        endpoint="http://127.0.0.1:11434",
        latency_ms=12.5,
        version_info="Ollama v0.3.14",
    )
    assert health.status == ProviderHealthStatus.HEALTHY
    assert health.latency_ms == 12.5
    assert health.version_info == "Ollama v0.3.14"


def test_health_evaluator_degraded_latency():
    """Verify high latency marks provider as DEGRADED."""
    health = HealthEvaluator.create_healthy(
        provider=ModelProviderKind.OLLAMA,
        endpoint="http://127.0.0.1:11434",
        latency_ms=6500.0,
    )
    assert health.status == ProviderHealthStatus.DEGRADED
    assert "Elevated latency" in (health.diagnostic_message or "")


def test_health_evaluator_unavailable():
    """Verify unavailable status creation."""
    health = HealthEvaluator.create_unavailable(
        provider=ModelProviderKind.OLLAMA,
        endpoint="http://127.0.0.1:11434",
        reason="Connection refused",
    )
    assert health.status == ProviderHealthStatus.UNAVAILABLE
    assert health.latency_ms is None
    assert "Connection refused" in (health.diagnostic_message or "")


@pytest.mark.asyncio
async def test_measure_roundtrip_latency():
    """Verify latency timer context calculates positive millisecond duration."""
    async with measure_roundtrip_latency() as timing:
        await asyncio.sleep(0.01)
    
    assert timing["elapsed_ms"] is not None
    assert timing["elapsed_ms"] >= 8.0  # at least ~8-10ms
