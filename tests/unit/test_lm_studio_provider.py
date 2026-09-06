"""Unit tests for LM Studio Runtime Provider (Milestone M1.9 Step 2)."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from orbit.runtime.model_providers.lm_studio import LMStudioProvider
from orbit.runtime.models.models import (
    ModelCapability,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealthStatus,
)


@pytest.mark.asyncio
async def test_lm_studio_discovery_success():
    provider = LMStudioProvider(host="127.0.0.1", port=1234)

    mock_resp = httpx.Response(
        200,
        json={
            "data": [
                {"id": "lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF", "object": "model"},
                {"id": "qwen2.5-coder-7b-instruct", "object": "model"},
            ]
        },
        request=httpx.Request("GET", "http://127.0.0.1:1234/v1/models"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        models = await provider.discover_models()

    assert len(models) == 2
    m1 = models[0]
    assert m1.model_id == "lm_studio:lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF"
    assert m1.provider == ModelProviderKind.LM_STUDIO
    assert m1.source_type == ModelSourceType.LOCAL_RUNTIME
    assert m1.status == ModelStatus.AVAILABLE

    m2 = models[1]
    assert m2.model_id == "lm_studio:qwen2.5-coder-7b-instruct"
    assert ModelCapability.CODE in m2.capabilities or ModelCapability.CODE_GENERATION in m2.capabilities


@pytest.mark.asyncio
async def test_lm_studio_health_check_healthy():
    provider = LMStudioProvider(host="127.0.0.1", port=1234)
    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "http://127.0.0.1:1234/v1/models"))

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        health = await provider.health_check()

    assert health.status == ProviderHealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_lm_studio_offline_unreachable():
    provider = LMStudioProvider(host="127.0.0.1", port=1234)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection refused")):
        health = await provider.health_check()
        models = await provider.discover_models()

    assert health.status == ProviderHealthStatus.UNAVAILABLE
    assert "refused" in (health.diagnostic_message or "").lower() or "unreachable" in (health.diagnostic_message or "").lower() or "cannot connect" in (health.diagnostic_message or "").lower()
    assert models == []


@pytest.mark.asyncio
async def test_lm_studio_timeout_handled_gracefully():
    provider = LMStudioProvider(host="127.0.0.1", port=1234, timeout_seconds=0.1)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Timed out")):
        health = await provider.health_check()
        models = await provider.discover_models()

    assert health.status == ProviderHealthStatus.UNAVAILABLE
    assert "timed out" in (health.diagnostic_message or "").lower() or "timeout" in (health.diagnostic_message or "").lower()
    assert models == []
