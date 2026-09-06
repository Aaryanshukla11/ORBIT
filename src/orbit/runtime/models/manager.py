"""Central Model Manager and Runtime Coordinator (Milestone M1.9 Step 3).

Orchestrates multi-provider discovery, registry maintenance, active model selection,
transactional model switching with atomic rollback, monotonic generation tracking,
inference runtime adapters, lifecycle state enforcement, installation coordination,
and system inventory reporting.

CRITICAL SECURITY INVARIANT:
API keys, authorization tokens, and credentials are NEVER serialized, logged,
or exposed through events, descriptors, exceptions, or runtime adapters.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Set
import uuid

from orbit.contracts.events import (
    EventType,
    ModelEventPayload,
    ModelHealthEventPayload,
    ModelSwitchEventPayload,
    RuntimeEvent,
)
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.models.adapters import (
    AdapterCapabilityStatus,
    CloudRuntimeAdapter,
    LocalRuntimeAdapter,
    ModelRuntimeAdapter,
    OpenAICompatibleAdapter,
    create_runtime_adapter,
)
from orbit.runtime.models.discovery import DiscoveryResult, ModelDiscoveryEngine
from orbit.runtime.models.file_scanner import LocalFileModelScanner
from orbit.runtime.models.installer import (
    ModelInstallationError,
    ModelInstaller,
    OllamaInstallationProvider,
)
from orbit.runtime.models.inventory import (
    InventoryReport,
    ModelInventory,
    SystemCapabilitiesReport,
)
from orbit.runtime.models.lifecycle import (
    InvalidStateTransitionError,
    ModelLifecycleManager,
)
from orbit.runtime.models.models import (
    ActiveModelSession,
    CloudAuthStatus,
    InstallationProgress,
    InstallationRequest,
    InstallationResult,
    ModelActivationRequest,
    ModelActivationResult,
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSelectionRequest,
    ModelSelectionResult,
    ModelSelectionStatus,
    ModelSessionStatus,
    ModelSourceType,
    ModelStatus,
    ModelSwitchPolicy,
    ModelSwitchResult,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry
from orbit.runtime.model_providers.base import ModelProvider
from orbit.runtime.model_providers.cloud import CloudModelProvider

logger = logging.getLogger(__name__)


class ModelManagerError(Exception):
    """Base exception for ModelManager operations."""
    pass


class ModelNotFoundError(ModelManagerError):
    """Raised when a requested model ID is not found in registry or inventory."""
    pass


class ModelUnavailableError(ModelManagerError):
    """Raised when a requested model is known but currently unavailable or incompatible."""
    pass


class ProviderNotFoundError(ModelManagerError):
    """Raised when a model's provider backend is not registered."""
    pass


class ProviderUnhealthyError(ModelManagerError):
    """Raised when attempting to activate a model whose provider backend is offline or unhealthy."""
    pass


class CloudAuthRequiredError(ModelManagerError):
    """Raised when attempting to activate a cloud model whose credentials are not configured."""
    pass


class CapabilityMismatchError(ModelManagerError):
    """Raised when a candidate model lacks one or more requested required capabilities."""
    pass


class StaleModelGenerationError(ModelManagerError):
    """Raised when an inference request is dispatched against an outdated model generation counter."""
    pass


class NoActiveModelError(ModelManagerError):
    """Raised when inference is requested but no model is currently active."""
    pass


class ModelSwitchError(ModelManagerError):
    """Raised when transactional active model switching fails and rolls back."""
    pass


