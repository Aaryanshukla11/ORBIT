"""Abstract Base Provider interface for AI Model Runtimes (Milestone M1.9 Step 1).

Defines the contract that all model provider implementations (Ollama, LM Studio, etc.)
must satisfy without leaking provider-specific idiosyncrasies into core ORBIT logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from orbit.runtime.models.models import (
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelStatus,
    ProviderHealth,
)


class ModelProvider(ABC):
    """Abstract interface for local and remote AI model providers."""

    @property
    @abstractmethod
    def provider_kind(self) -> ModelProviderKind:
        """The provider kind identifier (e.g. ModelProviderKind.OLLAMA)."""
        ...

    @property
    @abstractmethod
    def endpoint(self) -> str:
        """The active network address or base URL for this provider."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Perform an active connectivity and latency probe against the provider daemon."""
        ...

    @abstractmethod
    async def discover_models(self) -> List[ModelDescriptor]:
        """Query the runtime for all genuinely installed / available models."""
        ...

    @abstractmethod
    async def get_model(self, provider_model_name: str) -> Optional[ModelDescriptor]:
        """Fetch descriptor for a specific model by provider model name."""
        ...

    @abstractmethod
    async def get_model_status(self, provider_model_name: str) -> ModelStatus:
        """Query the runtime state for a specific model."""
        ...

    @abstractmethod
    async def generate(
        self,
        provider_model_name: str,
        request: ModelGenerateRequest,
    ) -> ModelGenerateResponse:
        """Generate text completion from a prompt using the specified model."""
        ...

    @abstractmethod
    async def chat(
        self,
        provider_model_name: str,
        request: ModelChatRequest,
    ) -> ModelGenerateResponse:
        """Conduct structured multi-turn conversation using the specified model."""
        ...

    @abstractmethod
    async def load_model(self, provider_model_name: str) -> bool:
        """Instruct the provider to preload the model into memory/VRAM if supported."""
        ...

    @abstractmethod
    async def unload_model(self, provider_model_name: str) -> bool:
        """Instruct the provider to evict the model from memory/VRAM if supported."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Release any open HTTP sessions, connections, or background workers."""
        ...
