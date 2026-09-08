"""Production-grade Ollama Model Provider (Milestone M1.9 Step 1).

Interacts directly with genuine local Ollama HTTP REST API (default http://127.0.0.1:11434):
- Detects whether the daemon is actively running
- Discovers installed local GGUF models without fabrication
- Preserves exact model strings, parameter scales, and quantization levels
- Exposes generate, chat, load, unload, and microsecond health checking
- Handles network unavailability, timeouts, and connection errors truthfully and fail-safe
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time
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
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.base import ModelProvider

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_CONNECT_TIMEOUT_SEC = 5.0
DEFAULT_READ_TIMEOUT_SEC = 60.0


class OllamaProviderError(Exception):
    """Base exception for Ollama provider failures."""
    pass


class OllamaUnavailableError(OllamaProviderError):
    """Raised when the Ollama service is offline or unreachable."""
    pass


class OllamaModelNotFoundError(OllamaProviderError):
    """Raised when a requested model is not installed in the Ollama runtime."""
    pass


class OllamaTimeoutError(OllamaProviderError):
    """Raised when an operation against Ollama exceeds the timeout threshold."""
    pass


class OllamaProvider(ModelProvider):
    """Real implementation of ModelProvider for local Ollama runtimes."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SEC,
        read_timeout: float = DEFAULT_READ_TIMEOUT_SEC,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if endpoint is not None:
            raw_endpoint = endpoint
        elif host is not None and port is not None:
            raw_endpoint = f"http://{host}:{port}"
        else:
            raw_endpoint = os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_ENDPOINT

        # Normalize endpoint (strip trailing slashes)
        self._endpoint = raw_endpoint.rstrip("/")
        if not self._endpoint.startswith(("http://", "https://")):
            self._endpoint = f"http://{self._endpoint}"

        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._client: Optional[httpx.AsyncClient] = client
        self._last_health: Optional[ProviderHealth] = None

    @property
    def provider_kind(self) -> ModelProviderKind:
        return ModelProviderKind.OLLAMA

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or initialize the persistent async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._endpoint,
                timeout=httpx.Timeout(
                    connect=self._connect_timeout,
                    read=self._read_timeout,
                    write=10.0,
                    pool=5.0,
                ),
            )
        return self._client

    async def health_check(self) -> ProviderHealth:
        """Probe the Ollama daemon for reachability, version info, and latency."""
        client = await self._get_client()
        try:
            async with measure_roundtrip_latency() as timing:
                response = await client.get("/api/version", timeout=self._connect_timeout)
            
            if response.status_code == 200:
                data = response.json()
                version = data.get("version", "unknown")
                health = HealthEvaluator.create_healthy(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    latency_ms=timing["elapsed_ms"] or 0.0,
                    version_info=f"Ollama v{version}",
                    diagnostic_message="Ollama runtime is reachable and responsive",
                    metadata={"version": version},
                )
            else:
                health = HealthEvaluator.create_error(
                    provider=self.provider_kind,
                    endpoint=self._endpoint,
                    error_message=f"Ollama returned HTTP {response.status_code}: {response.text}",
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            health = HealthEvaluator.create_unavailable(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                reason=f"Cannot connect to Ollama at {self._endpoint}: connection refused or timed out ({ex})",
            )
        except httpx.ReadTimeout as ex:
            health = HealthEvaluator.create_unavailable(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                reason=f"Ollama at {self._endpoint} did not respond within {self._connect_timeout}s timeout: {ex}",
            )
        except Exception as ex:
            health = HealthEvaluator.create_error(
                provider=self.provider_kind,
                endpoint=self._endpoint,
                error_message=f"Unexpected error probing Ollama health: {ex}",
            )

        self._last_health = health
        return health

    async def discover_models(self) -> List[ModelDescriptor]:
        """Query genuine installed models from `/api/tags`."""
        client = await self._get_client()
        try:
            response = await client.get("/api/tags", timeout=self._connect_timeout)
            if response.status_code != 200:
                raise OllamaProviderError(f"Failed to query /api/tags: HTTP {response.status_code} ({response.text})")
            
            data = response.json()
            models_list = data.get("models", [])
            descriptors: List[ModelDescriptor] = []

            for raw_model in models_list:
                name = raw_model.get("name") or raw_model.get("model")
                if not name:
                    continue

                details = raw_model.get("details", {})
                raw_caps = raw_model.get("capabilities", [])
                family = details.get("family") or ""

                # Infer capabilities from runtime tags and details
                capabilities = infer_capabilities(
                    provider=self.provider_kind,
                    raw_capabilities=raw_caps,
                    model_name=name,
                    family=family,
                    metadata=details,
                )

                # Context length & parameter size (truthful parsing)
                context_len = details.get("context_length")
                if context_len is not None:
                    try:
                        context_len = int(context_len)
                    except (ValueError, TypeError):
                        context_len = None

                param_size = details.get("parameter_size")
                if param_size is not None:
                    param_size = str(param_size)

                quant = details.get("quantization_level")
                if quant is not None:
                    quant = str(quant)

                size_bytes = raw_model.get("size")
                if size_bytes is not None:
                    try:
                        size_bytes = int(size_bytes)
                    except (ValueError, TypeError):
                        size_bytes = None

                digest = raw_model.get("digest")

                descriptor = ModelDescriptor(
                    model_id=f"ollama:{name}",
                    provider=self.provider_kind,
                    provider_model_name=name,
                    display_name=name,
                    status=ModelStatus.AVAILABLE,
                    capabilities=capabilities,
                    context_window=context_len,
                    parameter_size=param_size,
                    quantization_level=quant,
                    family=family or None,
                    size_bytes=size_bytes,
                    digest=digest or None,
                    local_or_remote="local",
                    endpoint=self._endpoint,
                    discovered_at_utc=datetime.now(timezone.utc),
                    last_health=self._last_health,
                    metadata={
                        "modified_at": raw_model.get("modified_at"),
                        "raw_details": details,
                        "raw_capabilities": raw_caps,
                    },
                )
                descriptors.append(descriptor)

            logger.info("Discovered %d local models from Ollama at %s", len(descriptors), self._endpoint)
            return descriptors

        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            logger.warning("Ollama service unreachable at %s: %s", self._endpoint, ex)
            raise OllamaUnavailableError(f"Ollama service unreachable at {self._endpoint}: {ex}") from ex
        except httpx.ReadTimeout as ex:
            logger.warning("Timeout querying Ollama models at %s: %s", self._endpoint, ex)
            raise OllamaTimeoutError(f"Ollama request timed out after {self._connect_timeout}s: {ex}") from ex
        except Exception as ex:
            if isinstance(ex, (OllamaUnavailableError, OllamaTimeoutError, OllamaProviderError)):
                raise
            logger.error("Error discovering models from Ollama: %s", ex)
            raise OllamaProviderError(f"Unexpected error discovering Ollama models: {ex}") from ex

    list_models = discover_models

    async def get_model(self, provider_model_name: str) -> Optional[ModelDescriptor]:
        """Fetch descriptor for a single model by name."""
        models = await self.discover_models()
        for m in models:
            if m.provider_model_name.lower() == provider_model_name.lower():
                return m
        return None

    async def get_model_status(self, provider_model_name: str) -> ModelStatus:
        """Query status of a specific model."""
        health = await self.health_check()
        if health.status != ProviderHealthStatus.HEALTHY:
            return ModelStatus.OFFLINE

        try:
            model = await self.get_model(provider_model_name)
            return model.status if model else ModelStatus.UNAVAILABLE
        except Exception:
            return ModelStatus.ERROR

    async def generate(
        self,
        provider_model_name: str,
        request: ModelGenerateRequest,
    ) -> ModelGenerateResponse:
        """Perform text generation via `/api/generate`."""
        client = await self._get_client()
        payload: Dict[str, Any] = {
            "model": provider_model_name,
            "prompt": request.prompt,
            "stream": False,
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

        options: Dict[str, Any] = dict(request.options)
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if request.stop:
            options["stop"] = request.stop
        if options:
            payload["options"] = options

        try:
            start_ns = time.perf_counter_ns()
            response = await client.post("/api/generate", json=payload, timeout=self._read_timeout)
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

            if response.status_code == 404:
                raise OllamaModelNotFoundError(f"Model '{provider_model_name}' not found on Ollama server at {self._endpoint}")
            if response.status_code != 200:
                raise OllamaProviderError(f"Ollama generation failed (HTTP {response.status_code}): {response.text}")

            data = response.json()
            content = data.get("response", "")
            done = bool(data.get("done", True))

            # Duration and tokens
            total_duration_ns = data.get("total_duration")
            total_dur_ms = (total_duration_ns / 1_000_000.0) if total_duration_ns is not None else elapsed_ms

            return ModelGenerateResponse(
                model_id=f"ollama:{provider_model_name}",
                content=content,
                done=done,
                total_duration_ms=round(total_dur_ms, 3),
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
                raw_response=data,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            raise OllamaUnavailableError(f"Ollama service unreachable at {self._endpoint}: {ex}") from ex
        except httpx.ReadTimeout as ex:
            raise OllamaTimeoutError(f"Ollama generation timed out after {self._read_timeout}s: {ex}") from ex

    async def chat(
        self,
        provider_model_name: str,
        request: ModelChatRequest,
    ) -> ModelGenerateResponse:
        """Perform structured conversational chat via `/api/chat`."""
        client = await self._get_client()
        messages: List[Dict[str, Any]] = []
        for msg in request.messages:
            m_dict: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.images:
                m_dict["images"] = msg.images
            messages.append(m_dict)

        payload: Dict[str, Any] = {
            "model": provider_model_name,
            "messages": messages,
            "stream": False,
        }

        options: Dict[str, Any] = dict(request.options)
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if request.stop:
            options["stop"] = request.stop
        if options:
            payload["options"] = options

        try:
            start_ns = time.perf_counter_ns()
            response = await client.post("/api/chat", json=payload, timeout=self._read_timeout)
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

            if response.status_code == 404:
                raise OllamaModelNotFoundError(f"Model '{provider_model_name}' not found on Ollama server at {self._endpoint}")
            if response.status_code != 200:
                raise OllamaProviderError(f"Ollama chat failed (HTTP {response.status_code}): {response.text}")

            data = response.json()
            msg_obj = data.get("message", {})
            content = msg_obj.get("content", "")
            done = bool(data.get("done", True))

            total_duration_ns = data.get("total_duration")
            total_dur_ms = (total_duration_ns / 1_000_000.0) if total_duration_ns is not None else elapsed_ms

            return ModelGenerateResponse(
                model_id=f"ollama:{provider_model_name}",
                content=content,
                done=done,
                total_duration_ms=round(total_dur_ms, 3),
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
                raw_response=data,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            raise OllamaUnavailableError(f"Ollama service unreachable at {self._endpoint}: {ex}") from ex
        except httpx.ReadTimeout as ex:
            raise OllamaTimeoutError(f"Ollama chat timed out after {self._read_timeout}s: {ex}") from ex

    async def load_model(self, provider_model_name: str) -> bool:
        """Instruct Ollama to preload model weights into VRAM."""
        client = await self._get_client()
        try:
            # An empty generate request with stream: False triggers loading without streaming overhead
            payload = {"model": provider_model_name, "prompt": "", "stream": False, "keep_alive": "5m"}
            response = await client.post("/api/generate", json=payload, timeout=3.0)
            return response.status_code == 200
        except Exception as ex:
            logger.warning("Failed to preload model %s on Ollama: %s", provider_model_name, ex)
            return False

    async def unload_model(self, provider_model_name: str) -> bool:
        """Instruct Ollama to evict model from VRAM immediately (`keep_alive=0`)."""
        client = await self._get_client()
        try:
            payload = {"model": provider_model_name, "stream": False, "keep_alive": 0}
            response = await client.post("/api/generate", json=payload, timeout=5.0)
            return response.status_code == 200
        except Exception as ex:
            logger.warning("Failed to unload model %s on Ollama: %s", provider_model_name, ex)
            return False

    async def shutdown(self) -> None:
        """Close open HTTP connections."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
