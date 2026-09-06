"""Central AI Model Inventory Engine and System Capabilities Reporter (Milestone M1.9 Step 2).

Discovers, aggregates, deduplicates, and reports on all available AI models across:
1. Local Runtimes (Ollama, LM Studio, etc.)
2. Local Model Weight Files (GGUF, ONNX, SafeTensors)
3. Cloud Providers (OpenAI, Anthropic, Gemini, Custom)

CRITICAL SECURITY INVARIANT:
Public inventory reports NEVER leak API keys, authorization headers, or private credentials.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from orbit.runtime.models.discovery import ModelDiscoveryEngine
from orbit.runtime.models.file_scanner import LocalFileModelScanner
from orbit.runtime.models.models import (
    CloudAuthStatus,
    CloudProviderKind,
    LocalModelFileDescriptor,
    ModelCapability,
    ModelDescriptor,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry
from orbit.runtime.model_providers.base import ModelProvider
from orbit.runtime.model_providers.cloud import CloudModelProvider

logger = logging.getLogger(__name__)


class RuntimeInventorySummary(BaseModel):
    """Summary of a discovered local AI inference daemon."""

    provider: ModelProviderKind
    endpoint: str
    is_available: bool
    health_status: ProviderHealthStatus
    latency_ms: Optional[float] = None
    models_count: int = 0
    diagnostic_message: Optional[str] = None


class CloudProviderInventorySummary(BaseModel):
    """Summary of a configured or candidate cloud AI provider."""

    cloud_kind: CloudProviderKind
    endpoint: str
    is_configured: bool
    auth_status: CloudAuthStatus
    models_count: int = 0
    diagnostic_message: Optional[str] = None


class SystemCapabilitiesReport(BaseModel):
    """Aggregated functional capabilities of the system's current AI model inventory."""

    offline_models_available: bool = Field(..., description="Whether at least one local offline model is ready/available")
    cloud_models_available: bool = Field(..., description="Whether at least one cloud model is authenticated/available")
    total_models: int = Field(default=0, ge=0, description="Total count of all discovered models")
    local_models_count: int = Field(default=0, ge=0, description="Count of local models (runtimes + files)")
    cloud_models_count: int = Field(default=0, ge=0, description="Count of remote cloud models")
    vision_capable_count: int = Field(default=0, ge=0, description="Count of models supporting visual understanding")
    tool_capable_count: int = Field(default=0, ge=0, description="Count of models supporting function / tool calling")
    reasoning_capable_count: int = Field(default=0, ge=0, description="Count of models with reasoning tokens")
    embedding_capable_count: int = Field(default=0, ge=0, description="Count of embedding models")


class InventoryReport(BaseModel):
    """Full structured inventory report exposing system model availability."""

    inventory_generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    local_runtimes: List[RuntimeInventorySummary] = Field(default_factory=list)
    cloud_providers: List[CloudProviderInventorySummary] = Field(default_factory=list)
    local_files: List[LocalModelFileDescriptor] = Field(default_factory=list)
    models: List[ModelDescriptor] = Field(default_factory=list)
    system_capabilities: SystemCapabilitiesReport

    def to_public_dict(self) -> Dict[str, Any]:
        """Serialize report for public / websocket consumers with credentials strictly excluded."""
        data = self.model_dump(mode="json")
        # Ensure no credential or authorization metadata is present
        for cp in data.get("cloud_providers", []):
            cp.pop("api_key", None)
            cp.pop("headers", None)
        return data


