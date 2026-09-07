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
        """Fetch descriptor for a specific model ID with flexible case, prefix matching, and on-demand synthesis."""
        async with self._lock:
            # 1. Exact match
            if model_id in self._models:
                return self._models[model_id]

            # 2. Case-insensitive key match
            mid_lower = model_id.lower()
            for k, v in self._models.items():
                if k.lower() == mid_lower:
                    return v

            # 3. Match stripping provider prefix or matching provider_model_name
            clean_id = model_id.split(":", 1)[-1].lower()
            last_part = model_id.split(":")[-1].lower()
            for k, v in self._models.items():
                k_clean = k.split(":", 1)[-1].lower()
                k_last = k.split(":")[-1].lower()
                if k_clean == clean_id or k_last == last_part or k_clean == last_part or k_last == clean_id:
                    return v
                if v.provider_model_name.lower() in (mid_lower, clean_id, last_part):
                    return v

            # 4. Check if this is a Cloud Model (OpenAI, Anthropic, Gemini, DeepSeek, etc.)
            is_cloud = (
                mid_lower.startswith(("cloud:", "openai:", "anthropic:", "gemini:", "google:", "deepseek:", "custom:"))
                or clean_id.startswith(("gpt-", "o1-", "o1", "o3-", "claude-", "gemini-", "deepseek-", "text-embedding-"))
                or last_part.startswith(("gpt-", "o1-", "o1", "o3-", "claude-", "gemini-", "deepseek-", "text-embedding-"))
            )

            if is_cloud:
                try:
                    from orbit.runtime.model_providers.cloud import CURATED_CLOUD_CATALOGS
                    from orbit.runtime.models.models import CloudProviderKind, ModelSourceType

                    p_kind = ModelProviderKind.CLOUD_OPENAI
                    c_kind = CloudProviderKind.OPENAI
                    if "anthropic" in mid_lower or "claude" in mid_lower:
                        p_kind = ModelProviderKind.CLOUD_ANTHROPIC
                        c_kind = CloudProviderKind.ANTHROPIC
                    elif "gemini" in mid_lower or "google" in mid_lower:
                        p_kind = ModelProviderKind.CLOUD_GEMINI
                        c_kind = CloudProviderKind.GEMINI
                    elif "deepseek" in mid_lower:
                        p_kind = ModelProviderKind.CLOUD
                        c_kind = CloudProviderKind.CUSTOM_OPENAI_COMPATIBLE

                    catalog = CURATED_CLOUD_CATALOGS.get(c_kind, [])
                    matched_item = None
                    for item in catalog:
                        i_id = item["id"].lower()
                        if i_id == clean_id or i_id == last_part or i_id in mid_lower:
                            matched_item = item
                            break

                    display_name = matched_item["name"] if matched_item else clean_id.replace("-", " ").title()
                    raw_name = matched_item["id"] if matched_item else last_part
                    caps = matched_item.get("capabilities") if matched_item else {ModelCapability.TEXT_GENERATION, ModelCapability.CHAT, ModelCapability.CODE}
                    ctx = matched_item.get("context_window", 128000) if matched_item else 128000
                    fam = matched_item.get("family", "cloud") if matched_item else "cloud"

                    synth_id = f"cloud:{c_kind.value.lower()}:{raw_name}"
                    synth_desc = ModelDescriptor(
                        model_id=synth_id,
                        provider=p_kind,
                        provider_model_name=raw_name,
                        display_name=display_name,
                        source_type=ModelSourceType.CLOUD_PROVIDER,
                        status=ModelStatus.AVAILABLE,
                        capabilities=caps,
                        context_window=ctx,
                        family=fam,
                        local_or_remote="remote",
                    )
                    self._models[synth_id] = synth_desc
                    self._models[model_id] = synth_desc
                    return synth_desc
                except Exception:
                    pass

            # 5. Local Ollama synthesis ONLY if it's explicitly local / not a cloud model
            if not is_cloud:
                from orbit.runtime.models.models import ModelSourceType
                from orbit.runtime.models.capabilities import infer_capabilities

                raw_name = model_id.split(":", 1)[-1] if "ollama" in mid_lower else model_id
                synth_id = f"ollama:{raw_name}"
                synth_desc = ModelDescriptor(
                    model_id=synth_id,
                    provider=ModelProviderKind.OLLAMA,
                    provider_model_name=raw_name,
                    display_name=raw_name,
                    source_type=ModelSourceType.LOCAL_RUNTIME,
                    status=ModelStatus.AVAILABLE,
                    capabilities=infer_capabilities(raw_name),
                    context_window=32768,
                    family="Ollama",
                    local_or_remote="local",
                )
                self._models[synth_id] = synth_desc
                self._models[model_id] = synth_desc
                return synth_desc

            return None

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
