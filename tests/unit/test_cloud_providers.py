"""Unit tests for Cloud Model Providers and Credential Protection (Milestone M1.9 Step 2)."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from orbit.runtime.model_providers.cloud import (
    CloudModelProvider,
    CloudProviderAuthError,
    CloudProviderError,
    CloudProviderUnreachableError,
)
from orbit.runtime.models.models import (
    CloudAuthStatus,
    CloudProviderKind,
    ModelCapability,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealthStatus,
)


def test_cloud_provider_unconfigured():
    provider = CloudModelProvider(cloud_kind=CloudProviderKind.OPENAI, api_key=None)
    assert not provider.is_configured
    assert provider.get_auth_status() == CloudAuthStatus.NOT_CONFIGURED
    assert provider.provider_kind == ModelProviderKind.CLOUD_OPENAI


def test_cloud_provider_configured():
    provider = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-test-super-secret-key-1234567890",
    )
    assert provider.is_configured
    assert provider.get_auth_status() == CloudAuthStatus.AUTHENTICATED


def test_credential_never_exposed_in_repr():
    secret = "sk-super-secret-token-abcdef123456"
    provider = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key=secret,
    )
    repr_str = repr(provider)
    assert secret not in repr_str
    assert "configured=True" in repr_str or "api_key_configured=True" in repr_str


@pytest.mark.asyncio
async def test_unconfigured_health_check_returns_unavailable():
    provider = CloudModelProvider(cloud_kind=CloudProviderKind.ANTHROPIC, api_key=None)
    health = await provider.health_check()
    assert health.status == ProviderHealthStatus.UNAVAILABLE
    assert "not configured" in (health.diagnostic_message or "").lower()


@pytest.mark.asyncio
async def test_configured_health_check_success():
    provider = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-valid-key",
    )

    mock_resp = httpx.Response(200, json={"data": []}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        health = await provider.health_check()
        assert health.status == ProviderHealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_configured_health_check_unauthorized():
    provider = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-invalid-key",
    )

    mock_resp = httpx.Response(401, json={"error": "Invalid API key"}, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        health = await provider.health_check()
        assert health.status in (ProviderHealthStatus.UNAVAILABLE, ProviderHealthStatus.ERROR)
        assert "401" in (health.diagnostic_message or "") or "auth" in (health.diagnostic_message or "").lower()


@pytest.mark.asyncio
async def test_configured_health_check_timeout():
    provider = CloudModelProvider(
        cloud_kind=CloudProviderKind.OPENAI,
        api_key="sk-valid-key",
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Connection timed out")):
        health = await provider.health_check()
        assert health.status == ProviderHealthStatus.UNAVAILABLE
        assert "timed out" in (health.diagnostic_message or "").lower() or "timeout" in (health.diagnostic_message or "").lower()


@pytest.mark.asyncio
async def test_cloud_model_discovery_catalog():
    provider = CloudModelProvider(
        cloud_kind=CloudProviderKind.ANTHROPIC,
        api_key="sk-ant-test-key",
    )

    models = await provider.discover_models()
    assert len(models) > 0
    m_claude = next(m for m in models if "claude" in m.model_name.lower() or "claude-3-5-sonnet" in m.provider_model_name.lower())
    assert m_claude.source_type == ModelSourceType.CLOUD_PROVIDER
    assert m_claude.provider == ModelProviderKind.CLOUD_ANTHROPIC
    assert m_claude.status in (ModelStatus.AVAILABLE, ModelStatus.READY)
    assert ModelCapability.VISION in m_claude.capabilities
    assert ModelCapability.TOOL_CALLING in m_claude.capabilities
