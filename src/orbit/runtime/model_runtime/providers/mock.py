"""Mock Model Runtime Adapter for Deterministic Testing (Milestone M1.9 Step 4).

Provides a deterministic mock runtime for unit and integration testing without
requiring running provider daemons or active cloud credentials.
Supports simulated initialization failures, health degradation, inference latency,
and synthetic crashes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set

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
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class MockModelRuntimeAdapter(BaseModelRuntime):
    """Deterministic mock runtime adapter for testing."""

    def __init__(
        self,
        descriptor: ModelDescriptor,
        runtime_kind: ModelRuntimeKind = ModelRuntimeKind.LOCAL,
        simulate_init_failure: bool = False,
        init_failure_reason: str = "Simulated initialization failure",
        init_delay_seconds: float = 0.0,
        simulate_health_failure: bool = False,
        simulate_inference_crash: bool = False,
        default_response_text: str = "Deterministic mock AI response",
        latency_ms: float = 5.0,
    ) -> None:
        super().__init__(descriptor)
        self._runtime_kind = runtime_kind
        self.simulate_init_failure = simulate_init_failure
        self.init_failure_reason = init_failure_reason
        self.init_delay_seconds = init_delay_seconds
        self.simulate_health_failure = simulate_health_failure
        self.simulate_inference_crash = simulate_inference_crash
        self.default_response_text = default_response_text
        self.latency_ms = latency_ms
        self.generated_requests: List[ModelGenerateRequest] = []
        self.chat_requests: List[ModelChatRequest] = []
        self.shutdown_called: bool = False

    @property
    def runtime_kind(self) -> ModelRuntimeKind:
        return self._runtime_kind

    async def initialize(
        self,
        timeout_seconds: float = 30.0,
        preload_weights: bool = True,
    ) -> RuntimeInitializationResult:
        """Initialize mock runtime with optional simulated failure or delay."""
        start = time.perf_counter()
        self._status = ModelRuntimeStatus.INITIALIZING

        if self.init_delay_seconds > 0:
            await asyncio.sleep(self.init_delay_seconds)

        if self.simulate_init_failure:
            self._status = ModelRuntimeStatus.FAILED
            duration_ms = (time.perf_counter() - start) * 1000.0
            return RuntimeInitializationResult(
                is_success=False,
                model_id=self.model_id,
                status=self._status,
                duration_ms=duration_ms,
                error_message=self.init_failure_reason,
            )

        self._status = ModelRuntimeStatus.READY
        duration_ms = (time.perf_counter() - start) * 1000.0
        return RuntimeInitializationResult(
            is_success=True,
            model_id=self.model_id,
            status=self._status,
            duration_ms=duration_ms,
            metadata={"mock": True},
        )

    async def health_check(self) -> ModelRuntimeHealth:
        """Execute mock health check."""
        if self.simulate_health_failure:
            health = ModelRuntimeHealth(
                model_id=self.model_id,
                status=ModelRuntimeStatus.UNAVAILABLE,
                is_healthy=False,
                latency_ms=self.latency_ms,
                diagnostic_message="Simulated health check failure",
            )
            self._last_health = health
            return health

        status = ModelRuntimeStatus.ACTIVE if self._status == ModelRuntimeStatus.ACTIVE else ModelRuntimeStatus.READY
        health = ModelRuntimeHealth(
            model_id=self.model_id,
            status=status,
            is_healthy=True,
            latency_ms=self.latency_ms,
            diagnostic_message=None,
            metadata={"mock": True},
        )
        self._last_health = health
        return health

    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        """Execute mock text generation."""
        if not self.is_initialized:
            raise RuntimeError(f"Cannot generate: model '{self.model_id}' is not initialized (status: {self._status.value})")

        if self.simulate_inference_crash:
            self.mark_failed("Simulated inference crash in mock runtime")
            raise RuntimeError(f"Mock runtime crashed during generation for {self.model_id}")

        self._is_busy = True
        self.generated_requests.append(request)
        try:
            return ModelGenerateResponse(
                model_id=self.model_id,
                content=self.default_response_text,
                done=True,
                total_duration_ms=self.latency_ms,
                prompt_tokens=10,
                completion_tokens=20,
                raw_response={"mock": True},
            )
        finally:
            self._is_busy = False

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        """Execute mock conversational turn."""
        if not self.is_initialized:
            raise RuntimeError(f"Cannot chat: model '{self.model_id}' is not initialized (status: {self._status.value})")

        if self.simulate_inference_crash:
            self.mark_failed("Simulated inference crash in mock runtime")
            raise RuntimeError(f"Mock runtime crashed during chat for {self.model_id}")

        self._is_busy = True
        self.chat_requests.append(request)
        try:
            return ModelGenerateResponse(
                model_id=self.model_id,
                content=self.default_response_text,
                done=True,
                total_duration_ms=self.latency_ms,
                prompt_tokens=15,
                completion_tokens=25,
                raw_response={"mock": True},
            )
        finally:
            self._is_busy = False

    async def shutdown(self) -> None:
        """Shut down mock runtime."""
        self._status = ModelRuntimeStatus.STOPPED
        self.shutdown_called = True
        logger.info("MockModelRuntimeAdapter for %s stopped", self.model_id)
