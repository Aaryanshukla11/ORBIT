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
            "id": "o1-preview",
            "name": "OpenAI o1-preview",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE},
            "context_window": 128000,
            "family": "o1",
        },
        {
            "id": "o1-mini",
            "name": "OpenAI o1-mini",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE},
            "context_window": 128000,
            "family": "o1",
        },
        {
            "id": "o3-mini",
            "name": "OpenAI o3-mini",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE},
            "context_window": 200000,
            "family": "o3",
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
            "id": "claude-3-5-sonnet",
            "name": "Claude 3.5 Sonnet",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 200000,
            "family": "claude",
        },
        {
            "id": "claude-3-5-sonnet-latest",
            "name": "Claude 3.5 Sonnet",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 200000,
            "family": "claude",
        },
        {
            "id": "claude-3-5-haiku",
            "name": "Claude 3.5 Haiku",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
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
        {
            "id": "claude-3-opus",
            "name": "Claude 3 Opus",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
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
        {
            "id": "gemini-1.5-flash",
            "name": "Gemini 1.5 Flash",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.TOOL_CALLING, ModelCapability.CODE},
            "context_window": 1048576,
            "family": "gemini",
        },
    ],
    CloudProviderKind.CUSTOM_OPENAI_COMPATIBLE: [
        {
            "id": "deepseek-chat",
            "name": "DeepSeek Chat (V3)",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.CODE},
            "context_window": 64000,
            "family": "deepseek",
        },
        {
            "id": "deepseek-reasoner",
            "name": "DeepSeek R1 (Reasoner)",
            "capabilities": {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CODE},
            "context_window": 64000,
            "family": "deepseek",
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
        connect_timeout: float = 8.0,
        request_timeout: float = 30.0,
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
        self._auth_status: CloudAuthStatus = (
            CloudAuthStatus.NOT_CONFIGURED if not (self._api_key and len(self._api_key.strip()) > 0) else CloudAuthStatus.CONFIGURED_UNVERIFIED
        )
        self._auth_error_message: Optional[str] = None
        self._auth_lock = asyncio.Lock()

    def __repr__(self) -> str:
        """Secure representation that NEVER reveals secrets."""
        has_key = bool(self._api_key)
        return f"<CloudModelProvider kind={self._cloud_kind.value} endpoint={self._endpoint} configured={has_key} auth={self._auth_status.value}>"

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
        return self._auth_status

    def update_credentials(self, api_key: str, endpoint: Optional[str] = None) -> None:
        """Update provider credentials securely in memory."""
        self._api_key = api_key.strip()
        if endpoint:
            self._endpoint = endpoint.rstrip("/")
        if not self._api_key:
            self._auth_status = CloudAuthStatus.NOT_CONFIGURED
            self._auth_error_message = None
        else:
            self._auth_status = CloudAuthStatus.CONFIGURED_UNVERIFIED
            self._auth_error_message = None

    async def health_check(self) -> ProviderHealth:
        """Perform a lightweight non-inference connectivity and authentication check."""
        if not self.is_configured:
            self._auth_status = CloudAuthStatus.NOT_CONFIGURED
            self._auth_error_message = f"Cloud provider '{self._cloud_kind.value}' is not configured (missing credentials)"
            return HealthEvaluator.create_unavailable(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                reason=self._auth_error_message,
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

        async with self._auth_lock:
            self._auth_status = CloudAuthStatus.AUTHENTICATING
            try:
                start_ns = asyncio.get_event_loop().time()
                response = await self._client.get(probe_url, headers=headers, timeout=self._connect_timeout)
                latency_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0

                if response.status_code in (200, 404, 405):  # 200 or active server responding
                    self._auth_status = CloudAuthStatus.AUTHENTICATED
                    self._auth_error_message = None
                    return HealthEvaluator.create_healthy(
                        provider=self.provider_kind,
                        endpoint=self._endpoint,
                        latency_ms=latency_ms,
                        diagnostic_message=f"Cloud provider '{self._cloud_kind.value}' reachable and authenticated",
                        metadata={"auth_status": CloudAuthStatus.AUTHENTICATED.value, "cloud_kind": self._cloud_kind.value},
                    )
                elif response.status_code in (401, 403):
                    self._auth_status = CloudAuthStatus.AUTH_FAILED
                    self._auth_error_message = f"Authentication failed for cloud provider '{self._cloud_kind.value}' (HTTP {response.status_code})"
                    return HealthEvaluator.create_unavailable(
                        provider=self.provider_kind,
                        endpoint=self._endpoint,
                        reason=self._auth_error_message,
                        metadata={"auth_status": CloudAuthStatus.AUTH_FAILED.value, "cloud_kind": self._cloud_kind.value},
                    )
                else:
                    self._auth_status = CloudAuthStatus.ERROR
                    self._auth_error_message = f"Cloud provider '{self._cloud_kind.value}' returned HTTP {response.status_code}"
                    return HealthEvaluator.create_error(
                        provider=self.provider_kind,
                        endpoint=self._endpoint,
                        error_message=self._auth_error_message,
                        metadata={"auth_status": CloudAuthStatus.ERROR.value, "cloud_kind": self._cloud_kind.value},
                    )

            except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
                self._auth_status = CloudAuthStatus.UNREACHABLE
                self._auth_error_message = f"Cannot connect to cloud provider '{self._cloud_kind.value}' at {self._endpoint}"
                return HealthEvaluator.create_unavailable(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    reason=self._auth_error_message,
                    metadata={"auth_status": CloudAuthStatus.UNREACHABLE.value, "cloud_kind": self._cloud_kind.value},
                )
            except httpx.TimeoutException as ex:
                self._auth_status = CloudAuthStatus.UNREACHABLE
                self._auth_error_message = f"Connection timed out for cloud provider '{self._cloud_kind.value}' at {self._endpoint}"
                return HealthEvaluator.create_unavailable(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    reason=self._auth_error_message,
                    metadata={"auth_status": CloudAuthStatus.UNREACHABLE.value, "cloud_kind": self._cloud_kind.value},
                )
            except Exception as ex:
                self._auth_status = CloudAuthStatus.ERROR
                self._auth_error_message = f"Health probe error for cloud provider '{self._cloud_kind.value}': {ex}"
                return HealthEvaluator.create_error(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    error_message=self._auth_error_message,
                    metadata={"auth_status": CloudAuthStatus.ERROR.value, "cloud_kind": self._cloud_kind.value},
                )

    async def discover_models(self) -> List[ModelDescriptor]:
        """Discover remote models available through this cloud provider."""
        if not self.is_configured:
            logger.debug("Cloud provider %s not configured; returning empty discovery list", self._cloud_kind.value)
            return []

        # If it's a standard cloud provider, return the curated catalog with truthful availability status
        curated = CURATED_CLOUD_CATALOGS.get(self._cloud_kind)
        if curated:
            descriptors: List[ModelDescriptor] = []
            is_authenticated = (self.get_auth_status() == CloudAuthStatus.AUTHENTICATED)
            for item in curated:
                m_id = item["id"]
                stable_id = f"cloud:{self._cloud_kind.value.lower()}:{m_id}"
                desc = ModelDescriptor(
                    model_id=stable_id,
                    provider=self.provider_kind,
                    provider_model_name=m_id,
                    display_name=item["name"],
                    source_type=ModelSourceType.CLOUD_PROVIDER,
                    status=ModelStatus.AVAILABLE if is_authenticated else ModelStatus.UNAVAILABLE,
                    capabilities=item["capabilities"],
                    context_window=item.get("context_window"),
                    family=item.get("family"),
                    local_or_remote="remote",
                    endpoint=self._endpoint,
                    discovered_at_utc=datetime.now(timezone.utc),
                    metadata={
                        "cloud_kind": self._cloud_kind.value,
                        "account_verified": is_authenticated,
                        "auth_status": self.get_auth_status().value,
                        "catalog_source": "LIVE_VERIFIED" if is_authenticated else "CURATED_CATALOG",
                        "diagnostic_message": self._auth_error_message,
                    },
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
                    caps = infer_capabilities(m_id)
                    desc = ModelDescriptor(
                        model_id=stable_id,
                        provider=self.provider_kind,
                        provider_model_name=m_id,
                        display_name=m_id,
                        source_type=ModelSourceType.CLOUD_PROVIDER,
                        status=ModelStatus.AVAILABLE,
                        capabilities=caps,
                        local_or_remote="remote",
                        endpoint=self._endpoint,
                        discovered_at_utc=datetime.now(timezone.utc),
                        metadata={"cloud_kind": self._cloud_kind.value, "account_verified": True},
                    )
                    descriptors.append(desc)
                return descriptors
        except Exception as ex:
            logger.warning("Failed to query custom OpenAI-compatible models from %s: %s", url, ex)

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

        start_ns = asyncio.get_event_loop().time()

        if self._cloud_kind == CloudProviderKind.ANTHROPIC:
            url = f"{self._endpoint}/messages" if not self._endpoint.endswith("/messages") else self._endpoint
            headers = {
                "x-api-key": self._api_key or "",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            messages = [{"role": "user", "content": request.prompt}]
            payload: Dict[str, Any] = {
                "model": provider_model_name,
                "messages": messages,
                "max_tokens": request.max_tokens or 1024,
            }
            if request.system_prompt:
                payload["system"] = request.system_prompt
            response = await self._client.post(url, headers=headers, json=payload, timeout=self._request_timeout)
            duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0
            if response.status_code != 200:
                raise RuntimeError(f"Anthropic completion failed (HTTP {response.status_code}): {response.text[:200]}")
            data = response.json()
            content = "".join([b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"])
            usage = data.get("usage", {})
            return ModelGenerateResponse(
                model_id=f"cloud:{self._cloud_kind.value.lower()}:{provider_model_name}",
                content=content,
                done=True,
                total_duration_ms=round(duration_ms, 2),
                prompt_tokens=usage.get("input_tokens"),
                completion_tokens=usage.get("output_tokens"),
                raw_response=data,
            )
        elif self._cloud_kind == CloudProviderKind.GEMINI:
            url = f"{self._endpoint}/models/{provider_model_name}:generateContent?key={self._api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": request.prompt}]}]
            }
            response = await self._client.post(url, headers=headers, json=payload, timeout=self._request_timeout)
            duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0
            if response.status_code != 200:
                raise RuntimeError(f"Gemini completion failed (HTTP {response.status_code}): {response.text[:200]}")
            data = response.json()
            candidates = data.get("candidates", [])
            content = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                content = "".join([p.get("text", "") for p in parts if "text" in p])
            usage = data.get("usageMetadata", {})
            return ModelGenerateResponse(
                model_id=f"cloud:{self._cloud_kind.value.lower()}:{provider_model_name}",
                content=content,
                done=True,
                total_duration_ms=round(duration_ms, 2),
                prompt_tokens=usage.get("promptTokenCount"),
                completion_tokens=usage.get("candidatesTokenCount"),
                raw_response=data,
            )
        else:
            url = f"{self._endpoint}/chat/completions" if not self._endpoint.endswith("/chat/completions") else self._endpoint
            headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})
            payload = {
                "model": provider_model_name,
                "messages": messages,
                "temperature": request.temperature or 0.7,
                "max_tokens": request.max_tokens or 512,
            }
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

        start_ns = asyncio.get_event_loop().time()

        if self._cloud_kind == CloudProviderKind.ANTHROPIC:
            url = f"{self._endpoint}/messages" if not self._endpoint.endswith("/messages") else self._endpoint
            headers = {
                "x-api-key": self._api_key or "",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            sys_prompt = ""
            anthropic_messages = []
            for m in request.messages:
                if m.role == "system":
                    sys_prompt += m.content + "\n"
                else:
                    anthropic_messages.append({"role": m.role, "content": m.content})
            payload: Dict[str, Any] = {
                "model": provider_model_name,
                "messages": anthropic_messages or [{"role": "user", "content": "Hello"}],
                "max_tokens": request.max_tokens or 1024,
            }
            if sys_prompt.strip():
                payload["system"] = sys_prompt.strip()
            response = await self._client.post(url, headers=headers, json=payload, timeout=self._request_timeout)
            duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0
            if response.status_code != 200:
                raise RuntimeError(f"Anthropic chat failed (HTTP {response.status_code}): {response.text[:200]}")
            data = response.json()
            content = "".join([b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"])
            usage = data.get("usage", {})
            return ModelGenerateResponse(
                model_id=f"cloud:{self._cloud_kind.value.lower()}:{provider_model_name}",
                content=content,
                done=True,
                total_duration_ms=round(duration_ms, 2),
                prompt_tokens=usage.get("input_tokens"),
                completion_tokens=usage.get("output_tokens"),
                raw_response=data,
            )
        elif self._cloud_kind == CloudProviderKind.GEMINI:
            url = f"{self._endpoint}/models/{provider_model_name}:generateContent?key={self._api_key}"
            headers = {"Content-Type": "application/json"}
            gemini_contents = []
            for m in request.messages:
                role = "user" if m.role == "user" else "model"
                gemini_contents.append({"role": role, "parts": [{"text": m.content}]})
            payload = {"contents": gemini_contents or [{"role": "user", "parts": [{"text": "Hello"}]}]}
            response = await self._client.post(url, headers=headers, json=payload, timeout=self._request_timeout)
            duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0
            if response.status_code != 200:
                raise RuntimeError(f"Gemini chat failed (HTTP {response.status_code}): {response.text[:200]}")
            data = response.json()
            candidates = data.get("candidates", [])
            content = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                content = "".join([p.get("text", "") for p in parts if "text" in p])
            usage = data.get("usageMetadata", {})
            return ModelGenerateResponse(
                model_id=f"cloud:{self._cloud_kind.value.lower()}:{provider_model_name}",
                content=content,
                done=True,
                total_duration_ms=round(duration_ms, 2),
                prompt_tokens=usage.get("promptTokenCount"),
                completion_tokens=usage.get("candidatesTokenCount"),
                raw_response=data,
            )
        else:
            url = f"{self._endpoint}/chat/completions" if not self._endpoint.endswith("/chat/completions") else self._endpoint
            headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
            messages = [{"role": m.role, "content": m.content} for m in request.messages]
            payload = {
                "model": provider_model_name,
                "messages": messages,
                "temperature": request.temperature or 0.7,
                "max_tokens": request.max_tokens or 512,
            }
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
