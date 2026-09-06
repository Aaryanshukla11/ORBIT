"""Remote & Cloud Provider Runtime Adapters (Milestone M1.9 Step 4).

Implements OpenAICompatibleRuntimeAdapter for remote API endpoints,
cloud providers (OpenAI, Anthropic, Gemini, Groq, Mistral), and local OpenAI-compatible
runtimes (LM Studio, vLLM, LocalAI).

SECURITY INVARIANT:
API keys, tokens, and authorization headers are NEVER logged, serialized, or emitted.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Optional
import httpx

from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import (
    ModelRuntimeHealth,
    ModelRuntimeInfo,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    RuntimeInitializationResult,
)
from orbit.runtime.models.models import (
    CloudAuthStatus,
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.cloud import CloudModelProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleRuntimeAdapter(BaseModelRuntime):
    """Remote and cloud runtime adapter communicating via OpenAI-compatible REST API endpoints."""

    def __init__(
        self,
        descriptor: ModelDescriptor,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[CloudModelProvider] = None,
    ) -> None:
        super().__init__(descriptor)
        self._api_key = api_key
        self._base_url = (base_url or descriptor.endpoint or "https://api.openai.com/v1").rstrip("/")
        self._provider = provider
        self._runtime_kind = ModelRuntimeKind.REMOTE
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def runtime_kind(self) -> ModelRuntimeKind:
        return self._runtime_kind

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
            )
        return self._client

    async def initialize(
        self,
        timeout_seconds: float = 30.0,
        preload_weights: bool = True,
    ) -> RuntimeInitializationResult:
        """Perform lazy initialization and credentials verification."""
        start_time = time.perf_counter()
        self._status = ModelRuntimeStatus.INITIALIZING

        # 1. If wrapped by CloudModelProvider, check provider auth status
        if self._provider:
            if self._provider.auth_status == CloudAuthStatus.NOT_CONFIGURED:
                self._status = ModelRuntimeStatus.UNAVAILABLE
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return RuntimeInitializationResult(
                    is_success=False,
                    model_id=self.model_id,
                    status=self._status,
                    duration_ms=duration_ms,
                    error_message=f"Cloud credentials not configured for provider {self._descriptor.provider.value}",
                )

        # 2. Check if API key or local endpoint is reachable
        try:
            health = await self.health_check()
            if not health.is_healthy:
                self._status = ModelRuntimeStatus.UNAVAILABLE
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return RuntimeInitializationResult(
                    is_success=False,
                    model_id=self.model_id,
                    status=self._status,
                    duration_ms=duration_ms,
                    error_message=health.diagnostic_message or "Endpoint unreachable or unauthorized",
                )

            self._status = ModelRuntimeStatus.READY
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return RuntimeInitializationResult(
                is_success=True,
                model_id=self.model_id,
                status=self._status,
                duration_ms=duration_ms,
                metadata={"endpoint": self._base_url},
            )
        except Exception as ex:
            self._status = ModelRuntimeStatus.FAILED
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error("Initialization failed for remote model %s: %s", self.model_id, ex)
            return RuntimeInitializationResult(
                is_success=False,
                model_id=self.model_id,
                status=self._status,
                duration_ms=duration_ms,
                error_message=str(ex),
            )

    async def health_check(self) -> ModelRuntimeHealth:
        """Probe remote endpoint availability and measure roundtrip latency."""
        start = time.perf_counter()
        try:
            if self._provider:
                p_health = await self._provider.health_check()
                is_healthy = p_health.status == ProviderHealthStatus.HEALTHY
                status = ModelRuntimeStatus.READY if is_healthy else ModelRuntimeStatus.UNAVAILABLE
                if self._status == ModelRuntimeStatus.ACTIVE and is_healthy:
                    status = ModelRuntimeStatus.ACTIVE

                runtime_health = ModelRuntimeHealth(
                    model_id=self.model_id,
                    status=status,
                    is_healthy=is_healthy,
                    latency_ms=p_health.latency_ms,
                    diagnostic_message=p_health.diagnostic_message,
                    metadata={"endpoint": self._base_url},
                )
                self._last_health = runtime_health
                return runtime_health

            client = await self._get_client()
            resp = await client.get("/models")
            latency_ms = (time.perf_counter() - start) * 1000.0
            is_healthy = resp.status_code in {200, 401, 403}  # Endpoint responds
            if resp.status_code == 200:
                status = ModelRuntimeStatus.READY if self._status != ModelRuntimeStatus.ACTIVE else ModelRuntimeStatus.ACTIVE
                msg = None
            elif resp.status_code in {401, 403}:
                status = ModelRuntimeStatus.UNAVAILABLE
                is_healthy = False
                msg = "Authentication failed (invalid or missing API key)"
            else:
                status = ModelRuntimeStatus.UNAVAILABLE
                is_healthy = False
                msg = f"HTTP {resp.status_code}: {resp.reason_phrase}"

            runtime_health = ModelRuntimeHealth(
                model_id=self.model_id,
                status=status,
                is_healthy=is_healthy,
                latency_ms=latency_ms,
                diagnostic_message=msg,
                metadata={"endpoint": self._base_url},
            )
            self._last_health = runtime_health
            return runtime_health
        except Exception as ex:
            runtime_health = ModelRuntimeHealth(
                model_id=self.model_id,
                status=ModelRuntimeStatus.FAILED,
                is_healthy=False,
                latency_ms=None,
                diagnostic_message=str(ex),
            )
            self._last_health = runtime_health
            return runtime_health

    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        """Execute completion via OpenAI-compatible chat endpoint."""
        if not self.is_initialized:
            raise RuntimeError(f"Cannot generate: model '{self.model_id}' is not initialized (status: {self._status.value})")

        self._is_busy = True
        start_time = time.perf_counter()
        try:
            if self._provider:
                return await self._provider.generate(self._descriptor.provider_model_name, request)

            client = await self._get_client()
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

            payload: Dict[str, Any] = {
                "model": self._descriptor.provider_model_name,
                "messages": messages,
            }
            if request.temperature is not None:
                payload["temperature"] = request.temperature
            if request.max_tokens is not None:
                payload["max_tokens"] = request.max_tokens
            if request.stop:
                payload["stop"] = request.stop

            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})

            return ModelGenerateResponse(
                model_id=self.model_id,
                content=content,
                done=True,
                total_duration_ms=duration_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                raw_response=data,
            )
        finally:
            self._is_busy = False

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        """Execute chat conversation via OpenAI-compatible endpoint."""
        if not self.is_initialized:
            raise RuntimeError(f"Cannot chat: model '{self.model_id}' is not initialized (status: {self._status.value})")

        self._is_busy = True
        start_time = time.perf_counter()
        try:
            if self._provider:
                return await self._provider.chat(self._descriptor.provider_model_name, request)

            client = await self._get_client()
            messages = [
                {"role": m.role, "content": m.content}
                for m in request.messages
            ]
            payload: Dict[str, Any] = {
                "model": self._descriptor.provider_model_name,
                "messages": messages,
            }
            if request.temperature is not None:
                payload["temperature"] = request.temperature
            if request.max_tokens is not None:
                payload["max_tokens"] = request.max_tokens
            if request.stop:
                payload["stop"] = request.stop

            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})

            return ModelGenerateResponse(
                model_id=self.model_id,
                content=content,
                done=True,
                total_duration_ms=duration_ms,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                raw_response=data,
            )
        finally:
            self._is_busy = False

    async def shutdown(self) -> None:
        """Close connection pool and stop runtime."""
        self._status = ModelRuntimeStatus.STOPPED
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        logger.info("OpenAICompatibleRuntimeAdapter for %s stopped", self.model_id)
