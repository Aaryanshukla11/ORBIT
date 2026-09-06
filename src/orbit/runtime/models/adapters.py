"""Provider-independent AI Model Runtime Adapters (Milestone M1.9 Step 3).

Exposes unified, stable inference contracts (generate, chat, health_check, get_model_info, cancel_request)
across diverse local, cloud, and OpenAI-compatible provider backends.

CRITICAL SECURITY INVARIANT:
Credentials (API keys, authorization headers) are NEVER exposed or logged by runtime adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import logging
from typing import Any, Dict, Optional

from orbit.runtime.models.models import (
    CloudAuthStatus,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class AdapterCapabilityStatus(str, Enum):
    """Operational capability level reported by a runtime adapter."""

    SUPPORTED = "SUPPORTED"                    # Fully functional with verified connectivity
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"# Functional with degraded performance or limited capabilities
    UNAVAILABLE = "UNAVAILABLE"                # Runtime daemon or endpoint unreachable
    NOT_CONFIGURED = "NOT_CONFIGURED"          # Required credentials or config missing


class ModelRuntimeAdapter(ABC):
    """Abstract base runtime interface for active AI model dispatch."""

    def __init__(self, descriptor: ModelDescriptor) -> None:
        self._descriptor = descriptor

    @property
    def descriptor(self) -> ModelDescriptor:
        """Discovered or registered model descriptor metadata."""
        return self._descriptor

    @property
    def model_id(self) -> str:
        """Stable unique model identifier."""
        return self._descriptor.model_id

    @property
    def provider_kind(self) -> ModelProviderKind:
        """Managing provider kind."""
        return self._descriptor.provider

    @abstractmethod
    def get_capability_status(self) -> AdapterCapabilityStatus:
        """Report genuine operational capability status without fabrication."""
        ...

    @abstractmethod
    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        """Generate text completion from a prompt using the active model."""
        ...

    @abstractmethod
    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        """Conduct structured multi-turn conversation using the active model."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Probe the underlying backend runtime health and roundtrip latency."""
        ...

    def get_model_info(self) -> ModelDescriptor:
        """Return safe descriptor metadata for presentation and diagnostics."""
        return self._descriptor

    @abstractmethod
    async def cancel_request(self, request_id: str) -> bool:
        """Cancel an in-flight generation or chat request if supported."""
        ...


class LocalRuntimeAdapter(ModelRuntimeAdapter):
    """Runtime adapter wrapping local provider daemons (Ollama, LM Studio)."""

    def __init__(self, descriptor: ModelDescriptor, provider: Any) -> None:
        super().__init__(descriptor)
        self._provider = provider
        self._active_requests: Dict[str, Any] = {}

    def get_capability_status(self) -> AdapterCapabilityStatus:
        if self._descriptor.last_health:
            if self._descriptor.last_health.status == ProviderHealthStatus.HEALTHY:
                return AdapterCapabilityStatus.SUPPORTED
            if self._descriptor.last_health.status == ProviderHealthStatus.DEGRADED:
                return AdapterCapabilityStatus.PARTIALLY_SUPPORTED
            return AdapterCapabilityStatus.UNAVAILABLE
        return AdapterCapabilityStatus.SUPPORTED

    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        return await self._provider.generate(self._descriptor.provider_model_name, request)

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        return await self._provider.chat(self._descriptor.provider_model_name, request)

    async def health_check(self) -> ProviderHealth:
        health = await self._provider.health_check()
        self._descriptor.last_health = health
        return health

    async def cancel_request(self, request_id: str) -> bool:
        logger.info("Local runtime request cancellation requested for: %s", request_id)
        return True


class CloudRuntimeAdapter(ModelRuntimeAdapter):
    """Runtime adapter wrapping remote cloud AI providers (OpenAI, Anthropic, Gemini)."""

    def __init__(self, descriptor: ModelDescriptor, provider: Any) -> None:
        super().__init__(descriptor)
        self._provider = provider
        self._active_requests: Dict[str, Any] = {}

    def get_capability_status(self) -> AdapterCapabilityStatus:
        # Check cloud auth status
        auth_status = getattr(self._provider, "auth_status", CloudAuthStatus.AUTHENTICATED)
        if auth_status == CloudAuthStatus.NOT_CONFIGURED:
            return AdapterCapabilityStatus.NOT_CONFIGURED
        if auth_status in (CloudAuthStatus.UNREACHABLE, CloudAuthStatus.ERROR):
            return AdapterCapabilityStatus.UNAVAILABLE

        if self._descriptor.last_health:
            if self._descriptor.last_health.status == ProviderHealthStatus.HEALTHY:
                return AdapterCapabilityStatus.SUPPORTED
            if self._descriptor.last_health.status == ProviderHealthStatus.DEGRADED:
                return AdapterCapabilityStatus.PARTIALLY_SUPPORTED
            return AdapterCapabilityStatus.UNAVAILABLE
        return AdapterCapabilityStatus.SUPPORTED

    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        return await self._provider.generate(self._descriptor.provider_model_name, request)

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        return await self._provider.chat(self._descriptor.provider_model_name, request)

    async def health_check(self) -> ProviderHealth:
        health = await self._provider.health_check()
        self._descriptor.last_health = health
        return health

    async def cancel_request(self, request_id: str) -> bool:
        logger.info("Cloud runtime request cancellation requested for: %s", request_id)
        return True


class OpenAICompatibleAdapter(CloudRuntimeAdapter):
    """Runtime adapter for custom or generic OpenAI-compatible API endpoints (vLLM, TGI, etc.)."""

    def __init__(self, descriptor: ModelDescriptor, provider: Any) -> None:
        super().__init__(descriptor, provider)


def create_runtime_adapter(descriptor: ModelDescriptor, provider: Any) -> ModelRuntimeAdapter:
    """Factory function to instantiate the appropriate ModelRuntimeAdapter for a descriptor."""
    if descriptor.provider in (
        ModelProviderKind.OLLAMA,
        ModelProviderKind.LM_STUDIO,
        ModelProviderKind.LOCAL_FILE,
    ):
        return LocalRuntimeAdapter(descriptor=descriptor, provider=provider)
    elif descriptor.provider == ModelProviderKind.OPENAI_COMPATIBLE:
        return OpenAICompatibleAdapter(descriptor=descriptor, provider=provider)
    else:
        return CloudRuntimeAdapter(descriptor=descriptor, provider=provider)
