"""Unit tests for Model Inventory Engine covering all Milestone M1.9 Step 2 specifications."""

import json
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional
import httpx
import pytest
from unittest.mock import AsyncMock, patch

from orbit.runtime.models.discovery import ModelDiscoveryEngine
from orbit.runtime.models.file_scanner import LocalFileModelScanner
from orbit.runtime.models.inventory import (
    CloudProviderInventorySummary,
    InventoryReport,
    ModelInventory,
    RuntimeInventorySummary,
    SystemCapabilitiesReport,
)
from orbit.runtime.models.lifecycle import (
    InvalidStateTransitionError,
    ModelLifecycleManager,
)
from orbit.runtime.models.models import (
    CloudAuthStatus,
    CloudProviderKind,
    ModelCapability,
    ModelDescriptor,
    ModelFileFormat,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry
from orbit.runtime.model_providers.base import ModelProvider
from orbit.runtime.model_providers.cloud import CloudModelProvider
from orbit.runtime.model_providers.lm_studio import LMStudioProvider
from orbit.runtime.model_providers.ollama import OllamaProvider


class FakeLocalProvider(ModelProvider):
    """Controlled fake local runtime provider."""

    def __init__(
        self,
        provider_kind: ModelProviderKind = ModelProviderKind.OLLAMA,
        models: Optional[List[ModelDescriptor]] = None,
        health: Optional[ProviderHealth] = None,
        should_raise: bool = False,
    ):
        self._provider_kind = provider_kind
        self._models = models or []
        self._health = health or ProviderHealth(
            provider=provider_kind,
            status=ProviderHealthStatus.HEALTHY,
            is_available=True,
            endpoint="http://127.0.0.1:11434",
            diagnostic_message="OK",
        )
        self._should_raise = should_raise

    @property
    def provider_kind(self) -> ModelProviderKind:
        return self._provider_kind

    @property
    def endpoint(self) -> str:
        return self._health.endpoint

    async def is_available(self) -> bool:
        return self._health.is_available

    async def health_check(self) -> ProviderHealth:
        if self._should_raise:
            raise RuntimeError("Provider health check crashed unexpectedly")
        return self._health

    async def discover_models(self) -> List[ModelDescriptor]:
        if self._should_raise:
            raise RuntimeError("Provider discovery crashed unexpectedly")
        return self._models

    async def get_model(self, provider_model_name: str) -> Optional[ModelDescriptor]:
        for m in self._models:
            if m.provider_model_name == provider_model_name or m.model_id == provider_model_name:
                return m
        return None

    async def get_model_status(self, provider_model_name: str) -> ModelStatus:
        m = await self.get_model(provider_model_name)
        return m.status if m else ModelStatus.UNAVAILABLE

    async def load_model(self, model_name: str) -> bool:
        return True

    async def unload_model(self, provider_model_name: str) -> bool:
        return True

    async def generate(self, model_name: str, request: ModelGenerateRequest) -> ModelGenerateResponse:
        return ModelGenerateResponse(model_name=model_name, response_text="fake output")

    async def chat(self, model_name: str, request: Any) -> ModelGenerateResponse:
        return ModelGenerateResponse(model_name=model_name, response_text="fake chat output")

    async def shutdown(self) -> None:
        pass


# 1. Local runtime detected
@pytest.mark.asyncio
async def test_01_local_runtime_detected():
    m = ModelDescriptor(
        model_id="ollama:qwen2.5:latest",
        model_name="qwen2.5:latest",
        provider=ModelProviderKind.OLLAMA,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        provider_model_name="qwen2.5:latest",
        status=ModelStatus.AVAILABLE,
    )
    provider = FakeLocalProvider(provider_kind=ModelProviderKind.OLLAMA, models=[m])
    inv = ModelInventory()
    inv.register_runtime_provider(provider)

    report = await inv.refresh(include_cloud=False, include_files=False)
    assert len(report.local_runtimes) == 1
    assert report.local_runtimes[0].is_available is True
    assert report.local_runtimes[0].health_status == ProviderHealthStatus.HEALTHY
    assert len(report.models) == 1
    assert report.models[0].model_id == "ollama:qwen2.5:latest"


# 2. Local runtime unavailable
@pytest.mark.asyncio
async def test_02_local_runtime_unavailable():
    provider = FakeLocalProvider(
        provider_kind=ModelProviderKind.LM_STUDIO,
        health=ProviderHealth(
            provider=ModelProviderKind.LM_STUDIO,
            status=ProviderHealthStatus.UNAVAILABLE,
            is_available=False,
            endpoint="http://127.0.0.1:1234",
            diagnostic_message="LM Studio local server is not reachable",
        ),
    )
    inv = ModelInventory()
    inv.register_runtime_provider(provider)

    report = await inv.refresh(include_cloud=False, include_files=False)
    assert len(report.local_runtimes) == 1
    assert report.local_runtimes[0].is_available is False
    assert report.local_runtimes[0].health_status == ProviderHealthStatus.UNAVAILABLE
    assert len(report.models) == 0


# 3. Runtime timeout
@pytest.mark.asyncio
async def test_03_runtime_timeout():
    provider = LMStudioProvider(host="127.0.0.1", port=9999, timeout_seconds=0.01)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Timeout")):
        inv = ModelInventory()
        inv.register_runtime_provider(provider)
        report = await inv.refresh(include_cloud=False, include_files=False)

    assert len(report.local_runtimes) == 1
    assert report.local_runtimes[0].is_available is False
    assert "timed out" in (report.local_runtimes[0].diagnostic_message or "").lower() or "timeout" in (report.local_runtimes[0].diagnostic_message or "").lower()


# 4. Ollama-style model normalization
@pytest.mark.asyncio
async def test_04_ollama_model_normalization():
    p = OllamaProvider(host="127.0.0.1", port=11434)
    tags_resp = httpx.Response(
        200,
        json={
            "models": [
                {
                    "name": "llama3.2-vision:latest",
                    "model": "llama3.2-vision:latest",
                    "size": 7914820608,
                    "details": {
                        "family": "llama",
                        "parameter_size": "11B",
                        "quantization_level": "Q4_K_M",
                    },
                }
            ]
        },
        request=httpx.Request("GET", "http://127.0.0.1:11434/api/tags"),
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=tags_resp):
        models = await p.discover_models()

    assert len(models) == 1
    m = models[0]
    assert m.model_id == "ollama:llama3.2-vision:latest"
    assert m.provider == ModelProviderKind.OLLAMA
    assert m.source_type == ModelSourceType.LOCAL_RUNTIME
    assert m.size_bytes == 7914820608
    assert m.parameter_size == "11B"
    assert m.quantization == "Q4_K_M"
    assert ModelCapability.VISION in m.capabilities


# 5. Duplicate model identity handling (provenance-aware)
@pytest.mark.asyncio
async def test_05_duplicate_model_identity_provenance_aware():
    m_ollama = ModelDescriptor(
        model_id="ollama:qwen2.5-coder:7b",
        model_name="qwen2.5-coder:7b",
        provider=ModelProviderKind.OLLAMA,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        provider_model_name="qwen2.5-coder:7b",
        status=ModelStatus.AVAILABLE,
    )
    m_file = ModelDescriptor(
        model_id="local_file:qwen2.5-coder:7b",
        model_name="qwen2.5-coder:7b",
        provider=ModelProviderKind.LOCAL_FILE,
        source_type=ModelSourceType.LOCAL_FILE,
        provider_model_name="qwen2.5-coder:7b",
        status=ModelStatus.DISCOVERED,
    )
    m_cloud = ModelDescriptor(
        model_id="cloud:openai:qwen2.5-coder:7b",
        model_name="qwen2.5-coder:7b",
        provider=ModelProviderKind.CLOUD_OPENAI,
        source_type=ModelSourceType.CLOUD_PROVIDER,
        provider_model_name="qwen2.5-coder:7b",
        status=ModelStatus.READY,
    )

    registry = ModelRegistry()
    await registry.register_models([m_ollama, m_file, m_cloud])

    # All 3 distinct provenances must co-exist without colliding or overwriting
    all_models = await registry.list_models()
    assert len(all_models) == 3
    ids = {m.model_id for m in all_models}
    assert ids == {
        "ollama:qwen2.5-coder:7b",
        "local_file:qwen2.5-coder:7b",
        "cloud:openai:qwen2.5-coder:7b",
    }


# 6. Local model file discovery
@pytest.mark.asyncio
async def test_06_local_model_file_discovery(tmp_path: Path):
    model_file = tmp_path / "model.gguf"
    # GGUF header
    model_file.write_bytes(b"GGUF\x03\x00\x00\x00\x10\x00\x00\x00\x05\x00\x00\x00" + b"\x00" * 50)

    scanner = LocalFileModelScanner(model_directories=[tmp_path])
    inv = ModelInventory(file_scanner=scanner)

    report = await inv.refresh(include_runtimes=False, include_cloud=False, include_files=True)
    assert len(report.local_files) == 1
    assert report.local_files[0].format == ModelFileFormat.GGUF
    assert len(report.models) == 1
    assert report.models[0].source_type == ModelSourceType.LOCAL_FILE


# 7. Unsupported file ignored safely
@pytest.mark.asyncio
async def test_07_unsupported_file_ignored_safely(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("Hello world")
    (tmp_path / "script.py").write_text("import sys")
    (tmp_path / "data.csv").write_text("a,b,c")

    scanner = LocalFileModelScanner(model_directories=[tmp_path])
    inv = ModelInventory(file_scanner=scanner)

    report = await inv.refresh(include_runtimes=False, include_cloud=False, include_files=True)
    assert len(report.local_files) == 0
    assert len(report.models) == 0


# 8. Cloud provider configured
@pytest.mark.asyncio
async def test_08_cloud_provider_configured():
    cloud_p = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-test-live-key",
    )
    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        inv = ModelInventory(cloud_providers=[cloud_p])
        report = await inv.refresh(include_runtimes=False, include_cloud=True, include_files=False)

    assert len(report.cloud_providers) == 1
    cp = report.cloud_providers[0]
    assert cp.is_configured is True
    assert cp.auth_status == CloudAuthStatus.AUTHENTICATED
    assert cp.models_count > 0


# 9. Cloud provider unconfigured
@pytest.mark.asyncio
async def test_09_cloud_provider_unconfigured():
    cloud_p = CloudModelProvider(
        cloud_kind=CloudProviderKind.ANTHROPIC,
        api_key=None,
    )
    inv = ModelInventory(cloud_providers=[cloud_p])
    report = await inv.refresh(include_runtimes=False, include_cloud=True, include_files=False)

    assert len(report.cloud_providers) == 1
    cp = report.cloud_providers[0]
    assert cp.is_configured is False
    assert cp.auth_status == CloudAuthStatus.NOT_CONFIGURED
    assert cp.models_count == 0


# 10. Credentials never serialized
@pytest.mark.asyncio
async def test_10_credentials_never_serialized():
    secret_key = "sk-super-secret-password-xyz12345678"
    cloud_p = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key=secret_key,
    )
    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        inv = ModelInventory(cloud_providers=[cloud_p])
        report = await inv.refresh(include_runtimes=False, include_cloud=True, include_files=False)

    pub_dict = report.to_public_dict()
    pub_json = json.dumps(pub_dict)

    assert secret_key not in pub_json
    assert "Authorization" not in pub_json
    assert "headers" not in pub_dict.get("cloud_providers", [{}])[0]


