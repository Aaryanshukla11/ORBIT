"""LM Studio Local Model Provider Implementation (Milestone M1.9 Step 2).

Integrates with LM Studio's local OpenAI-compatible API daemon (default http://127.0.0.1:1234).
Honors connection timeouts, isolates network failures, and queries genuine model lists.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import httpx

from orbit.runtime.models.capabilities import infer_capabilities
from orbit.runtime.models.health import HealthEvaluator, measure_roundtrip_latency
from orbit.runtime.models.models import (
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


class LMStudioProviderError(Exception):
    """Base exception for LMStudioProvider operations."""
    pass


class LMStudioUnavailableError(LMStudioProviderError):
    """Raised when LM Studio local server is unavailable."""
    pass


class LMStudioProvider(ModelProvider):
    """Production provider for LM Studio local server."""

    DEFAULT_ENDPOINT = "http://127.0.0.1:1234"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        host: str = "127.0.0.1",
        port: int = 1234,
        connect_timeout: float = 1.0,
        request_timeout: float = 10.0,
        timeout_seconds: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if endpoint is not None:
            self._endpoint = endpoint.rstrip("/")
        else:
            self._endpoint = f"http://{host}:{port}".rstrip("/")
        self._connect_timeout = timeout_seconds if timeout_seconds is not None else connect_timeout
        self._request_timeout = timeout_seconds if timeout_seconds is not None else request_timeout
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self._request_timeout, connect=self._connect_timeout),
        )
        self._own_client = client is None

    @property
    def provider_kind(self) -> ModelProviderKind:
        return ModelProviderKind.LM_STUDIO

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def health_check(self) -> ProviderHealth:
        """Probe LM Studio daemon connectivity and measure latency via /v1/models."""
        url = f"{self._endpoint}/v1/models"

        try:
            async with measure_roundtrip_latency() as timing:
                response = await self._client.get(url, timeout=self._connect_timeout)

            latency_ms = timing.get("elapsed_ms") or 0.0
            if response.status_code == 200:
                return HealthEvaluator.create_healthy(
                    provider=ModelProviderKind.LM_STUDIO,
                    endpoint=self._endpoint,
                    latency_ms=latency_ms,
                    diagnostic_message=f"LM Studio local server is online and reachable",
                )
            else:
                return HealthEvaluator.create_error(
                    provider=ModelProviderKind.LM_STUDIO,
                    endpoint=self._endpoint,
                    error_message=f"LM Studio returned HTTP {response.status_code}: {response.text[:200]}",
                )

        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            return HealthEvaluator.create_unavailable(
                provider=ModelProviderKind.LM_STUDIO,
                endpoint=self._endpoint,
                reason=f"Cannot connect to LM Studio at {self._endpoint}: connection refused or unreachable ({ex})",
            )
        except httpx.TimeoutException as ex:
            return HealthEvaluator.create_unavailable(
                provider=ModelProviderKind.LM_STUDIO,
                endpoint=self._endpoint,
                reason=f"LM Studio health probe timed out at {self._endpoint}: {ex}",
            )
        except Exception as ex:
            return HealthEvaluator.create_error(
                provider=ModelProviderKind.LM_STUDIO,
                endpoint=self._endpoint,
                error_message=f"LM Studio health probe error: {ex}",
            )

    async def discover_models(self) -> List[ModelDescriptor]:
        """Query LM Studio /v1/models and convert into ModelDescriptors."""
        url = f"{self._endpoint}/v1/models"
        try:
            response = await self._client.get(url, timeout=self._request_timeout)
            if response.status_code != 200:
                logger.warning("LM Studio /v1/models returned HTTP %d: %s", response.status_code, response.text[:200])
                return []

            data = response.json()
            raw_models = data.get("data", [])
            descriptors: List[ModelDescriptor] = []

            for item in raw_models:
                m_id = item.get("id", "")
                if not m_id:
                    continue

                display_name = m_id.split("/")[-1]
                capabilities = infer_capabilities(m_id)
                stable_id = f"lm_studio:{m_id}"

                descriptor = ModelDescriptor(
                    model_id=stable_id,
                    provider=ModelProviderKind.LM_STUDIO,
                    provider_model_name=m_id,
                    display_name=display_name,
                    source_type=ModelSourceType.LOCAL_RUNTIME,
                    status=ModelStatus.AVAILABLE,
                    capabilities=capabilities,
                    endpoint=self._endpoint,
                    local_or_remote="local",
                    discovered_at_utc=datetime.now(timezone.utc),
                    metadata=item,
                )
                descriptors.append(descriptor)

            logger.info("LM Studio discovery: found %d models at %s", len(descriptors), self._endpoint)
            return descriptors

        except (httpx.ConnectError, httpx.ConnectTimeout):
            logger.debug("LM Studio daemon not reachable at %s (skipped safely)", self._endpoint)
            return []
        except Exception as ex:
            logger.warning("Error discovering LM Studio models: %s", ex)
            return []

    async def get_model(self, provider_model_name: str) -> Optional[ModelDescriptor]:
        models = await self.discover_models()
        for m in models:
            if m.provider_model_name == provider_model_name:
                return m
        return None

    async def get_model_status(self, provider_model_name: str) -> ModelStatus:
        health = await self.health_check()
        if health.status != ProviderHealthStatus.HEALTHY:
            return ModelStatus.UNAVAILABLE
        model = await self.get_model(provider_model_name)
        return model.status if model else ModelStatus.UNAVAILABLE

    async def generate(self, provider_model_name: str, request: ModelGenerateRequest) -> ModelGenerateResponse:
        """Call LM Studio /v1/completions."""
        url = f"{self._endpoint}/v1/completions"
        payload = {
            "model": provider_model_name,
            "prompt": request.prompt,
            "temperature": request.temperature or 0.7,
            "max_tokens": request.max_tokens or 512,
            "stop": request.stop,
        }
        start_ns = asyncio.get_event_loop().time()
        response = await self._client.post(url, json=payload, timeout=self._request_timeout)
        duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0

        if response.status_code != 200:
            raise RuntimeError(f"LM Studio completion failed (HTTP {response.status_code}): {response.text[:200]}")

        data = response.json()
        choices = data.get("choices", [])
        text = choices[0].get("text", "") if choices else ""
        usage = data.get("usage", {})

        return ModelGenerateResponse(
            model_id=f"lm_studio:{provider_model_name}",
            content=text,
            done=True,
            total_duration_ms=round(duration_ms, 2),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw_response=data,
        )

    async def chat(self, provider_model_name: str, request: ModelChatRequest) -> ModelGenerateResponse:
        """Call LM Studio /v1/chat/completions."""
        url = f"{self._endpoint}/v1/chat/completions"
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        payload = {
            "model": provider_model_name,
            "messages": messages,
            "temperature": request.temperature or 0.7,
            "max_tokens": request.max_tokens or 512,
            "stop": request.stop,
        }
        start_ns = asyncio.get_event_loop().time()
        response = await self._client.post(url, json=payload, timeout=self._request_timeout)
        duration_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0

        if response.status_code != 200:
            raise RuntimeError(f"LM Studio chat failed (HTTP {response.status_code}): {response.text[:200]}")

        data = response.json()
        choices = data.get("choices", [])
        content = ""
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
        usage = data.get("usage", {})

        return ModelGenerateResponse(
            model_id=f"lm_studio:{provider_model_name}",
            content=content,
            done=True,
            total_duration_ms=round(duration_ms, 2),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw_response=data,
        )

    async def load_model(
        self,
        provider_model_name: str,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """LM Studio automatically loads models on request or keeps active loaded model."""
        return True

    async def unload_model(
        self,
        provider_model_name: str,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        return True

    async def shutdown(self) -> None:
        if self._own_client and not self._client.is_closed:
            await self._client.aclose()
