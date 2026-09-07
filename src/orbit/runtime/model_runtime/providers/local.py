"""Local Provider Runtime Adapters (Milestone M1.9 Step 4).

Implements OllamaRuntimeAdapter wrapping native local Ollama HTTP REST API.
Enforces lazy initialization: weights are not preloaded until initialize() is called.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Optional

from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import (
    ModelRuntimeHealth,
    ModelRuntimeInfo,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    RuntimeInitializationResult,
)
from orbit.runtime.models.models import (
    ModelCapability,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.ollama import (
    OllamaModelNotFoundError,
    OllamaProvider,
    OllamaUnavailableError,
)

logger = logging.getLogger(__name__)


class OllamaRuntimeAdapter(BaseModelRuntime):
    """Local runtime adapter interfacing with an Ollama daemon."""

    def __init__(
        self,
        descriptor: ModelDescriptor,
        provider: Optional[OllamaProvider] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        super().__init__(descriptor)
        self._provider = provider or OllamaProvider(endpoint=endpoint or descriptor.endpoint)
        self._runtime_kind = ModelRuntimeKind.LOCAL

    @property
    def runtime_kind(self) -> ModelRuntimeKind:
        return self._runtime_kind

    @property
    def provider(self) -> OllamaProvider:
        return self._provider

    async def initialize(
        self,
        timeout_seconds: float = 30.0,
        preload_weights: bool = True,
    ) -> RuntimeInitializationResult:
        """Perform lazy initialization and optional weight preloading."""
        start_time = time.perf_counter()
        self._status = ModelRuntimeStatus.INITIALIZING

        try:
            # 1. Health check to ensure daemon is reachable
            health = await self._provider.health_check()
            if health.status != ProviderHealthStatus.HEALTHY:
                self._status = ModelRuntimeStatus.UNAVAILABLE
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return RuntimeInitializationResult(
                    is_success=False,
                    model_id=self.model_id,
                    status=self._status,
                    duration_ms=duration_ms,
                    error_message=f"Ollama provider is not healthy: {health.diagnostic_message or health.status.value}",
                )

            # 2. Check if model is installed in Ollama
            target_name = self._descriptor.provider_model_name
            installed_models = await self._provider.discover_models()
            matched_model = None
            for m in installed_models:
                if (
                    m.provider_model_name.lower() == target_name.lower()
                    or m.model_id.lower() == self.model_id.lower()
                    or m.provider_model_name.lower() == self.model_id.split(":", 1)[-1].lower()
                    or m.model_id.split(":", 1)[-1].lower() == target_name.split(":", 1)[-1].lower()
                ):
                    matched_model = m
                    break

            if matched_model is None:
                self._status = ModelRuntimeStatus.UNAVAILABLE
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return RuntimeInitializationResult(
                    is_success=False,
                    model_id=self.model_id,
                    status=self._status,
                    duration_ms=duration_ms,
                    error_message=f"Model '{target_name}' is not installed in local Ollama instance",
                )

            # Preserve exact matched provider model name for Ollama runtime calls
            target_name = matched_model.provider_model_name
            self._descriptor.provider_model_name = target_name

            # 3. Optional weight preloading
            if preload_weights:
                try:
                    await self._provider.load_model(target_name)
                except Exception as ex:
                    logger.warning("Weight preloading failed for %s: %s (will continue)", target_name, ex)

            self._status = ModelRuntimeStatus.READY
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return RuntimeInitializationResult(
                is_success=True,
                model_id=self.model_id,
                status=self._status,
                duration_ms=duration_ms,
                metadata={"endpoint": self._provider.endpoint},
            )

        except Exception as ex:
            self._status = ModelRuntimeStatus.FAILED
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error("Initialization failed for %s: %s", self.model_id, ex)
            return RuntimeInitializationResult(
                is_success=False,
                model_id=self.model_id,
                status=self._status,
                duration_ms=duration_ms,
                error_message=str(ex),
            )

    async def health_check(self) -> ModelRuntimeHealth:
        """Measure latency and check daemon availability."""
        try:
            health = await self._provider.health_check()
            is_healthy = health.status == ProviderHealthStatus.HEALTHY
            status = ModelRuntimeStatus.READY if is_healthy else ModelRuntimeStatus.UNAVAILABLE
            if self._status == ModelRuntimeStatus.ACTIVE and is_healthy:
                status = ModelRuntimeStatus.ACTIVE

            runtime_health = ModelRuntimeHealth(
                model_id=self.model_id,
                status=status,
                is_healthy=is_healthy,
                latency_ms=health.latency_ms,
                diagnostic_message=health.diagnostic_message,
                metadata={"endpoint": self._provider.endpoint},
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
        """Execute text generation against local Ollama runtime."""
        if not self.is_initialized:
            raise RuntimeError(f"Cannot generate: model '{self.model_id}' is not initialized (status: {self._status.value})")

        self._is_busy = True
        try:
            return await self._provider.generate(self._descriptor.provider_model_name, request)
        finally:
            self._is_busy = False

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        """Execute conversational turn against local Ollama runtime."""
        if not self.is_initialized:
            raise RuntimeError(f"Cannot chat: model '{self.model_id}' is not initialized (status: {self._status.value})")

        self._is_busy = True
        try:
            return await self._provider.chat(self._descriptor.provider_model_name, request)
        finally:
            self._is_busy = False

    async def shutdown(self) -> None:
        """Release Ollama connection resources."""
        self._status = ModelRuntimeStatus.STOPPED
        logger.info("OllamaRuntimeAdapter for %s stopped", self.model_id)