# 11. Invalid lifecycle transition rejected
def test_11_invalid_lifecycle_transition_rejected():
    lc = ModelLifecycleManager()
    lc.record_transition("m1", ModelStatus.UNAVAILABLE)

    assert not lc.can_transition(ModelStatus.UNAVAILABLE, ModelStatus.ACTIVE)
    with pytest.raises(InvalidStateTransitionError):
        lc.transition("m1", ModelStatus.ACTIVE)


# 12. Valid lifecycle transition accepted
def test_12_valid_lifecycle_transition_accepted():
    lc = ModelLifecycleManager()
    lc.record_transition("m1", ModelStatus.AVAILABLE)

    assert lc.can_transition(ModelStatus.AVAILABLE, ModelStatus.ACTIVE)
    trans = lc.transition("m1", ModelStatus.ACTIVE, reason="Activated by orchestrator")
    assert trans.to_status == ModelStatus.ACTIVE
    assert lc.get_current_status("m1") == ModelStatus.ACTIVE


# 13. Health check timeout
@pytest.mark.asyncio
async def test_13_health_check_timeout():
    provider = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-test-key",
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Network timeout")):
        health = await provider.health_check()

    assert health.status == ProviderHealthStatus.UNAVAILABLE
    assert "timed out" in (health.diagnostic_message or "").lower() or "timeout" in (health.diagnostic_message or "").lower()


