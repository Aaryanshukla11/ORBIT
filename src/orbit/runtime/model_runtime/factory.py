"""Model Runtime Factory (Milestone M1.9 Step 4).

Instantiates the appropriate BaseModelRuntime adapter based on model descriptor
metadata, provider kind, and available provider backend instances.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.providers.local import OllamaRuntimeAdapter
from orbit.runtime.model_runtime.providers.mock import MockModelRuntimeAdapter
from orbit.runtime.model_runtime.providers.remote import OpenAICompatibleRuntimeAdapter
from orbit.runtime.models.models import (
    ModelDescriptor,
    ModelProviderKind,
    ModelSourceType,
)
from orbit.runtime.model_providers.base import ModelProvider
from orbit.runtime.model_providers.cloud import CloudModelProvider
from orbit.runtime.model_providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


class ModelRuntimeFactory:
    """Factory for creating BaseModelRuntime instances from descriptors and provider backends."""

    def __init__(self, providers: Optional[List[ModelProvider]] = None) -> None:
        self._providers: Dict[ModelProviderKind, ModelProvider] = {}
        if providers:
            for p in providers:
                self._providers[p.provider_kind] = p

    def register_provider(self, provider: ModelProvider) -> None:
        """Register a provider backend instance."""
        self._providers[provider.provider_kind] = provider

    def create_runtime(
        self,
        descriptor: ModelDescriptor,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> BaseModelRuntime:
        """Create and return a configured, uninitialized BaseModelRuntime instance."""
        provider_kind = descriptor.provider

        # Check if custom mock descriptor
        if descriptor.model_id.startswith("mock:") or descriptor.provider_model_name.startswith("mock-"):
            return MockModelRuntimeAdapter(descriptor=descriptor)

        # 1. Local Ollama Runtime
        if provider_kind == ModelProviderKind.OLLAMA:
            p = self._providers.get(ModelProviderKind.OLLAMA)
            ollama_p = p if isinstance(p, OllamaProvider) else None
            return OllamaRuntimeAdapter(descriptor=descriptor, provider=ollama_p, endpoint=base_url)

        # 2. Cloud Providers (OpenAI, Anthropic, Gemini, etc.)
        if provider_kind in {
            ModelProviderKind.CLOUD,
            ModelProviderKind.CLOUD_OPENAI,
            ModelProviderKind.CLOUD_ANTHROPIC,
            ModelProviderKind.CLOUD_GEMINI,
        }:
            p = self._providers.get(provider_kind) or self._providers.get(ModelProviderKind.CLOUD)
            if not p:
                for cand in self._providers.values():
                    if isinstance(cand, CloudModelProvider):
                        if cand.provider_kind == provider_kind or (getattr(cand, "cloud_kind", None) and cand.cloud_kind.value.lower() in descriptor.model_id.lower()):
                            p = cand
                            break
            cloud_p = p if isinstance(p, CloudModelProvider) else None
            return OpenAICompatibleRuntimeAdapter(
                descriptor=descriptor,
                api_key=api_key or (cloud_p._api_key if cloud_p else None),
                base_url=base_url or (cloud_p.endpoint if cloud_p else None),
                provider=cloud_p,
            )

        # 3. LM Studio & OpenAI-Compatible
        if provider_kind in {
            ModelProviderKind.LM_STUDIO,
            ModelProviderKind.OPENAI_COMPATIBLE,
        }:
            return OpenAICompatibleRuntimeAdapter(
                descriptor=descriptor,
                api_key=api_key,
                base_url=base_url or descriptor.endpoint,
            )

        # 4. Fallback / Local File
        if descriptor.source_type == ModelSourceType.LOCAL_FILE:
            return MockModelRuntimeAdapter(descriptor=descriptor)

        # Generic OpenAI-compatible fallback
        return OpenAICompatibleRuntimeAdapter(
            descriptor=descriptor,
            api_key=api_key,
            base_url=base_url or descriptor.endpoint,
        )


def create_model_runtime(
    descriptor: ModelDescriptor,
    providers: Optional[List[ModelProvider]] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> BaseModelRuntime:
    """Convenience helper to create a model runtime instance."""
    factory = ModelRuntimeFactory(providers=providers)
    return factory.create_runtime(descriptor=descriptor, api_key=api_key, base_url=base_url)
