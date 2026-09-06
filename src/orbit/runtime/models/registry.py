"""Thread-safe In-Memory Model Registry (Milestone M1.9 Step 1).

Maintains runtime descriptors for all discovered AI models across providers,
enforces provider-aware unique identities, and provides query and filter capabilities.
"""

from __future__ import annotations

import asyncio
from typing import Dict, Iterable, List, Optional, Set

from orbit.runtime.models.capabilities import matches_capabilities
from orbit.runtime.models.models import (
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
    ModelStatus,
    ProviderHealth,
)


class ModelRegistry:
    """Thread/async-safe repository of discovered AI model descriptors."""

    def __init__(self) -> None:
        self._models: Dict[str, ModelDescriptor] = {}
        self._lock = asyncio.Lock()

    async def register_model(self, descriptor: ModelDescriptor) -> None:
        """Register or update a single model descriptor in the registry."""
        async with self._lock:
            self._models[descriptor.model_id] = descriptor

    async def register_models(self, descriptors: Iterable[ModelDescriptor]) -> None:
        """Atomically register a collection of model descriptors."""
        async with self._lock:
            for desc in descriptors:
                self._models[desc.model_id] = desc

    async def get_model(self, model_id: str) -> Optional[ModelDescriptor]:
        """Fetch descriptor for a specific model ID (e.g. 'ollama:qwen2.5:latest')."""
        async with self._lock:
            return self._models.get(model_id)

    async def get_model_by_provider(
        self,
        provider: ModelProviderKind,
        provider_model_name: str,
    ) -> Optional[ModelDescriptor]:
        """Fetch descriptor matching a provider and exact provider model name."""
        target_id = f"{provider.value.lower()}:{provider_model_name}"
        async with self._lock:
            if target_id in self._models:
                return self._models[target_id]
            # Case-insensitive fallback
            for model in self._models.values():
                if model.provider == provider and model.provider_model_name.lower() == provider_model_name.lower():
                    return model
            return None

    async def list_models(
        self,
        provider: Optional[ModelProviderKind] = None,
        capability: Optional[ModelCapability] = None,
        status: Optional[ModelStatus] = None,
    ) -> List[ModelDescriptor]:
        """List registered models matching optional filter criteria."""
        async with self._lock:
            results = list(self._models.values())

        if provider is not None:
            results = [m for m in results if m.provider == provider]

        if capability is not None:
            results = [m for m in results if capability in m.capabilities]

        if status is not None:
            results = [m for m in results if m.status == status]

        return results

    async def update_model_status(self, model_id: str, status: ModelStatus) -> bool:
        """Update the operational status of an existing model descriptor."""
        async with self._lock:
            if model_id not in self._models:
                return False
            curr = self._models[model_id]
            updated = curr.model_copy(update={"status": status})
            self._models[model_id] = updated
            return True

    async def update_model_health(self, model_id: str, health: ProviderHealth) -> bool:
        """Update the latest health report for a model."""
        async with self._lock:
            if model_id not in self._models:
                return False
            curr = self._models[model_id]
            updated = curr.model_copy(update={"last_health": health})
            self._models[model_id] = updated
            return True

    async def remove_model(self, model_id: str) -> bool:
        """Remove a specific model from the registry."""
        async with self._lock:
            if model_id in self._models:
                del self._models[model_id]
                return True
            return False

    async def remove_models_by_provider(self, provider: ModelProviderKind) -> int:
        """Remove all models associated with a specific provider."""
        async with self._lock:
            to_remove = [k for k, m in self._models.items() if m.provider == provider]
            for k in to_remove:
                del self._models[k]
            return len(to_remove)

    async def clear(self) -> None:
        """Clear all registered models."""
        async with self._lock:
            self._models.clear()

    async def count(self) -> int:
        """Return total number of registered models."""
        async with self._lock:
            return len(self._models)