# 14. Inventory refresh failure isolation
@pytest.mark.asyncio
async def test_14_inventory_refresh_failure_isolation():
    # Provider 1 crashes
    broken_prov = FakeLocalProvider(
        provider_kind=ModelProviderKind.OLLAMA,
        should_raise=True,
    )
    # Provider 2 succeeds
    good_m = ModelDescriptor(
        model_id="lm_studio:good-model",
        model_name="good-model",
        provider=ModelProviderKind.LM_STUDIO,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        provider_model_name="good-model",
        status=ModelStatus.AVAILABLE,
    )
    good_prov = FakeLocalProvider(
        provider_kind=ModelProviderKind.LM_STUDIO,
        models=[good_m],
    )

    inv = ModelInventory()
    inv.register_runtime_provider(broken_prov)
    inv.register_runtime_provider(good_prov)

    # Refresh must NOT crash, and must preserve the working provider results
    report = await inv.refresh(include_cloud=False, include_files=False)

    assert len(report.local_runtimes) == 2
    assert len(report.models) == 1
    assert report.models[0].model_id == "lm_studio:good-model"


# 15. Empty inventory
@pytest.mark.asyncio
async def test_15_empty_inventory():
    inv = ModelInventory(cloud_providers=[])
    report = await inv.refresh(include_runtimes=False, include_cloud=False, include_files=False)

    assert len(report.models) == 0
    assert report.system_capabilities.total_models == 0
    assert report.system_capabilities.offline_models_available is False
    assert report.system_capabilities.cloud_models_available is False


