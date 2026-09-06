"""Model Discovery Engine (Milestone M1.9 Step 1).

Orchestrates multi-provider local and remote model discovery, isolates provider failures,
aggregates descriptors without collision, and preserves provider provenance.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.models.models import (
    ModelDescriptor,
    ModelProviderKind,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.model_providers.base import ModelProvider

logger = logging.getLogger(__name__)


class ProviderDiscoveryReport(BaseModel):
    """Detailed discovery report for an individual model provider."""

    provider: ModelProviderKind
    endpoint: str
    is_available: bool
    models_count: int
    health: Optional[ProviderHealth] = None
    error_message: Optional[str] = None
    elapsed_ms: float = 0.0


class DiscoveryResult(BaseModel):
    """Aggregated outcome of a multi-provider model discovery pass."""

    discovered_models: List[ModelDescriptor] = Field(default_factory=list)
    provider_reports: Dict[str, ProviderDiscoveryReport] = Field(default_factory=dict)
    total_discovered: int = 0
    successful_providers: List[ModelProviderKind] = Field(default_factory=list)
    failed_providers: Dict[str, str] = Field(default_factory=dict)
    discovered_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelDiscoveryEngine:
    """Engine responsible for polling providers and collecting model descriptors."""

    def __init__(self, providers: Optional[List[ModelProvider]] = None) -> None:
        self._providers: List[ModelProvider] = []
        if providers:
            for p in providers:
                self.register_provider(p)

    @property
    def providers(self) -> List[ModelProvider]:
        """List of registered model providers."""
        return list(self._providers)

    def register_provider(self, provider: ModelProvider) -> None:
        """Register a provider backend with the discovery engine."""
        # Replace existing provider with identical kind and endpoint if already present
        self._providers = [p for p in self._providers if not (p.provider_kind == provider.provider_kind and p.endpoint == provider.endpoint)]
        self._providers.append(provider)
        logger.debug("Registered model provider: %s (%s)", provider.provider_kind.value, provider.endpoint)

    def get_provider(self, provider_kind: ModelProviderKind, endpoint: Optional[str] = None) -> Optional[ModelProvider]:
        """Get registered provider by kind and optional endpoint."""
        for p in self._providers:
            if p.provider_kind == provider_kind:
                if endpoint is None or p.endpoint == endpoint:
                    return p
        return None

    def list_providers(self) -> List[ModelProvider]:
        """List all currently registered providers."""
        return list(self._providers)

    async def discover_provider(self, provider: ModelProvider) -> tuple[List[ModelDescriptor], ProviderDiscoveryReport]:
        """Discover models from a single provider with isolated error handling."""
        start_ns = asyncio.get_event_loop().time()
        health: Optional[ProviderHealth] = None
        try:
            # 1. Probe provider health
            health = await provider.health_check()
            if health.status in (ProviderHealthStatus.UNAVAILABLE, ProviderHealthStatus.ERROR):
                elapsed_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0
                report = ProviderDiscoveryReport(
                    provider=provider.provider_kind,
                    endpoint=provider.endpoint,
                    is_available=False,
                    models_count=0,
                    health=health,
                    error_message=health.diagnostic_message,
                    elapsed_ms=round(elapsed_ms, 2),
                )
                return [], report

            # 2. Query models from healthy/reachable provider
            models = await provider.discover_models()
            elapsed_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0
            report = ProviderDiscoveryReport(
                provider=provider.provider_kind,
                endpoint=provider.endpoint,
                is_available=True,
                models_count=len(models),
                health=health,
                error_message=None,
                elapsed_ms=round(elapsed_ms, 2),
            )
            return models, report

        except Exception as ex:
            elapsed_ms = (asyncio.get_event_loop().time() - start_ns) * 1000.0
            logger.warning("Discovery failed for provider %s: %s", provider.provider_kind.value, ex)
            report = ProviderDiscoveryReport(
                provider=provider.provider_kind,
                endpoint=provider.endpoint,
                is_available=False,
                models_count=0,
                health=health,
                error_message=str(ex),
                elapsed_ms=round(elapsed_ms, 2),
            )
            return [], report

    async def discover_all(self) -> DiscoveryResult:
        """Query all registered providers concurrently and aggregate model descriptors."""
        if not self._providers:
            return DiscoveryResult()

        tasks = [self.discover_provider(p) for p in self._providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_models: List[ModelDescriptor] = []
        provider_reports: Dict[str, ProviderDiscoveryReport] = {}
        successful_providers: List[ModelProviderKind] = []
        failed_providers: Dict[str, str] = {}

        for provider, res in zip(self._providers, results):
            p_key = f"{provider.provider_kind.value}@{provider.endpoint}"
            if isinstance(res, Exception):
                provider_reports[p_key] = ProviderDiscoveryReport(
                    provider=provider.provider_kind,
                    endpoint=provider.endpoint,
                    is_available=False,
                    models_count=0,
                    error_message=str(res),
                )
                failed_providers[p_key] = str(res)
            else:
                models, report = res
                provider_reports[p_key] = report
                if report.is_available:
                    all_models.extend(models)
                    if provider.provider_kind not in successful_providers:
                        successful_providers.append(provider.provider_kind)
                else:
                    failed_providers[p_key] = report.error_message or "Provider unavailable"

        return DiscoveryResult(
            discovered_models=all_models,
            provider_reports=provider_reports,
            total_discovered=len(all_models),
            successful_providers=successful_providers,
            failed_providers=failed_providers,
            discovered_at_utc=datetime.now(timezone.utc),
        )
