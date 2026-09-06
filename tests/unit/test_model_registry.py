"""Unit tests for ModelRegistry (Milestone M1.9 Step 1)."""

from __future__ import annotations

import pytest

from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry


@pytest.mark.asyncio
async def test_registry_register_and_get():
    """Verify registering and retrieving model descriptors by model_id."""
    registry = ModelRegistry()
    desc = ModelDescriptor(
        model_id="ollama:qwen2.5:7b",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="qwen2.5:7b",
        display_name="Qwen 2.5 7B",
        status=ModelStatus.AVAILABLE,
    )
    await registry.register_model(desc)

    fetched = await registry.get_model("ollama:qwen2.5:7b")
    assert fetched is not None
    assert fetched.model_id == "ollama:qwen2.5:7b"
    assert fetched.display_name == "Qwen 2.5 7B"


@pytest.mark.asyncio
async def test_registry_duplicate_names_different_providers_no_collision():
    """Verify identical model names from different providers do not collide."""
    registry = ModelRegistry()
    desc_ollama = ModelDescriptor(
        model_id="ollama:llama3:latest",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="llama3:latest",
        display_name="Ollama LLaMA 3",
    )
    desc_lm_studio = ModelDescriptor(
        model_id="lm_studio:llama3:latest",
        provider=ModelProviderKind.LM_STUDIO,
        provider_model_name="llama3:latest",
        display_name="LM Studio LLaMA 3",
    )

    await registry.register_models([desc_ollama, desc_lm_studio])

    assert await registry.count() == 2
    f_ollama = await registry.get_model("ollama:llama3:latest")
    f_lm = await registry.get_model("lm_studio:llama3:latest")
    assert f_ollama is not None and f_ollama.provider == ModelProviderKind.OLLAMA
    assert f_lm is not None and f_lm.provider == ModelProviderKind.LM_STUDIO


@pytest.mark.asyncio
async def test_registry_filter_by_capability_and_provider():
    """Verify filtering models by provider and required capability."""
    registry = ModelRegistry()
    m1 = ModelDescriptor(
        model_id="ollama:vision_model",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="vision_model",
        display_name="Vision Model",
        capabilities={ModelCapability.CHAT, ModelCapability.VISION},
    )
    m2 = ModelDescriptor(
        model_id="ollama:code_model",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="code_model",
        display_name="Code Model",
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_CALLING},
    )
    m3 = ModelDescriptor(
        model_id="lm_studio:code_model",
        provider=ModelProviderKind.LM_STUDIO,
        provider_model_name="code_model",
        display_name="LM Code Model",
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_CALLING},
    )

    await registry.register_models([m1, m2, m3])

    # Filter by VISION
    vision_models = await registry.list_models(capability=ModelCapability.VISION)
    assert len(vision_models) == 1
    assert vision_models[0].model_id == "ollama:vision_model"

    # Filter by OLLAMA + TOOL_CALLING
    ollama_tools = await registry.list_models(provider=ModelProviderKind.OLLAMA, capability=ModelCapability.TOOL_CALLING)
    assert len(ollama_tools) == 1
    assert ollama_tools[0].model_id == "ollama:code_model"


@pytest.mark.asyncio
async def test_registry_status_and_health_update():
    """Verify atomic status and health updates in registry."""
    registry = ModelRegistry()
    m = ModelDescriptor(
        model_id="ollama:model_1",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="model_1",
        display_name="Model 1",
        status=ModelStatus.DISCOVERED,
    )
    await registry.register_model(m)

    ok = await registry.update_model_status("ollama:model_1", ModelStatus.LOADED)
    assert ok is True
    updated = await registry.get_model("ollama:model_1")
    assert updated is not None
    assert updated.status == ModelStatus.LOADED

    health = ProviderHealth(
        provider=ModelProviderKind.OLLAMA,
        status=ProviderHealthStatus.HEALTHY,
        endpoint="http://127.0.0.1:11434",
        latency_ms=10.0,
    )
    ok_h = await registry.update_model_health("ollama:model_1", health)
    assert ok_h is True
    updated_h = await registry.get_model("ollama:model_1")
    assert updated_h is not None
    assert updated_h.last_health is not None
    assert updated_h.last_health.latency_ms == 10.0


@pytest.mark.asyncio
async def test_registry_remove_and_clear():
    """Verify removing models by ID, provider, and clearing registry."""
    registry = ModelRegistry()
    m1 = ModelDescriptor(model_id="ollama:m1", provider=ModelProviderKind.OLLAMA, provider_model_name="m1", display_name="M1")
    m2 = ModelDescriptor(model_id="ollama:m2", provider=ModelProviderKind.OLLAMA, provider_model_name="m2", display_name="M2")
    m3 = ModelDescriptor(model_id="lm_studio:m3", provider=ModelProviderKind.LM_STUDIO, provider_model_name="m3", display_name="M3")

    await registry.register_models([m1, m2, m3])
    assert await registry.count() == 3

    # Remove single
    assert await registry.remove_model("ollama:m1") is True
    assert await registry.count() == 2

    # Remove by provider
    removed_count = await registry.remove_models_by_provider(ModelProviderKind.OLLAMA)
    assert removed_count == 1
    assert await registry.count() == 1

    # Clear
    await registry.clear()
    assert await registry.count() == 0
