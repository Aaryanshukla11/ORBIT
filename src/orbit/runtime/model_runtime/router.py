"""Hybrid Local LLM + Cloud LLM Model Router.

Routes inference requests across Local (Ollama, LM Studio) and Cloud (OpenAI, Anthropic, Gemini, DeepSeek)
providers based on required capabilities, privacy constraints, latency, and cost preferences.

SECURITY INVARIANT:
Credentials, API keys, and authorization tokens are NEVER logged, serialized, or emitted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field

from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import (
    ActiveModelContext,
    ModelNotFoundError,
    ModelRuntimeError,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    NoActiveModelError,
)
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import (
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
)

logger = logging.getLogger(__name__)


class ModelRoutingTier(str, Enum):
    """Cost/Latency preference tiers for model routing."""

    PREFER_LOCAL = "PREFER_LOCAL"          # Prioritize local models (zero cloud cost, zero cloud data transfer)
    BALANCED = "BALANCED"                  # Use local for fast text/reasoning, cloud when multimodal vision needed
    PERFORMANCE_CLOUD = "PERFORMANCE_CLOUD"# Prioritize highest capability cloud models (GPT-4o, Claude 3.5, Gemini 1.5)


class PrivacyPolicy(BaseModel):
    """Privacy constraints governing cloud data transfer."""

    allow_cloud_transfer: bool = Field(
        default=True,
        description="Whether data (including desktop screenshots and prompts) may be sent to remote cloud APIs",
    )
    strictly_local: bool = Field(
        default=False,
        description="If true, reject any model invocation that is not strictly on localhost / on-premise",
    )


class RoutingPolicy(BaseModel):
    """Routing directive specifying requirements and preferences for model selection."""

    required_capabilities: Set[ModelCapability] = Field(
        default_factory=lambda: {ModelCapability.TEXT_GENERATION},
        description="Capabilities that the target model must support",
    )
    tier: ModelRoutingTier = Field(
        default=ModelRoutingTier.PREFER_LOCAL,
        description="Cost / performance preference tier",
    )
    privacy: PrivacyPolicy = Field(
        default_factory=PrivacyPolicy,
        description="Privacy and data transfer policy",
    )
    fallback_enabled: bool = Field(
        default=True,
        description="Whether to fall back to the currently active model if no exact candidate matches",
    )
    preferred_model_id: Optional[str] = Field(
        default=None,
        description="Explicit model ID to prioritize if available and policy compliant",
    )


class RouteResolution(BaseModel):
    """Audit record of a routing decision."""

    selected_model_id: str
    provider: ModelProviderKind
    runtime_kind: ModelRuntimeKind
    tier: ModelRoutingTier
    capabilities: Set[ModelCapability]
    is_fallback: bool = False
    routing_reason: str = ""
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelRouter:
    """Intelligent Router selecting and dispatching across Local and Cloud model runtimes."""

    def __init__(
        self,
        session_manager: ModelSessionManager,
        default_policy: Optional[RoutingPolicy] = None,
    ) -> None:
        self._session_manager = session_manager
        self._default_policy = default_policy or RoutingPolicy()
        self._routing_history: List[RouteResolution] = []

    @property
    def session_manager(self) -> ModelSessionManager:
        return self._session_manager

    def get_routing_history(self, limit: int = 50) -> List[RouteResolution]:
        """Return recent routing resolution records."""
        return self._routing_history[-limit:]

    async def resolve_runtime(
        self,
        policy: Optional[RoutingPolicy] = None,
    ) -> BaseModelRuntime:
        """Resolve the optimal BaseModelRuntime instance for the given routing policy."""
        effective_policy = policy or self._default_policy
        req_caps = set(effective_policy.required_capabilities)

        # 1. Check if user requested an explicit preferred model
        if effective_policy.preferred_model_id:
            try:
                candidate = await self._session_manager.get_or_create_runtime(effective_policy.preferred_model_id)
                if candidate and self._is_candidate_compliant(candidate.descriptor, effective_policy):
                    if not candidate.is_initialized:
                        await candidate.initialize()
                    self._record_resolution(candidate, effective_policy, "Explicit preferred model requested", is_fallback=False)
                    return candidate
            except Exception as ex:
                logger.debug("Preferred model %s unavailable: %s", effective_policy.preferred_model_id, ex)

        # 2. Check current active model in ModelSessionManager if it matches tier preference
        active_runtime = self._session_manager.get_active_runtime()
        if active_runtime is not None and active_runtime.is_initialized:
            desc = active_runtime.descriptor
            is_local = self.is_local_descriptor(desc)
            tier_matches = (
                (effective_policy.tier == ModelRoutingTier.PREFER_LOCAL and is_local)
                or (effective_policy.tier == ModelRoutingTier.PERFORMANCE_CLOUD and not is_local)
                or (effective_policy.tier == ModelRoutingTier.BALANCED)
            )
            if tier_matches and self._is_candidate_compliant(desc, effective_policy):
                self._record_resolution(active_runtime, effective_policy, "Active model satisfies requirements and tier", is_fallback=False)
                return active_runtime

        # 3. Discover candidates from ModelRegistry & Providers
        descriptors = await self._session_manager.list_all_descriptors()
        compliant_candidates: List[ModelDescriptor] = []

        for desc in descriptors:
            if self._is_candidate_compliant(desc, effective_policy):
                compliant_candidates.append(desc)

        # Rank candidates based on routing tier
        ranked = self._rank_candidates(compliant_candidates, effective_policy)

        for candidate_desc in ranked:
            try:
                runtime = await self._session_manager.get_or_create_runtime(candidate_desc.model_id)
                if not runtime.is_initialized:
                    init_res = await runtime.initialize()
                    if not init_res.is_success:
                        continue
                self._record_resolution(runtime, effective_policy, f"Selected via {effective_policy.tier.value} policy", is_fallback=False)
                return runtime
            except Exception as ex:
                logger.debug("Candidate %s initialization failed: %s", candidate_desc.model_id, ex)

        # 4. Fallback Path
        if effective_policy.fallback_enabled and active_runtime is not None:
            if not effective_policy.privacy.strictly_local or active_runtime.descriptor.source_type == ModelSourceType.LOCAL_RUNTIME:
                self._record_resolution(
                    active_runtime,
                    effective_policy,
                    "Fallback to currently active model (no exact compliant candidate)",
                    is_fallback=True,
                )
                return active_runtime

        raise NoActiveModelError(
            f"No AI model runtime available matching capabilities {req_caps} with privacy policy {effective_policy.privacy}"
        )

    @staticmethod
    def is_local_descriptor(desc: ModelDescriptor) -> bool:
        """Deterministically determine if a model descriptor is hosted locally."""
        prov_val = desc.provider.value if hasattr(desc.provider, "value") else str(desc.provider)
        return (
            desc.provider in {ModelProviderKind.OLLAMA, ModelProviderKind.LM_STUDIO, ModelProviderKind.LOCAL_FILE}
            or prov_val.upper() in {"OLLAMA", "LM_STUDIO", "LOCAL_FILE"}
            or "LOCAL" in prov_val.upper()
            or desc.source_type == ModelSourceType.LOCAL_RUNTIME
        )

    def _is_candidate_compliant(self, desc: ModelDescriptor, policy: RoutingPolicy) -> bool:
        """Check if candidate model satisfies capability and privacy constraints."""
        is_local = self.is_local_descriptor(desc)
        # Privacy check
        if policy.privacy.strictly_local:
            if not is_local:
                return False

        if not policy.privacy.allow_cloud_transfer:
            if not is_local or desc.source_type == ModelSourceType.CLOUD_PROVIDER or desc.provider in {
                ModelProviderKind.CLOUD,
                ModelProviderKind.CLOUD_OPENAI,
                ModelProviderKind.CLOUD_ANTHROPIC,
                ModelProviderKind.CLOUD_GEMINI,
            }:
                return False

        # Required capabilities check
        for req_cap in policy.required_capabilities:
            if req_cap not in desc.capabilities:
                if req_cap == ModelCapability.TEXT_GENERATION and ModelCapability.CHAT in desc.capabilities:
                    continue
                return False

        return True

    def _rank_candidates(
        self,
        candidates: List[ModelDescriptor],
        policy: RoutingPolicy,
    ) -> List[ModelDescriptor]:
        """Sort candidates based on routing tier and capability richness."""
        def score(desc: ModelDescriptor) -> int:
            is_local = self.is_local_descriptor(desc)
            points = 0
            if policy.tier == ModelRoutingTier.PREFER_LOCAL:
                points += 100 if is_local else 10
            elif policy.tier == ModelRoutingTier.PERFORMANCE_CLOUD:
                points += 100 if not is_local else 20
            else:  # BALANCED
                points += 50

            # Bonus for requested capabilities
            for cap in policy.required_capabilities:
                if cap in desc.capabilities:
                    points += 25
            return points

        return sorted(candidates, key=score, reverse=True)

    def _record_resolution(
        self,
        runtime: BaseModelRuntime,
        policy: RoutingPolicy,
        reason: str,
        is_fallback: bool,
    ) -> None:
        rec = RouteResolution(
            selected_model_id=runtime.model_id,
            provider=runtime.descriptor.provider,
            runtime_kind=runtime.runtime_kind,
            tier=policy.tier,
            capabilities=set(runtime.descriptor.capabilities),
            is_fallback=is_fallback,
            routing_reason=reason,
        )
        self._routing_history.append(rec)
        if len(self._routing_history) > 100:
            self._routing_history = self._routing_history[-100:]

    async def generate(
        self,
        request: ModelGenerateRequest,
        policy: Optional[RoutingPolicy] = None,
    ) -> ModelGenerateResponse:
        """Route and execute text generation."""
        runtime = await self.resolve_runtime(policy)
        return await runtime.generate(request)

    async def chat(
        self,
        request: ModelChatRequest,
        policy: Optional[RoutingPolicy] = None,
    ) -> ModelGenerateResponse:
        """Route and execute chat turn."""
        runtime = await self.resolve_runtime(policy)
        return await runtime.chat(request)