class ModelInventory:
    """Central engine managing model discovery, installation, and capability reporting."""

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        discovery_engine: Optional[ModelDiscoveryEngine] = None,
        file_scanner: Optional[LocalFileModelScanner] = None,
        cloud_providers: Optional[List[CloudModelProvider]] = None,
    ) -> None:
        self._registry = registry or ModelRegistry()
        self._discovery_engine = discovery_engine or ModelDiscoveryEngine()
        self._file_scanner = file_scanner or LocalFileModelScanner()
        self._cloud_providers: List[CloudModelProvider] = list(cloud_providers or [])
        self._last_report: Optional[InventoryReport] = None
        self._lock = asyncio.Lock()

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def discovery_engine(self) -> ModelDiscoveryEngine:
        return self._discovery_engine

    @property
    def file_scanner(self) -> LocalFileModelScanner:
        return self._file_scanner

    @property
    def cloud_providers(self) -> List[CloudModelProvider]:
        """List registered cloud model providers."""
        return list(self._cloud_providers)

    def register_runtime_provider(self, provider: ModelProvider) -> None:
        """Register a local runtime provider (Ollama, LM Studio, etc.)."""
        self._discovery_engine.register_provider(provider)

    def register_cloud_provider(self, provider: CloudModelProvider) -> None:
        """Register a cloud model provider (OpenAI, Anthropic, Gemini, etc.)."""
        self._cloud_providers = [p for p in self._cloud_providers if p.cloud_kind != provider.cloud_kind]
        self._cloud_providers.append(provider)

    async def refresh(
        self,
        include_runtimes: bool = True,
        include_cloud: bool = True,
        include_files: bool = True,
    ) -> InventoryReport:
        """Refresh and re-aggregate all AI model sources with strict failure isolation."""
        async with self._lock:
            all_discovered_models: List[ModelDescriptor] = []
            runtime_summaries: List[RuntimeInventorySummary] = []
            cloud_summaries: List[CloudProviderInventorySummary] = []
            file_descriptors: List[LocalModelFileDescriptor] = []

            # 1. Discover from Local Runtimes
            if include_runtimes:
                disc_res = await self._discovery_engine.discover_all()
                all_discovered_models.extend(disc_res.discovered_models)

                for p_key, rep in disc_res.provider_reports.items():
                    h_status = rep.health.status if rep.health else (ProviderHealthStatus.HEALTHY if rep.is_available else ProviderHealthStatus.UNAVAILABLE)
                    latency = rep.health.latency_ms if rep.health else None
                    runtime_summaries.append(
                        RuntimeInventorySummary(
                            provider=rep.provider,
                            endpoint=rep.endpoint,
                            is_available=rep.is_available,
                            health_status=h_status,
                            latency_ms=latency,
                            models_count=rep.models_count,
                            diagnostic_message=rep.error_message,
                        )
                    )

            # 2. Discover from Cloud Providers
            if include_cloud:
                for cp in self._cloud_providers:
                    try:
                        health = await cp.health_check()
                        models = await cp.discover_models()
                        all_discovered_models.extend(models)
                        cloud_summaries.append(
                            CloudProviderInventorySummary(
                                cloud_kind=cp.cloud_kind,
                                endpoint=cp.endpoint,
                                is_configured=cp.is_configured,
                                auth_status=cp.get_auth_status(),
                                models_count=len(models),
                                diagnostic_message=health.diagnostic_message,
                            )
                        )
                    except Exception as ex:
                        logger.warning("Error refreshing cloud provider %s: %s", cp.cloud_kind.value, ex)
                        cloud_summaries.append(
                            CloudProviderInventorySummary(
                                cloud_kind=cp.cloud_kind,
                                endpoint=cp.endpoint,
                                is_configured=cp.is_configured,
                                auth_status=CloudAuthStatus.ERROR,
                                models_count=0,
                                diagnostic_message=str(ex),
                            )
                        )

            # 3. Discover from Local Model Files
            if include_files:
                try:
                    file_descriptors = self._file_scanner.scan_all()
                    file_model_descriptors = self._file_scanner.to_model_descriptors(file_descriptors)
                    all_discovered_models.extend(file_model_descriptors)
                except Exception as ex:
                    logger.warning("Error scanning local model files: %s", ex)

            # 4. Deduplicate and update registry while preserving provenance
            # Note: ModelRegistry keys on stable model_id which includes provider/source prefix
            if all_discovered_models:
                await self._registry.register_models(all_discovered_models)

            # 5. Compute System Capabilities
            total_count = len(all_discovered_models)
            local_count = sum(1 for m in all_discovered_models if m.source_type in (ModelSourceType.LOCAL_RUNTIME, ModelSourceType.LOCAL_FILE))
            cloud_count = sum(1 for m in all_discovered_models if m.source_type == ModelSourceType.CLOUD_PROVIDER)

            offline_avail = any(
                m.status in (ModelStatus.AVAILABLE, ModelStatus.READY, ModelStatus.LOADED, ModelStatus.ACTIVE, ModelStatus.INSTALLED)
                and m.source_type in (ModelSourceType.LOCAL_RUNTIME, ModelSourceType.LOCAL_FILE)
                for m in all_discovered_models
            )
            cloud_avail = any(
                m.status in (ModelStatus.AVAILABLE, ModelStatus.READY)
                and m.source_type == ModelSourceType.CLOUD_PROVIDER
                for m in all_discovered_models
            )

            vision_count = sum(1 for m in all_discovered_models if ModelCapability.VISION in m.capabilities)
            tool_count = sum(1 for m in all_discovered_models if ModelCapability.TOOL_CALLING in m.capabilities)
            reasoning_count = sum(1 for m in all_discovered_models if ModelCapability.REASONING in m.capabilities)
            embedding_count = sum(1 for m in all_discovered_models if ModelCapability.EMBEDDINGS in m.capabilities)

            capabilities_report = SystemCapabilitiesReport(
                offline_models_available=offline_avail,
                cloud_models_available=cloud_avail,
                total_models=total_count,
                local_models_count=local_count,
                cloud_models_count=cloud_count,
                vision_capable_count=vision_count,
                tool_capable_count=tool_count,
                reasoning_capable_count=reasoning_count,
                embedding_capable_count=embedding_count,
            )

            report = InventoryReport(
                inventory_generated_at_utc=datetime.now(timezone.utc),
                local_runtimes=runtime_summaries,
                cloud_providers=cloud_summaries,
                local_files=file_descriptors,
                models=all_discovered_models,
                system_capabilities=capabilities_report,
            )

            self._last_report = report
            logger.info(
                "Inventory refresh complete: %d models (Local: %d, Cloud: %d, Offline Ready: %s, Cloud Ready: %s)",
                total_count,
                local_count,
                cloud_count,
                offline_avail,
                cloud_avail,
            )
            return report

    async def get_report(self) -> InventoryReport:
        """Get latest cached report or run fresh refresh if none exists."""
        if self._last_report is None:
            return await self.refresh()
        return self._last_report
