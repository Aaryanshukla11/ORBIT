"""Cloud Model Providers Adapter and Gateway (Milestone M1.9 Step 2).

Supports OpenAI-compatible, Anthropic, Gemini, and custom remote API endpoints.

CRITICAL SECURITY INVARIANT:
API keys and authentication credentials are NEVER logged, serialized, or exposed.
Only auth availability status (AUTHENTICATED, NOT_CONFIGURED, UNREACHABLE, ERROR) is reported.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional, Set
import httpx

from orbit.runtime.models.capabilities import infer_capabilities
from orbit.runtime.models.health import HealthEvaluator, measure_roundtrip_latency
from orbit.runtime.models.models import (
    CloudAuthStatus,
    CloudProviderKind,
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.base import ModelProvider

logger = logging.getLogger(__name__)


class CloudProviderError(Exception):
    """Base exception for CloudModelProvider errors."""
    pass


class CloudProviderUnreachableError(CloudProviderError):
    """Raised when cloud endpoint cannot be reached."""
    pass


class CloudProviderAuthError(CloudProviderError):
    """Raised when authentication against cloud endpoint fails."""
    pass


# Default curated catalogs for supported cloud platforms when authenticated
CURATED_CLOUD_CATALOGS: Dict[CloudProviderKind, List[Dict[str, Any]]] = {
    CloudProviderKind.OPENAI: [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 128000,
            "family": "gpt4",
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 128000,
            "family": "gpt4",
        },
        {
            "id": "o1",
            "name": "OpenAI o1",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE},
            "context_window": 200000,
            "family": "o1",
        },
        {
            "id": "text-embedding-3-small",
            "name": "Text Embedding 3 Small",
            "capabilities": {ModelCapability.EMBEDDINGS},
            "context_window": 8191,
            "family": "embedding",
        },
    ],
    CloudProviderKind.ANTHROPIC: [
        {
            "id": "claude-3-5-sonnet-latest",
            "name": "Claude 3.5 Sonnet",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 200000,
            "family": "claude",
        },
        {
            "id": "claude-3-5-haiku-latest",
            "name": "Claude 3.5 Haiku",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 200000,
            "family": "claude",
        },
    ],
    CloudProviderKind.GEMINI: [
        {
            "id": "gemini-2.0-flash",
            "name": "Gemini 2.0 Flash",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 1048576,
            "family": "gemini",
        },
        {
            "id": "gemini-1.5-pro",
            "name": "Gemini 1.5 Pro",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.REASONING, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 2097152,
            "family": "gemini",
        },
    ],
}


class CloudModelProvider(ModelProvider):
    """Secure provider adapter for cloud AI services."""

    def __init__(
        self,
        cloud_kind: CloudProviderKind = CloudProviderKind.OPENAI,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        env_var_name: Optional[str] = None,
        connect_timeout: float = 2.0,
        request_timeout: float = 15.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._cloud_kind = cloud_kind
        self._env_var_name = env_var_name or self._default_env_var(cloud_kind)
        # Store api_key securely in private attribute without logging or exposing in repr
        self._api_key = api_key or os.environ.get(self._env_var_name)
        self._endpoint = (endpoint or self._default_endpoint(cloud_kind)).rstrip("/")
        self._connect_timeout = connect_timeout
        self._request_timeout = request_timeout
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout, connect=connect_timeout),
        )
        self._own_client = client is None

    def __repr__(self) -> str:
        """Secure representation that NEVER reveals secrets."""
        has_key = bool(self._api_key)
        return f"<CloudModelProvider kind={self._cloud_kind.value} endpoint={self._endpoint} configured={has_key}>"

    @staticmethod
    def _default_env_var(kind: CloudProviderKind) -> str:
        if kind == CloudProviderKind.OPENAI:
            return "OPENAI_API_KEY"
        elif kind == CloudProviderKind.ANTHROPIC:
            return "ANTHROPIC_API_KEY"
        elif kind == CloudProviderKind.GEMINI:
            return "GEMINI_API_KEY"
        return "CUSTOM_AI_API_KEY"

    @staticmethod
    def _default_endpoint(kind: CloudProviderKind) -> str:
        if kind == CloudProviderKind.OPENAI:
            return "https://api.openai.com/v1"
        elif kind == CloudProviderKind.ANTHROPIC:
            return "https://api.anthropic.com/v1"
        elif kind == CloudProviderKind.GEMINI:
            return "https://generativelanguage.googleapis.com/v1beta"
        return "http://127.0.0.1:8000/v1"

    @property
    def provider_kind(self) -> ModelProviderKind:
        if self._cloud_kind == CloudProviderKind.OPENAI:
            return ModelProviderKind.CLOUD_OPENAI
        elif self._cloud_kind == CloudProviderKind.ANTHROPIC:
            return ModelProviderKind.CLOUD_ANTHROPIC
        elif self._cloud_kind == CloudProviderKind.GEMINI:
            return ModelProviderKind.CLOUD_GEMINI
        return ModelProviderKind.CLOUD

    @property
    def cloud_kind(self) -> CloudProviderKind:
        return self._cloud_kind

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def is_configured(self) -> bool:
        """Check whether credentials are provided without exposing them."""
        return bool(self._api_key and len(self._api_key.strip()) > 0)

    @property
    def auth_status(self) -> CloudAuthStatus:
        """Return current authentication configuration state as property."""
        return self.get_auth_status()

    def get_auth_status(self) -> CloudAuthStatus:
        """Return current authentication configuration state."""
        if not self.is_configured:
            return CloudAuthStatus.NOT_CONFIGURED
        return CloudAuthStatus.AUTHENTICATED

    async def health_check(self) -> ProviderHealth:
        """Perform a lightweight non-inference connectivity check."""
        if not self.is_configured:
            return HealthEvaluator.create_unavailable(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                reason=f"Cloud provider '{self._cloud_kind.value}' is not configured (missing credentials)",
                metadata={"auth_status": CloudAuthStatus.NOT_CONFIGURED.value, "cloud_kind": self._cloud_kind.value},
            )

        headers = {}
        if self._cloud_kind in (CloudProviderKind.OPENAI, CloudProviderKind.CUSTOM_OPENAI_COMPATIBLE):
            headers["Authorization"] = f"Bearer {self._api_key}"
            probe_url = f"{self._endpoint}/models" if not self._endpoint.endswith("/models") else self._endpoint
        elif self._cloud_kind == CloudProviderKind.ANTHROPIC:
            headers["x-api-key"] = self._api_key or ""
            headers["anthropic-version"] = "2023-06-01"
            probe_url = self._endpoint
        else:
            probe_url = self._endpoint

        try:
            start_ns = asyncio.get_event_loop().time()
            response = await self._client.get(probe_url, headers=headers, timeout=self._connect_timeout)
            latency_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0

            if response.status_code in (200, 404, 405):  # 200 or active server responding
                return HealthEvaluator.create_healthy(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    latency_ms=latency_ms,
                    diagnostic_message=f"Cloud provider '{self._cloud_kind.value}' reachable and authenticated",
                    metadata={"auth_status": CloudAuthStatus.AUTHENTICATED.value, "cloud_kind": self._cloud_kind.value},
                )
            elif response.status_code in (401, 403):
                return HealthEvaluator.create_unavailable(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    reason=f"Authentication failed for cloud provider '{self._cloud_kind.value}' (HTTP {response.status_code})",
                    metadata={"auth_status": CloudAuthStatus.ERROR.value, "cloud_kind": self._cloud_kind.value},
                )
            else:
                return HealthEvaluator.create_error(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    error_message=f"Cloud provider '{self._cloud_kind.value}' returned HTTP {response.status_code}",
                    metadata={"auth_status": CloudAuthStatus.AUTHENTICATED.value, "cloud_kind": self._cloud_kind.value},
                )

        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            return HealthEvaluator.create_unavailable(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                reason=f"Cannot connect to cloud provider '{self._cloud_kind.value}' at {self._endpoint}: {ex}",
                metadata={"auth_status": CloudAuthStatus.UNREACHABLE.value, "cloud_kind": self._cloud_kind.value},
            )
        except httpx.TimeoutException as ex:
            return HealthEvaluator.create_unavailable(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                reason=f"Connection timed out for cloud provider '{self._cloud_kind.value}' at {self._endpoint}: {ex}",
                metadata={"auth_status": CloudAuthStatus.UNREACHABLE.value, "cloud_kind": self._cloud_kind.value},
            )
        except Exception as ex:
            return HealthEvaluator.create_error(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                error_message=f"Health probe error for cloud provider '{self._cloud_kind.value}': {ex}",
                metadata={"auth_status": CloudAuthStatus.ERROR.value, "cloud_kind": self._cloud_kind.value},
            )

    async def discover_models(self) -> List[ModelDescriptor]:
        """Discover remote models available through this cloud provider."""
        if not self.is_configured:
            logger.debug("Cloud provider %s not configured; returning empty discovery list", self._cloud_kind.value)
            return []

        # If it's a standard cloud provider, return the validated curated catalog
        curated = CURATED_CLOUD_CATALOGS.get(self._cloud_kind)
        if curated:
            descriptors: List[ModelDescriptor] = []
            for item in curated:
                m_id = item["id"]
                stable_id = f"cloud:{self._cloud_kind.value.lower()}:{m_id}"
                desc = ModelDescriptor(
                    model_id=stable_id,
                    provider=self.provider_kind,
                    provider_model_name=m_id,
                    display_name=item["name"],
                    source_type=ModelSourceType.CLOUD_PROVIDER,
                    status=ModelStatus.AVAILABLE,
                    capabilities=item["capabilities"],
                    context_window=item.get("context_window"),
                    family=item.get("family"),
                    local_or_remote="remote",
                    endpoint=self._endpoint,
                    discovered_at_utc=datetime.now(timezone.utc),
                    metadata={"cloud_kind": self._cloud_kind.value},
                )
                descriptors.append(desc)
            return descriptors

        # For custom OpenAI-compatible endpoints, query /models if available
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._endpoint}/models" if not self._endpoint.endswith("/models") else self._endpoint
        try:
            resp = await self._client.get(url, headers=headers, timeout=self._request_timeout)
            if resp.status_code == 200:
                data = resp.json()
                raw_models = data.get("data", [])
                descriptors = []
                for item in raw_models:
                    m_id = item.get("id", "")
                    if not m_id:
                        continue
                    stable_id = f"cloud:custom:{m_id}"
                    desc = ModelDescriptor(
                        model_id=stable_id,
                        provider=ModelProviderKind.CLOUD,
                        provider_model_name=m_id,
                        display_name=m_id,
                        source_type=ModelSourceType.CLOUD_PROVIDER,
                        status=ModelStatus.AVAILABLE,
                        capabilities=infer_capabilities(m_id),
                        local_or_remote="remote",
                        endpoint=self._endpoint,
                        discovered_at_utc=datetime.now(timezone.utc),
                        metadata=item,
                    )
                    descriptors.append(desc)
                return descriptors
        except Exception as ex:
            logger.warning("Failed to query custom cloud endpoint models at %s: %s", self._endpoint, ex)

        return []

    async def get_model(self, provider_model_name: str) -> Optional[ModelDescriptor]:
        models = await self.discover_models()
        for m in models:
            if m.provider_model_name == provider_model_name:
                return m
        return None

    async def get_model_status(self, provider_model_name: str) -> ModelStatus:
        if not self.is_configured:
            return ModelStatus.UNAVAILABLE
        health = await self.health_check()
        return ModelStatus.AVAILABLE if health.status == ProviderHealthStatus.HEALTHY else ModelStatus.UNREACHABLE

    async def generate(self, provider_model_name: str, request: ModelGenerateRequest) -> ModelGenerateResponse:
        """Call cloud completion endpoint."""
        if not self.is_configured:
            raise RuntimeError(f"Cloud provider '{self._cloud_kind.value}' is not configured with an API key")

        url = f"{self._endpoint}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {
            "model": provider_model_name,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature or 0.7,
            "max_tokens": request.max_tokens or 512,
        }
        start_ns = asyncio.get_event_loop().time()
        response = await self._client.post(url, headers=headers, json=payload, timeout=self._request_timeout)
        duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0

        if response.status_code != 200:
            raise RuntimeError(f"Cloud completion failed (HTTP {response.status_code}): {response.text[:200]}")

        data = response.json()
        choices = data.get("choices", [])
        content = ""
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
        usage = data.get("usage", {})

        return ModelGenerateResponse(
            model_id=f"cloud:{self._cloud_kind.value.lower()}:{provider_model_name}",
            content=content,
            done=True,
            total_duration_ms=round(duration_ms, 2),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw_response=data,
        )

    async def chat(self, provider_model_name: str, request: ModelChatRequest) -> ModelGenerateResponse:
        """Call cloud chat completions endpoint."""
        if not self.is_configured:
            raise RuntimeError(f"Cloud provider '{self._cloud_kind.value}' is not configured with an API key")

        url = f"{self._endpoint}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        payload = {
            "model": provider_model_name,
            "messages": messages,
            "temperature": request.temperature or 0.7,
            "max_tokens": request.max_tokens or 512,
        }
        start_ns = asyncio.get_event_loop().time()
        response = await self._client.post(url, headers=headers, json=payload, timeout=self._request_timeout)
        duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0

        if response.status_code != 200:
            raise RuntimeError(f"Cloud chat failed (HTTP {response.status_code}): {response.text[:200]}")

        data = response.json()
        choices = data.get("choices", [])
        content = ""
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
        usage = data.get("usage", {})

        return ModelGenerateResponse(
            model_id=f"cloud:{self._cloud_kind.value.lower()}:{provider_model_name}",
            content=content,
            done=True,
            total_duration_ms=round(duration_ms, 2),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw_response=data,
        )

    async def load_model(self, provider_model_name: str) -> bool:
        """Cloud models are hosted remotely and require no local memory loading."""
        return True

    async def unload_model(self, provider_model_name: str) -> bool:
        return True

    async def shutdown(self) -> None:
        if self._own_client and not self._client.is_closed:
            await self._client.aclose()
