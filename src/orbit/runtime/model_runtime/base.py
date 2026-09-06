"""Base Model Runtime Abstract Interface (Milestone M1.9 Step 4).

Defines the contract for lazy, provider-independent model runtime instances.
Runtimes do not consume resources (VRAM, connections, processes) upon instantiation.
Resource allocation occurs explicitly during `initialize()`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Optional, Set

from orbit.runtime.model_runtime.contracts import (
    ModelRuntimeCapability,
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
)

logger = logging.getLogger(__name__)


class BaseModelRuntime(ABC):
    """Abstract base class for all ORBIT AI model runtime instances.
    
    Subclasses wrap concrete provider backends (e.g. Ollama, remote APIs, local files, mocks).
    Enforces lazy initialization and resource lifecycle management.
    """

    def __init__(self, descriptor: ModelDescriptor) -> None:
        self._descriptor = descriptor
        self._status: ModelRuntimeStatus = ModelRuntimeStatus.UNINITIALIZED
        self._last_health: Optional[ModelRuntimeHealth] = None
        self._is_busy: bool = False
        self._lock_count: int = 0

    @property
    def model_id(self) -> str:
        """Stable unique identifier of this model (e.g. 'ollama:qwen2.5:latest')."""
        return self._descriptor.model_id

    @property
    def descriptor(self) -> ModelDescriptor:
        """Discovered metadata descriptor."""
        return self._descriptor

    @property
    def status(self) -> ModelRuntimeStatus:
        """Current lifecycle status."""
        return self._status

    @property
    def is_initialized(self) -> bool:
        """Whether runtime has completed initialization and is ready/active."""
        return self._status in {
            ModelRuntimeStatus.READY,
            ModelRuntimeStatus.ACTIVE,
            ModelRuntimeStatus.BUSY,
        }

    @property
    def is_busy(self) -> bool:
        """Whether runtime is currently processing an inference request."""
        return self._is_busy

    @property
    @abstractmethod
    def runtime_kind(self) -> ModelRuntimeKind:
        """Classification (LOCAL, REMOTE, UNKNOWN)."""
        ...

    @property
    def info(self) -> ModelRuntimeInfo:
        """Sanitized runtime info snapshot."""
        return ModelRuntimeInfo(
            model_id=self.model_id,
            display_name=self._descriptor.display_name,
            provider=self._descriptor.provider,
            runtime_kind=self.runtime_kind,
            status=self._status,
            capabilities=self._descriptor.capabilities,
            context_window=self._descriptor.context_window,
            parameter_size=self._descriptor.parameter_size,
            quantization=self._descriptor.quantization_level or self._descriptor.quantization,
            endpoint=self._descriptor.endpoint,
            metadata=self._descriptor.metadata,
        )

    @abstractmethod
    async def initialize(self, timeout_seconds: float = 30.0, preload_weights: bool = True) -> RuntimeInitializationResult:
        """Perform lazy runtime preparation (connect, load weights, warmup).
        
        Must transition self._status to READY or FAILED.
        """
        ...

    @abstractmethod
    async def health_check(self) -> ModelRuntimeHealth:
        """Execute a genuine health probe against the underlying provider backend."""
        ...

    @abstractmethod
    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        """Execute text completion / generation."""
        ...

    @abstractmethod
    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        """Execute structured conversational turn."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Release allocated runtime resources (connections, idle memory)."""
        ...

    def set_active_state(self, is_active: bool) -> None:
        """Transition runtime between READY and ACTIVE states."""
        if is_active and self._status == ModelRuntimeStatus.READY:
            self._status = ModelRuntimeStatus.ACTIVE
        elif not is_active and self._status == ModelRuntimeStatus.ACTIVE:
            self._status = ModelRuntimeStatus.READY

    def mark_failed(self, reason: str) -> None:
        """Transition runtime to FAILED state."""
        self._status = ModelRuntimeStatus.FAILED
        logger.error("Model runtime for %s marked as FAILED: %s", self.model_id, reason)