# 16. Multiple provider aggregation
@pytest.mark.asyncio
async def test_16_multiple_provider_aggregation(tmp_path: Path):
    # 1. Local runtime model
    m_ollama = ModelDescriptor(
        model_id="ollama:llama3.2-vision:latest",
        model_name="llama3.2-vision:latest",
        provider=ModelProviderKind.OLLAMA,
        source_type=ModelSourceType.LOCAL_RUNTIME,
        provider_model_name="llama3.2-vision:latest",
        capabilities=[ModelCapability.VISION, ModelCapability.CHAT],
        status=ModelStatus.AVAILABLE,
    )
    p_ollama = FakeLocalProvider(provider_kind=ModelProviderKind.OLLAMA, models=[m_ollama])

    # 2. Local weight file
    model_file = tmp_path / "deepseek-coder.gguf"
    model_file.write_bytes(b"GGUF\x03\x00\x00\x00\x10\x00\x00\x00\x05\x00\x00\x00" + b"\x00" * 50)
    scanner = LocalFileModelScanner(model_directories=[tmp_path])

    # 3. Cloud provider
    cloud_p = CloudModelProvider(cloud_kind=CloudProviderKind.OPENAI, api_key="sk-test-openai")
    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))

    inv = ModelInventory(file_scanner=scanner, cloud_providers=[cloud_p])
    inv.register_runtime_provider(p_ollama)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        report = await inv.refresh()

    assert report.system_capabilities.total_models >= 3
    assert report.system_capabilities.offline_models_available is True
    assert report.system_capabilities.cloud_models_available is True
    assert report.system_capabilities.vision_capable_count >= 1
    assert report.system_capabilities.local_models_count == 2
    assert report.system_capabilities.cloud_models_count >= 1
