"""Integration tests for System Inventory Engine and Multi-Source Aggregation (Milestone M1.9 Step 2).

Validates the full discovery-to-report pipeline:
Runtime Adapter -> Discovery Engine -> Normalization -> Inventory -> Health Status -> Public Inventory Report
"""

from pathlib import Path
from typing import List
import httpx
import pytest
from unittest.mock import AsyncMock, patch

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.models.file_scanner import LocalFileModelScanner
from orbit.runtime.models.inventory import ModelInventory
from orbit.runtime.models.manager import ModelManager
from orbit.runtime.models.models import (
    CloudProviderKind,
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.cloud import CloudModelProvider
from orbit.runtime.model_providers.lm_studio import LMStudioProvider
from orbit.runtime.model_providers.ollama import OllamaProvider
from orbit.runtime.orchestrator import OrbitOrchestrator
from tests.unit.test_model_manager import MockTestProvider


@pytest.mark.asyncio
async def test_full_inventory_pipeline_end_to_end(tmp_path: Path):
    """Verify entire pipeline aggregates Local Runtimes, Local Files, and Cloud Providers."""
    # 1. Local Runtime Provider (Ollama)
    m_ollama = ModelDescriptor(
        model_id="ollama:qwen2.5:latest",
        model_name="qwen2.5:latest",
        provider=ModelProviderKind.OLLAMA,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        provider_model_name="qwen2.5:latest",
        capabilities={ModelCapability.CHAT, ModelCapability.TOOL_CALLING},
        status=ModelStatus.AVAILABLE,
    )
    p_ollama = MockTestProvider(provider_kind=ModelProviderKind.OLLAMA, models=[m_ollama])

    # 2. Local File Model (GGUF)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    gguf_file = model_dir / "llama-3-8b.gguf"
    gguf_file.write_bytes(b"GGUF\x03\x00\x00\x00\x10\x00\x00\x00\x05\x00\x00\x00" + b"\x00" * 50)
    file_scanner = LocalFileModelScanner(model_directories=[model_dir])

    # 3. Cloud Provider (OpenAI)
    cloud_openai = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-test-secret-key-12345",
    )

    # 4. Initialize Manager & Orchestrator
    manager = ModelManager(
        providers=[p_ollama],
        file_scanner=file_scanner,
        cloud_providers=[cloud_openai],
    )

    event_bus = EventBus()
    orchestrator = OrbitOrchestrator(event_bus=event_bus, model_manager=manager)

    # Mock cloud provider health check
    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        report = await orchestrator.refresh_model_inventory()

    # Verify Report Aggregation
    assert report.system_capabilities.offline_models_available is True
    assert report.system_capabilities.cloud_models_available is True
    assert report.system_capabilities.total_models >= 3
    assert report.system_capabilities.local_models_count == 2
    assert report.system_capabilities.cloud_models_count >= 1

    # Verify Public Serialization Invariant (No Secret Leakage)
    public_payload = report.to_public_dict()
    assert "sk-test-secret-key-12345" not in str(public_payload)
    assert "Authorization" not in str(public_payload)

    # Verify Orchestrator non-blocking cached report retrieval
    cached_report = await orchestrator.get_model_inventory_report()
    assert cached_report.system_capabilities.total_models == report.system_capabilities.total_models


@pytest.mark.asyncio
async def test_inventory_failure_isolation_between_providers():
    """Verify that when one provider crashes or times out, healthy providers succeed."""
    # Healthy Local Provider
    healthy_m = ModelDescriptor(
        model_id="ollama:qwen2.5:latest",
        model_name="qwen2.5:latest",
        provider=ModelProviderKind.OLLAMA,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        provider_model_name="qwen2.5:latest",
        status=ModelStatus.AVAILABLE,
    )
    p_healthy = MockTestProvider(provider_kind=ModelProviderKind.OLLAMA, models=[healthy_m])

    # Broken/Unreachable LM Studio Provider
    p_broken = LMStudioProvider(host="127.0.0.1", port=59999, timeout_seconds=0.01)

    manager = ModelManager(providers=[p_healthy, p_broken])
    report = await manager.refresh_inventory(include_cloud=False, include_files=False)

    assert len(report.local_runtimes) == 2
    # Healthy provider reported models
    assert len(report.models) == 1
    assert report.models[0].model_id == "ollama:qwen2.5:latest"
    # Capabilities computed correctly
    assert report.system_capabilities.offline_models_available is True