class ModelManager:
    """Production Model Manager managing model discovery, registration, selection,

    activation, atomic runtime switching with safe rollback, and active inference dispatch.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        discovery_engine: Optional[ModelDiscoveryEngine] = None,
        providers: Optional[List[ModelProvider]] = None,
        inventory: Optional[ModelInventory] = None,
        installer: Optional[ModelInstaller] = None,
        lifecycle_manager: Optional[ModelLifecycleManager] = None,
        file_scanner: Optional[LocalFileModelScanner] = None,
        cloud_providers: Optional[List[CloudModelProvider]] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._registry = registry or ModelRegistry()
        self._discovery_engine = discovery_engine or ModelDiscoveryEngine(providers=providers)
        self._file_scanner = file_scanner or LocalFileModelScanner()
        self._lifecycle_manager = lifecycle_manager or ModelLifecycleManager()

        self._inventory = inventory or ModelInventory(
            registry=self._registry,
            discovery_engine=self._discovery_engine,
            file_scanner=self._file_scanner,
            cloud_providers=cloud_providers,
        )

        self._installer = installer or ModelInstaller(
            providers=[OllamaInstallationProvider()]
        )

        self._event_bus = event_bus

        # Concurrency & Active Session State
        self._active_model_id: Optional[str] = None
        self._active_session: Optional[ActiveModelSession] = None
        self._active_runtime: Optional[ModelRuntimeAdapter] = None
        self._generation: int = 1
        self._lock = asyncio.Lock()

    @property
    def registry(self) -> ModelRegistry:
        """Reference to the underlying ModelRegistry."""
        return self._registry

    @property
    def discovery_engine(self) -> ModelDiscoveryEngine:
        """Reference to the ModelDiscoveryEngine."""
        return self._discovery_engine

    @property
    def inventory(self) -> ModelInventory:
        """Reference to the ModelInventory engine."""
        return self._inventory

    @property
    def providers(self) -> List[ModelProvider]:
        """List of local and remote providers configured in discovery engine."""
        return self._discovery_engine.providers

    @property
    def installer(self) -> ModelInstaller:
        """Reference to the ModelInstaller engine."""
        return self._installer

    @property
    def lifecycle_manager(self) -> ModelLifecycleManager:
        """Reference to the ModelLifecycleManager."""
        return self._lifecycle_manager

    @property
    def event_bus(self) -> Optional[EventBus]:
        """Reference to the EventBus."""
        return self._event_bus

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Attach or update the ORBIT EventBus for streaming events."""
        self._event_bus = event_bus

    def register_provider(self, provider: ModelProvider) -> None:
        """Register a local AI model provider backend."""
        self._discovery_engine.register_provider(provider)
        self._inventory.register_runtime_provider(provider)

    def register_cloud_provider(self, provider: CloudModelProvider) -> None:
        """Register a cloud AI model provider."""
        self._inventory.register_cloud_provider(provider)

    def get_provider(self, provider_kind: ModelProviderKind) -> Optional[ModelProvider]:
        """Get registered local runtime provider by kind."""
        return self._discovery_engine.get_provider(provider_kind)

    def _resolve_provider_instance(self, provider_kind: ModelProviderKind) -> Optional[Any]:
        """Resolve either local provider or cloud provider for a given kind."""
        local = self._discovery_engine.get_provider(provider_kind)
        if local is not None:
            return local
        # Check cloud providers from inventory
        for cp in self._inventory.cloud_providers:
            if cp.provider_kind == provider_kind or getattr(cp, "cloud_kind", None) and cp.cloud_kind.value == provider_kind.value:
                return cp
        return None

    async def _emit_event(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Safely emit structured model event to EventBus without credentials."""
        if self._event_bus is None:
            return
        try:
            evt = RuntimeEvent(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                event_type=event_type,
                session_id=self._active_model_id or "system",
                payload=payload,
            )
            await self._event_bus.publish(evt)
        except Exception as ex:
            logger.debug("Failed to publish model event %s: %s", event_type.value, ex)

    # -------------------------------------------------------------------------
    # Discovery & Inventory Operations
    # -------------------------------------------------------------------------

    async def discover_models(self) -> DiscoveryResult:
        """Run discovery across all registered local providers and update the registry."""
        result = await self._discovery_engine.discover_all()
        if result.discovered_models:
            await self._registry.register_models(result.discovered_models)
            for m in result.discovered_models:
                self._lifecycle_manager.record_transition(
                    m.model_id,
                    m.status,
                    reason=f"Discovered via provider {m.provider.value}",
                )
            logger.info("ModelManager discovery complete: registered %d models", len(result.discovered_models))
        return result

    async def refresh_models(self) -> DiscoveryResult:
        """Refresh and re-discover models from local providers."""
        return await self.discover_models()

    async def refresh_inventory(
        self,
        include_runtimes: bool = True,
        include_cloud: bool = True,
        include_files: bool = True,
    ) -> InventoryReport:
        """Execute full inventory refresh across all sources (runtimes, cloud, files)."""
        report = await self._inventory.refresh(
            include_runtimes=include_runtimes,
            include_cloud=include_cloud,
            include_files=include_files,
        )
        for m in report.models:
            self._lifecycle_manager.record_transition(
                m.model_id,
                m.status,
                reason=f"Discovered via {m.source_type.value}",
            )
        return report

    async def get_inventory_report(self) -> InventoryReport:
        """Retrieve latest system inventory report."""
        return await self._inventory.get_report()

    async def install_model(self, request: InstallationRequest) -> AsyncIterator[InstallationProgress]:
        """Stream progress updates for a model installation request."""
        target_model_id = f"{request.target_runtime.value}:{request.model_name}"
        try:
            self._lifecycle_manager.transition(
                target_model_id,
                ModelStatus.INSTALLING,
                reason=f"Installation initiated for {request.model_name}",
            )
        except InvalidStateTransitionError:
            self._lifecycle_manager.record_transition(
                target_model_id,
                ModelStatus.INSTALLING,
                reason=f"Installation initiated for {request.model_name}",
            )

        async for progress in self._installer.install(request):
            if progress.stage.value == "COMPLETE":
                self._lifecycle_manager.record_transition(
                    target_model_id,
                    ModelStatus.INSTALLED,
                    reason=f"Installation completed successfully",
                )
            elif progress.stage.value == "FAILED":
                self._lifecycle_manager.record_transition(
                    target_model_id,
                    ModelStatus.FAILED,
                    reason=f"Installation failed: {progress.error_message}",
                )
            yield progress

    async def list_models(
        self,
        provider: Optional[ModelProviderKind] = None,
        capability: Optional[ModelCapability] = None,
        status: Optional[ModelStatus] = None,
    ) -> List[ModelDescriptor]:
        """List models currently stored in the registry matching criteria."""
        return await self._registry.list_models(provider=provider, capability=capability, status=status)

    async def get_model(self, model_id: str) -> Optional[ModelDescriptor]:
        """Fetch descriptor for a specific model ID."""
        descriptor = await self._registry.get_model(model_id)
        if descriptor is not None:
            return descriptor
        # Check inventory if not yet in registry
        report = await self._inventory.get_report()
        for m in report.models:
            if m.model_id == model_id:
                return m
        return None

    # -------------------------------------------------------------------------
    # Milestone M1.9 Step 3: Model Selection
    # -------------------------------------------------------------------------

    async def select_model(
        self,
        request: ModelSelectionRequest | str,
    ) -> ModelSelectionResult:
        """Validate whether a candidate model exists, is compatible, authenticated, and usable.

        FAILS HONESTLY without silently falling back to a different model.
        """
        if isinstance(request, str):
            req = ModelSelectionRequest(model_id=request)
        else:
            req = request

        model_id = req.model_id

        # Gate 1: Check model existence in registry or inventory
        descriptor = await self.get_model(model_id)
        if descriptor is None:
            res = ModelSelectionResult(
                is_successful=False,
                model_id=model_id,
                status=ModelSelectionStatus.MODEL_NOT_FOUND,
                failure_reason="MODEL_NOT_FOUND",
                diagnostic_message=f"Model '{model_id}' was not found in registry or system inventory.",
            )
            return res

        # Gate 2: Check operational status of model
        current_status = self._lifecycle_manager.get_current_status(model_id) or descriptor.status
        if current_status in (ModelStatus.UNAVAILABLE, ModelStatus.FAILED, ModelStatus.OFFLINE):
            return ModelSelectionResult(
                is_successful=False,
                model_id=model_id,
                status=ModelSelectionStatus.MODEL_UNAVAILABLE,
                failure_reason="MODEL_UNAVAILABLE",
                diagnostic_message=f"Model '{model_id}' is currently unavailable (status: {current_status.value}).",
                descriptor=descriptor,
            )
        if current_status == ModelStatus.INCOMPATIBLE:
            return ModelSelectionResult(
                is_successful=False,
                model_id=model_id,
                status=ModelSelectionStatus.MODEL_INCOMPATIBLE,
                failure_reason="MODEL_INCOMPATIBLE",
                diagnostic_message=f"Model '{model_id}' is incompatible with the host environment.",
                descriptor=descriptor,
            )

        # Gate 3: Check capability constraints
        if req.required_capabilities:
            missing_caps = req.required_capabilities - descriptor.capabilities
            if missing_caps:
                missing_str = ", ".join(c.value for c in missing_caps)
                return ModelSelectionResult(
                    is_successful=False,
                    model_id=model_id,
                    status=ModelSelectionStatus.CAPABILITY_MISMATCH,
                    failure_reason="CAPABILITY_MISMATCH",
                    diagnostic_message=f"Model '{model_id}' lacks required capabilities: {missing_str}",
                    descriptor=descriptor,
                )

        # Gate 4: Resolve provider backend and verify connectivity/auth
        provider = self._resolve_provider_instance(descriptor.provider)
        if provider is None:
            return ModelSelectionResult(
                is_successful=False,
                model_id=model_id,
                status=ModelSelectionStatus.RUNTIME_UNREACHABLE,
                failure_reason="RUNTIME_UNREACHABLE",
                diagnostic_message=f"Provider runtime backend for '{descriptor.provider.value}' is not registered or running.",
                descriptor=descriptor,
            )

        # If cloud provider: verify authentication configuration
        if isinstance(provider, CloudModelProvider):
            auth_status = provider.auth_status
            if auth_status == CloudAuthStatus.NOT_CONFIGURED:
                return ModelSelectionResult(
                    is_successful=False,
                    model_id=model_id,
                    status=ModelSelectionStatus.AUTH_NOT_CONFIGURED,
                    failure_reason="AUTH_NOT_CONFIGURED",
                    diagnostic_message=f"Cloud provider '{descriptor.provider.value}' requires credentials, but none are configured.",
                    descriptor=descriptor,
                )
            if auth_status in (CloudAuthStatus.UNREACHABLE, CloudAuthStatus.ERROR):
                return ModelSelectionResult(
                    is_successful=False,
                    model_id=model_id,
                    status=ModelSelectionStatus.RUNTIME_UNREACHABLE,
                    failure_reason="RUNTIME_UNREACHABLE",
                    diagnostic_message=f"Cloud provider endpoint for '{descriptor.provider.value}' is unreachable.",
                    descriptor=descriptor,
                )

        # Selection passed all validation gates
        await self._emit_event(
            EventType.MODEL_SELECTION_REQUESTED,
            ModelEventPayload(
                model_id=model_id,
                provider=descriptor.provider.value,
                status=ModelSelectionStatus.SELECTED.value,
                details={"capabilities": [c.value for c in descriptor.capabilities]},
            ).model_dump(),
        )

        return ModelSelectionResult(
            is_successful=True,
            model_id=model_id,
            status=ModelSelectionStatus.SELECTED,
            descriptor=descriptor,
            diagnostic_message=f"Model '{model_id}' successfully validated and selected.",
        )

    # -------------------------------------------------------------------------
    # Milestone M1.9 Step 3: Model Activation
    # -------------------------------------------------------------------------

    async def activate_model(
        self,
        request: ModelActivationRequest | str,
    ) -> ModelActivationResult:
        """Explicitly prepare, health-probe, and activate a model as the primary ORBIT model."""
        start_ns = time.perf_counter_ns()
        if isinstance(request, str):
            req = ModelActivationRequest(model_id=request)
        else:
            req = request

        model_id = req.model_id

        # Phase 1: Selection Validation
        sel_req = ModelSelectionRequest(
            model_id=model_id,
            required_capabilities=req.required_capabilities,
        )
        sel_result = await self.select_model(sel_req)
        if not sel_result.is_successful or sel_result.descriptor is None:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            return ModelActivationResult(
                is_successful=False,
                model_id=model_id,
                failure_reason=sel_result.failure_reason or "SELECTION_FAILED",
                diagnostic_message=sel_result.diagnostic_message,
                duration_ms=elapsed_ms,
            )

        descriptor = sel_result.descriptor
        provider = self._resolve_provider_instance(descriptor.provider)
        if provider is None:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            return ModelActivationResult(
                is_successful=False,
                model_id=model_id,
                failure_reason="RUNTIME_UNREACHABLE",
                diagnostic_message=f"Provider '{descriptor.provider.value}' not found.",
                duration_ms=elapsed_ms,
            )

        # Phase 2: Emit Activation Started Event
        await self._emit_event(
            EventType.MODEL_ACTIVATION_STARTED,
            ModelEventPayload(
                model_id=model_id,
                provider=descriptor.provider.value,
                status=ModelSessionStatus.ACTIVATING.value,
            ).model_dump(),
        )

        # Phase 3: Provider Preparation / Weight Loading
        try:
            if hasattr(provider, "load_model") and req.preload_weights:
                await provider.load_model(descriptor.provider_model_name)
        except Exception as ex:
            logger.warning("Provider load_model failed for %s: %s", model_id, ex)
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            return ModelActivationResult(
                is_successful=False,
                model_id=model_id,
                failure_reason="MODEL_NOT_READY",
                diagnostic_message=f"Failed to prepare model weights on provider: {ex}",
                duration_ms=elapsed_ms,
            )

        # Phase 4: Active Health Check
        health = await provider.health_check()
        await self._registry.update_model_health(model_id, health)
        if health.status in (ProviderHealthStatus.UNAVAILABLE, ProviderHealthStatus.ERROR):
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            return ModelActivationResult(
                is_successful=False,
                model_id=model_id,
                failure_reason="RUNTIME_UNREACHABLE",
                diagnostic_message=f"Provider health check failed ({health.status.value}): {health.diagnostic_message}",
                duration_ms=elapsed_ms,
            )

        # Phase 5: Atomic State Update & Generation Increment
        async with self._lock:
            # Monotonic generation increment
            if self._active_session is not None:
                self._generation += 1
            current_gen = self._generation

            session = ActiveModelSession(
                active_model_id=model_id,
                provider_id=descriptor.provider,
                provider_model_name=descriptor.provider_model_name,
                runtime_id=f"{descriptor.provider.value}_runtime",
                health_status=health.status,
                session_status=ModelSessionStatus.ACTIVE,
                generation=current_gen,
                capabilities=descriptor.capabilities,
                context_window=descriptor.context_window,
                endpoint=descriptor.endpoint,
                descriptor=descriptor,
            )

            runtime_adapter = create_runtime_adapter(descriptor, provider)

            self._active_model_id = model_id
            self._active_session = session
            self._active_runtime = runtime_adapter

            self._lifecycle_manager.record_transition(
                model_id,
                ModelStatus.LOADED,
                reason="Model activated as primary ORBIT active session",
            )
            await self._registry.update_model_status(model_id, ModelStatus.LOADED)

        # Phase 6: Emit Activated Event
        await self._emit_event(
            EventType.MODEL_ACTIVATED,
            ModelEventPayload(
                model_id=model_id,
                provider=descriptor.provider.value,
                generation=current_gen,
                status=ModelSessionStatus.ACTIVE.value,
            ).model_dump(),
        )

        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        return ModelActivationResult(
            is_successful=True,
            model_id=model_id,
            generation=current_gen,
            active_session=session,
            duration_ms=elapsed_ms,
        )

    # -------------------------------------------------------------------------
    # Milestone M1.9 Step 3: Safe Model Switching & Atomic Rollback
    # -------------------------------------------------------------------------

    async def switch_model(
        self,
        target_model_id: str,
        policy: ModelSwitchPolicy = ModelSwitchPolicy.SAFE_ROLLBACK,
        required_capabilities: Optional[Set[ModelCapability]] = None,
    ) -> ModelSwitchResult:
        """Transactionally switch the active model from A to B with guaranteed rollback on failure.

        CRITICAL REQUIREMENT:
        Never deactivate or destroy the current healthy active model before the replacement model
        has successfully passed validation, preparation, and health checks.
        """
        start_ns = time.perf_counter_ns()

        async with self._lock:
            previous_model_id = self._active_model_id
            previous_session = self._active_session
            previous_runtime = self._active_runtime
            previous_gen = self._generation

            # Emit Switch Started Event
            await self._emit_event(
                EventType.MODEL_SWITCH_STARTED,
                ModelSwitchEventPayload(
                    previous_model_id=previous_model_id,
                    target_model_id=target_model_id,
                    generation=previous_gen,
                    is_successful=False,
                ).model_dump(),
            )

            # Step 1: Validate Target Model Selection
            sel_req = ModelSelectionRequest(
                model_id=target_model_id,
                required_capabilities=required_capabilities or set(),
            )
            sel_res = await self.select_model(sel_req)
            if not sel_res.is_successful or sel_res.descriptor is None:
                elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                # Rollback invariant: previous model remains active
                await self._emit_event(
                    EventType.MODEL_SWITCH_FAILED,
                    ModelSwitchEventPayload(
                        previous_model_id=previous_model_id,
                        target_model_id=target_model_id,
                        generation=previous_gen,
                        is_successful=False,
                        failure_reason=sel_res.failure_reason,
                        diagnostic_message=sel_res.diagnostic_message,
                        duration_ms=elapsed_ms,
                    ).model_dump(),
                )
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=previous_model_id,
                    active_model_id=previous_model_id,
                    generation=previous_gen,
                    switched=False,
                    active_session=previous_session,
                    failure_reason=sel_res.failure_reason,
                    diagnostic_message=sel_res.diagnostic_message,
                    duration_ms=elapsed_ms,
                )

            target_descriptor = sel_res.descriptor
            target_provider = self._resolve_provider_instance(target_descriptor.provider)
            if target_provider is None:
                elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=previous_model_id,
                    active_model_id=previous_model_id,
                    generation=previous_gen,
                    switched=False,
                    active_session=previous_session,
                    failure_reason="RUNTIME_UNREACHABLE",
                    diagnostic_message=f"Target provider '{target_descriptor.provider.value}' not found.",
                    duration_ms=elapsed_ms,
                )

            # Step 2: Prepare Target Model (e.g. load weights into memory/VRAM)
            try:
                if hasattr(target_provider, "load_model"):
                    await target_provider.load_model(target_descriptor.provider_model_name)
            except Exception as ex:
                logger.error("Failed to prepare target model %s: %s (Rolling back)", target_model_id, ex)
                elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                # Rollback invariant: restore previous state
                await self._emit_event(
                    EventType.MODEL_SWITCH_FAILED,
                    ModelSwitchEventPayload(
                        previous_model_id=previous_model_id,
                        target_model_id=target_model_id,
                        generation=previous_gen,
                        is_successful=False,
                        failure_reason="MODEL_NOT_READY",
                        diagnostic_message=str(ex),
                        duration_ms=elapsed_ms,
                    ).model_dump(),
                )
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=previous_model_id,
                    active_model_id=previous_model_id,
                    generation=previous_gen,
                    switched=False,
                    active_session=previous_session,
                    failure_reason="MODEL_NOT_READY",
                    diagnostic_message=f"Target model preparation failed: {ex}",
                    duration_ms=elapsed_ms,
                )

            # Step 3: Health Probe Target Model
            try:
                health = await target_provider.health_check()
                await self._registry.update_model_health(target_model_id, health)
                if health.status in (ProviderHealthStatus.UNAVAILABLE, ProviderHealthStatus.ERROR):
                    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                    await self._emit_event(
                        EventType.MODEL_SWITCH_FAILED,
                        ModelSwitchEventPayload(
                            previous_model_id=previous_model_id,
                            target_model_id=target_model_id,
                            generation=previous_gen,
                            is_successful=False,
                            failure_reason="RUNTIME_UNREACHABLE",
                            diagnostic_message=health.diagnostic_message,
                            duration_ms=elapsed_ms,
                        ).model_dump(),
                    )
                    return ModelSwitchResult(
                        is_successful=False,
                        previous_model_id=previous_model_id,
                        active_model_id=previous_model_id,
                        generation=previous_gen,
                        switched=False,
                        active_session=previous_session,
                        failure_reason="RUNTIME_UNREACHABLE",
                        diagnostic_message=f"Target provider health check failed: {health.diagnostic_message}",
                        duration_ms=elapsed_ms,
                    )
            except Exception as ex:
                logger.error("Target provider health probe exception for %s: %s (Rolling back)", target_model_id, ex)
                elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=previous_model_id,
                    active_model_id=previous_model_id,
                    generation=previous_gen,
                    switched=False,
                    active_session=previous_session,
                    failure_reason="RUNTIME_UNREACHABLE",
                    diagnostic_message=str(ex),
                    duration_ms=elapsed_ms,
                )

            # Step 4: Atomic Commit — Swap Active Session and Advance Generation
            new_generation = previous_gen + 1
            new_session = ActiveModelSession(
                active_model_id=target_model_id,
                provider_id=target_descriptor.provider,
                provider_model_name=target_descriptor.provider_model_name,
                runtime_id=f"{target_descriptor.provider.value}_runtime",
                health_status=health.status,
                session_status=ModelSessionStatus.ACTIVE,
                generation=new_generation,
                capabilities=target_descriptor.capabilities,
                context_window=target_descriptor.context_window,
                endpoint=target_descriptor.endpoint,
                descriptor=target_descriptor,
            )

            new_runtime = create_runtime_adapter(target_descriptor, target_provider)

            self._active_model_id = target_model_id
            self._active_session = new_session
            self._active_runtime = new_runtime
            self._generation = new_generation

            # Step 5: Lifecycle Updates
            if previous_model_id and previous_model_id != target_model_id:
                self._lifecycle_manager.record_transition(
                    previous_model_id,
                    ModelStatus.AVAILABLE,
                    reason=f"Deactivated; replaced by {target_model_id}",
                )
                await self._registry.update_model_status(previous_model_id, ModelStatus.AVAILABLE)
                await self._emit_event(
                    EventType.MODEL_DEACTIVATED,
                    ModelEventPayload(
                        model_id=previous_model_id,
                        provider=previous_session.provider_id.value if previous_session else "unknown",
                        generation=previous_gen,
                        status=ModelSessionStatus.DEACTIVATED.value,
                    ).model_dump(),
                )

            self._lifecycle_manager.record_transition(
                target_model_id,
                ModelStatus.LOADED,
                reason=f"Activated as primary ORBIT model (Gen {new_generation})",
            )
            await self._registry.update_model_status(target_model_id, ModelStatus.LOADED)

            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

            # Step 6: Emit Activated and Switch Succeeded Events
            await self._emit_event(
                EventType.MODEL_ACTIVATED,
                ModelEventPayload(
                    model_id=target_model_id,
                    provider=target_descriptor.provider.value,
                    generation=new_generation,
                    status=ModelSessionStatus.ACTIVE.value,
                ).model_dump(),
            )
            await self._emit_event(
                EventType.MODEL_SWITCH_SUCCEEDED,
                ModelSwitchEventPayload(
                    previous_model_id=previous_model_id,
                    target_model_id=target_model_id,
                    generation=new_generation,
                    is_successful=True,
                    duration_ms=elapsed_ms,
                ).model_dump(),
            )

            logger.info(
                "Successfully switched active model to '%s' (Gen %d, previous: '%s')",
                target_model_id,
                new_generation,
                previous_model_id,
            )

            return ModelSwitchResult(
                is_successful=True,
                previous_model_id=previous_model_id,
                active_model_id=target_model_id,
                generation=new_generation,
                switched=True,
                active_session=new_session,
                duration_ms=elapsed_ms,
            )

    async def deactivate_active_model(self) -> bool:
        """Explicitly deactivate the current active model session."""
        async with self._lock:
            if self._active_model_id is None:
                return False

            prev_id = self._active_model_id
            prev_session = self._active_session
            prev_gen = self._generation

            self._lifecycle_manager.record_transition(
                prev_id,
                ModelStatus.AVAILABLE,
                reason="Explicit model deactivation",
            )
            await self._registry.update_model_status(prev_id, ModelStatus.AVAILABLE)

            self._active_model_id = None
            self._active_session = None
            self._active_runtime = None

            await self._emit_event(
                EventType.MODEL_DEACTIVATED,
                ModelEventPayload(
                    model_id=prev_id,
                    provider=prev_session.provider_id.value if prev_session else "unknown",
                    generation=prev_gen,
                    status=ModelSessionStatus.DEACTIVATED.value,
                ).model_dump(),
            )
            return True

    # -------------------------------------------------------------------------
    # Backwards-Compatible active model setter
    # -------------------------------------------------------------------------

    async def set_active_model(self, model_id: str) -> bool:
        """Transactionally switch the active ORBIT model (Backwards compatible helper).

        Raises typed ModelManagerError exceptions on failure.
        """
        result = await self.switch_model(model_id)
        if result.is_successful:
            return True

        # Raise appropriate typed error
        if result.failure_reason == "MODEL_NOT_FOUND":
            raise ModelNotFoundError(result.diagnostic_message or f"Model '{model_id}' not found")
        elif result.failure_reason in ("RUNTIME_UNREACHABLE", "UNAVAILABLE"):
            raise ProviderUnhealthyError(result.diagnostic_message or f"Provider for '{model_id}' is unreachable")
        elif result.failure_reason == "AUTH_NOT_CONFIGURED":
            raise CloudAuthRequiredError(result.diagnostic_message or f"Auth required for '{model_id}'")
        elif result.failure_reason == "CAPABILITY_MISMATCH":
            raise CapabilityMismatchError(result.diagnostic_message or f"Capability mismatch for '{model_id}'")
        else:
            raise ModelSwitchError(result.diagnostic_message or f"Failed to switch to model '{model_id}'")

    # -------------------------------------------------------------------------
    # Active Session & Runtime Accessors
    # -------------------------------------------------------------------------

    def get_active_model_id(self) -> Optional[str]:
        """Get the ID string of the currently active model."""
        return self._active_model_id

    async def get_active_model(self) -> Optional[ModelDescriptor]:
        """Get descriptor of the currently active model."""
        async with self._lock:
            if self._active_model_id is None:
                return None
            return await self.get_model(self._active_model_id)

    def get_active_session(self) -> Optional[ActiveModelSession]:
        """Get current immutable snapshot of the active model session."""
        return self._active_session

    def get_active_generation(self) -> int:
        """Get current monotonic activation generation counter."""
        return self._generation

    def get_active_runtime(self) -> Optional[ModelRuntimeAdapter]:
        """Get the provider-independent runtime adapter for the active model."""
        return self._active_runtime

    def is_model_active(self) -> bool:
        """Check if an active model session is currently ready for inference."""
        return self._active_session is not None and self._active_runtime is not None

    async def get_model_health(self, model_id: str) -> ProviderHealth:
        """Perform a fresh health probe for a specific model's provider and update registry."""
        descriptor = await self.get_model(model_id)
        if descriptor is None:
            raise ModelNotFoundError(f"Model '{model_id}' not found in registry")

        provider = self._resolve_provider_instance(descriptor.provider)
        if provider is None:
            raise ProviderNotFoundError(f"Provider '{descriptor.provider.value}' for model '{model_id}' is not registered")

        health = await provider.health_check()
        await self._registry.update_model_health(model_id, health)
        if self._active_model_id == model_id:
            if self._active_session:
                self._active_session.health_status = health.status
            if self._active_runtime and hasattr(self._active_runtime, "descriptor"):
                self._active_runtime.descriptor.last_health = health

        await self._emit_event(
            EventType.MODEL_HEALTH_CHANGED,
            ModelHealthEventPayload(
                model_id=model_id,
                provider=descriptor.provider.value,
                status=health.status.value,
                latency_ms=health.latency_ms,
                diagnostic_message=health.diagnostic_message,
            ).model_dump(),
        )

        return health

    # -------------------------------------------------------------------------
    # Active Inference Dispatch with Generation Guard
    # -------------------------------------------------------------------------

    async def generate(self, prompt: str, expected_generation: Optional[int] = None, **kwargs) -> ModelGenerateResponse:
        """Dispatch text generation to the currently active model with generation validation."""
        session = self._active_session
        runtime = self._active_runtime

        if session is None or runtime is None:
            raise NoActiveModelError("No active model selected. Call activate_model() or switch_model() before generating.")

        if expected_generation is not None and expected_generation != session.generation:
            raise StaleModelGenerationError(
                f"Stale model generation: request targeted generation {expected_generation}, "
                f"but active model is generation {session.generation} ({session.active_model_id})."
            )

        request = ModelGenerateRequest(
            prompt=prompt,
            expected_generation=expected_generation,
            **kwargs,
        )
        return await runtime.generate(request)

    async def chat(self, messages: List[ModelChatMessage], expected_generation: Optional[int] = None, **kwargs) -> ModelGenerateResponse:
        """Dispatch chat to the currently active model with generation validation."""
        session = self._active_session
        runtime = self._active_runtime

        if session is None or runtime is None:
            raise NoActiveModelError("No active model selected. Call activate_model() or switch_model() before chatting.")

        if expected_generation is not None and expected_generation != session.generation:
            raise StaleModelGenerationError(
                f"Stale model generation: request targeted generation {expected_generation}, "
                f"but active model is generation {session.generation} ({session.active_model_id})."
            )

        request = ModelChatRequest(
            messages=messages,
            expected_generation=expected_generation,
            **kwargs,
        )
        return await runtime.chat(request)

    async def shutdown(self) -> None:
        """Shutdown all registered providers and release resources."""
        providers = self._discovery_engine.list_providers()
        for p in providers:
            try:
                await p.shutdown()
            except Exception as ex:
                logger.warning("Error shutting down provider %s: %s", p.provider_kind.value, ex)
        for cp in self._inventory.cloud_providers:
            try:
                await cp.shutdown()
            except Exception as ex:
                logger.warning("Error shutting down cloud provider %s: %s", cp.cloud_provider_kind.value, ex)
