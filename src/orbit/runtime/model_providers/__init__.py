"""ORBIT Model Providers Subsystem (Milestone M1.9 Step 2).

Exposes provider implementations for local AI model runtimes (Ollama, LM Studio)
and cloud-hosted AI providers (OpenAI, Anthropic, Gemini, custom).
"""

from __future__ import annotations

from orbit.runtime.model_providers.base import ModelProvider
from orbit.runtime.model_providers.cloud import (
    CloudModelProvider,
    CloudProviderAuthError,
    CloudProviderError,
    CloudProviderUnreachableError,
)
from orbit.runtime.model_providers.lm_studio import (
    LMStudioProvider,
    LMStudioProviderError,
    LMStudioUnavailableError,
)
from orbit.runtime.model_providers.ollama import (
    OllamaModelNotFoundError,
    OllamaProvider,
    OllamaProviderError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)

__all__ = [
    # Base
    "ModelProvider",
    # Ollama
    "OllamaProvider",
    "OllamaProviderError",
    "OllamaUnavailableError",
    "OllamaModelNotFoundError",
    "OllamaTimeoutError",
    # LM Studio
    "LMStudioProvider",
    "LMStudioProviderError",
    "LMStudioUnavailableError",
    # Cloud
    "CloudModelProvider",
    "CloudProviderError",
    "CloudProviderUnreachableError",
    "CloudProviderAuthError",
]
