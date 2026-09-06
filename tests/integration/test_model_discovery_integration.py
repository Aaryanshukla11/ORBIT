"""Integration tests for Multi-Provider Model Discovery & Isolation (Milestone M1.9 Step 1).

Validates:
- Multi-provider discovery aggregation
- Fault isolation when one provider is offline/unreachable
- Duplicate name disambiguation across providers
- ModelManager discovery and registry integration
"""

from __future__ import annotations

import httpx
import pytest

from orbit.runtime.models.discovery import ModelDiscoveryEngine
from orbit.runtime.models.manager import ModelManager
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
    ModelStatus,
)
from orbit.runtime.model_providers.ollama import OllamaProvider
from tests.unit.test_model_manager import MockTestProvider


@pytest.mark.asyncio
async def test_discovery_engine_fault_isolation():
    """Verify healthy provider models are discovered even when a second provider is completely offline."""
    # Healthy Provider (Ollama Mock)
    healthy_models = [
        ModelDescriptor(
            model_id="ollama:qwen2.5:7b",
            provider=ModelProviderKind.OLLAMA,
            provider_model_name="qwen2.5:7b",
            display_name="Qwen 2.5 7B",
            status=ModelStatus.AVAILABLE,
            capabilities={ModelCapability.CHAT},
        ),
        ModelDescriptor(
            model_id="ollama:llama3:8b",
            provider=ModelProviderKind.OLLAMA,
            provider_model_name="llama3:8b",
            display_name="LLaMA 3 8B",
            status=ModelStatus.AVAILABLE,
            capabilities={ModelCapability.CHAT},
        ),
    ]
    healthy_provider = MockTestProvider(
        provider_kind=ModelProviderKind.OLLAMA,
        endpoint="http://127.0.0.1:11434",
        models=healthy_models,
    )

    # Offline / Unreachable Provider
    offline_provider = OllamaProvider(
        endpoint="http://127.0.0.1:59998",
        connect_timeout=0.3,
    )

    discovery_engine = ModelDiscoveryEngine(providers=[healthy_provider, offline_provider])
    result = await discovery_engine.discover_all()

    # Fault Isolation Invariant:
    # Discovery does NOT crash; healthy provider models are preserved!
    assert result.total_discovered == 2
    assert ModelProviderKind.OLLAMA in result.successful_providers
    assert len(result.failed_providers) >= 1

    # Check model descriptors
    discovered_ids = {m.model_id for m in result.discovered_models}
    assert "ollama:qwen2.5:7b" in discovered_ids
    assert "ollama:llama3:8b" in discovered_ids

    await offline_provider.shutdown()


@pytest.mark.asyncio
async def test_model_manager_discovery_integration():
    """Verify ModelManager end-to-end multi-provider discovery and registry population."""
    models_p1 = [
        ModelDescriptor(
            model_id="ollama:qwen2.5:latest",
            provider=ModelProviderKind.OLLAMA,
            provider_model_name="qwen2.5:latest",
            display_name="Qwen 2.5",
            status=ModelStatus.AVAILABLE,
            capabilities={ModelCapability.CHAT, ModelCapability.TOOL_CALLING},
        ),
    ]
    models_p2 = [
        ModelDescriptor(
            model_id="lm_studio:qwen2.5:latest",
            provider=ModelProviderKind.LM_STUDIO,
            provider_model_name="qwen2.5:latest",
            display_name="LM Studio Qwen 2.5",
            status=ModelStatus.AVAILABLE,
            capabilities={ModelCapability.CHAT},
        ),
    ]

    p1 = MockTestProvider(provider_kind=ModelProviderKind.OLLAMA, models=models_p1)
    p2 = MockTestProvider(provider_kind=ModelProviderKind.LM_STUDIO, endpoint="http://127.0.0.1:1234", models=models_p2)

    manager = ModelManager(providers=[p1, p2])
    result = await manager.discover_models()

    assert result.total_discovered == 2

    # Query registry via manager
    all_models = await manager.list_models()
    assert len(all_models) == 2

    # Query by capability
    tool_models = await manager.list_models(capability=ModelCapability.TOOL_CALLING)
    assert len(tool_models) == 1
    assert tool_models[0].model_id == "ollama:qwen2.5:latest"

    # Transactional Switch to P1
    await manager.set_active_model("ollama:qwen2.5:latest")
    assert manager.get_active_model_id() == "ollama:qwen2.5:latest"

    # Transactional Switch to P2
    await manager.set_active_model("lm_studio:qwen2.5:latest")
    assert manager.get_active_model_id() == "lm_studio:qwen2.5:latest"
