"""Central Model Session Manager (Milestone M1.9 Step 4).

The Single Authority responsible for:
- Active model state and session context
- Concurrency-safe activation, deactivation, and switching
- Active-task collision prevention (REJECT_DURING_ACTIVE_TASK policy)
- Transactional switching with atomic rollback (Model A preserved if Model B fails)
- Monotonic generation counter tracking and stale request rejection
- Structured event streaming for future WebSocket gateway integration
- Provider-agnostic inference dispatch

SECURITY INVARIANT:
Zero secrets or credentials are ever emitted, logged, or serialized.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Union
import uuid

from orbit.contracts.events import (
    EventType,
    ModelEventPayload,
    ModelHealthEventPayload,
    ModelSwitchEventPayload,
    RuntimeEvent,
)
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import (
    ActiveModelContext,
    ActiveTaskConflictError,
    ModelActivationRequest,
    ModelActivationResult,
    ModelActivationStatus,
    ModelInitializationError,
    ModelNotFoundError,
    ModelRuntimeHealth,
    ModelRuntimeInfo,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    ModelSwitchPolicy,
    ModelSwitchRejectedError,
    ModelSwitchResult,
    ModelUnavailableError,
    NoActiveModelError,
    StaleModelGenerationError,
)
from orbit.runtime.model_runtime.factory import ModelRuntimeFactory, create_model_runtime
from orbit.runtime.models.models import (
    CloudAuthStatus,
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry
from orbit.runtime.model_providers.base import ModelProvider

logger = logging.getLogger(__name__)


class ModelSessionManager:
    """Single authority for active AI model state and safe runtime switching in ORBIT."""

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        providers: Optional[List[ModelProvider]] = None,
        event_bus: Optional[EventBus] = None,
        is_task_executing_fn: Optional[Callable[[], bool]] = None,
        task_cancel_fn: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._registry = registry or ModelRegistry()
        self._providers = providers or []
        self._factory = ModelRuntimeFactory(providers=self._providers)
        self._event_bus = event_bus
        self._is_task_executing_fn = is_task_executing_fn
        self._task_cancel_fn = task_cancel_fn

        self._active_runtime: Optional[BaseModelRuntime] = None
        self._active_context: Optional[ActiveModelContext] = None
        self._generation: int = 0
        self._lock = asyncio.Lock()
        self._event_seq: int = 0

    @property
    def event_bus(self) -> Optional[EventBus]:
        return self._event_bus

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Attach or update the system event bus."""
        self._event_bus = event_bus

    def set_task_executing_predicate(self, predicate: Callable[[], bool]) -> None:
        """Set callback to check if an autonomous task is actively executing."""
        self._is_task_executing_fn = predicate

    def set_task_cancel_callback(self, callback: Callable[[], Any]) -> None:
        """Set callback to cancel active tasks when CANCEL_AND_SWITCH policy is requested."""
        self._task_cancel_fn = callback

    def register_provider(self, provider: ModelProvider) -> None:
        """Register a provider backend."""
        self._providers.append(provider)
        self._factory.register_provider(provider)

    async def register_descriptor(self, descriptor: ModelDescriptor) -> None:
        """Register a model descriptor in the local registry."""
        await self._registry.register_model(descriptor)

    # =========================================================================
    # Query API
    # =========================================================================

    def get_active_model(self) -> Optional[ActiveModelContext]:
        """Return the current active model context snapshot, or None."""
        return self._active_context

    def get_active_context(self) -> Optional[ActiveModelContext]:
        """Alias for get_active_model()."""
        return self._active_context

    def get_active_generation(self) -> int:
        """Return the current monotonic activation generation counter."""
        return self._generation

    def is_model_active(self) -> bool:
        """Whether a model runtime is currently active and ready for inference."""
        return self._active_runtime is not None and self._active_runtime.is_initialized

    def get_active_runtime(self) -> Optional[BaseModelRuntime]:
        """Return active BaseModelRuntime adapter instance."""
        return self._active_runtime

    def get_runtime_status(self) -> ModelRuntimeStatus:
        """Return current status of active runtime, or STOPPED if none active."""
        if self._active_runtime is None:
            return ModelRuntimeStatus.STOPPED
        return self._active_runtime.status

    async def get_runtime_health(self) -> Optional[ModelRuntimeHealth]:
        """Probe and return health of the active model runtime."""
        if self._active_runtime is None:
            return None
        health = await self._active_runtime.health_check()
        # Emit health changed event if status changed
        await self._emit_event(
            EventType.MODEL_HEALTH_CHANGED,
            payload=ModelHealthEventPayload(
                model_id=self._active_runtime.model_id,
                provider=self._active_runtime.descriptor.provider.value,
                status=health.status.value,
                latency_ms=health.latency_ms,
                diagnostic_message=health.diagnostic_message,
            ).model_dump(),
        )
        return health

    # =========================================================================
    # Activation API
    # =========================================================================

    async def activate_model(
        self,
        request_or_model_id: Union[str, ModelActivationRequest],
        descriptor: Optional[ModelDescriptor] = None,
    ) -> ModelActivationResult:
        """Activate a model runtime as ORBIT's primary active model."""
        if isinstance(request_or_model_id, str):
            request = ModelActivationRequest(model_id=request_or_model_id)
        else:
            request = request_or_model_id

        start_time = time.perf_counter()
        target_model_id = request.model_id

        async with self._lock:
            # 1. Check if already active
            if (
                self._active_runtime is not None
                and self._active_runtime.model_id == target_model_id
                and self._active_runtime.is_initialized
            ):
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return ModelActivationResult(
                    is_successful=True,
                    model_id=target_model_id,
                    status=ModelActivationStatus.ALREADY_ACTIVE,
                    generation=self._generation,
                    active_context=self._active_context,
                    duration_ms=duration_ms,
                )

            # 2. Check task execution conflict if currently active model is changing
            if self._active_runtime is not None:
                conflict_result = self._check_task_conflict(request.policy)
                if conflict_result:
                    return conflict_result

            # 3. Resolve descriptor
            if descriptor is not None:
                target_descriptor = descriptor
            elif hasattr(self._registry, "get_model"):
                target_descriptor = await self._registry.get_model(target_model_id)
            else:
                target_descriptor = None

            if target_descriptor is None:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return ModelActivationResult(
                    is_successful=False,
                    model_id=target_model_id,
                    status=ModelActivationStatus.MODEL_NOT_FOUND,
                    failure_reason="MODEL_NOT_FOUND",
                    diagnostic_message=f"Model '{target_model_id}' was not found in registry",
                    duration_ms=duration_ms,
                )

            # 4. Check capability constraints
            if request.required_capabilities:
                missing = request.required_capabilities - target_descriptor.capabilities
                if missing:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    missing_str = ", ".join(c.value for c in missing)
                    return ModelActivationResult(
                        is_successful=False,
                        model_id=target_model_id,
                        status=ModelActivationStatus.SWITCH_REJECTED,
                        failure_reason="CAPABILITY_MISMATCH",
                        diagnostic_message=f"Model lacks required capabilities: {missing_str}",
                        duration_ms=duration_ms,
                    )

            # 5. Emit MODEL_ACTIVATION_STARTED / MODEL_ACTIVATING
            await self._emit_event(
                EventType.MODEL_ACTIVATION_STARTED,
                payload=ModelEventPayload(
                    model_id=target_model_id,
                    provider=target_descriptor.provider.value,
                    generation=self._generation + 1,
                    status="ACTIVATING",
                ).model_dump(),
            )
            await self._emit_event(
                EventType.MODEL_ACTIVATING,
                payload=ModelEventPayload(
                    model_id=target_model_id,
                    provider=target_descriptor.provider.value,
                    generation=self._generation + 1,
                    status="ACTIVATING",
                ).model_dump(),
            )

            # 6. Instantiate runtime adapter
            try:
                new_runtime = self._factory.create_runtime(descriptor=target_descriptor)
            except Exception as ex:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                logger.error("Failed to instantiate runtime for %s: %s", target_model_id, ex)
                return ModelActivationResult(
                    is_successful=False,
                    model_id=target_model_id,
                    status=ModelActivationStatus.INITIALIZATION_FAILED,
                    failure_reason="INSTANTIATION_FAILED",
                    diagnostic_message=str(ex),
                    duration_ms=duration_ms,
                )

            # 7. Initialize runtime (lazy allocation & warmup)
            init_result = await new_runtime.initialize(
                timeout_seconds=request.timeout_seconds,
                preload_weights=request.preload_weights,
            )
            if not init_result.is_success:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                await self._emit_event(
                    EventType.MODEL_RUNTIME_FAILED,
                    payload=ModelEventPayload(
                        model_id=target_model_id,
                        provider=target_descriptor.provider.value,
                        generation=self._generation,
                        status="FAILED",
                        reason=init_result.error_message,
                    ).model_dump(),
                )
                return ModelActivationResult(
                    is_successful=False,
                    model_id=target_model_id,
                    status=ModelActivationStatus.INITIALIZATION_FAILED,
                    failure_reason="INITIALIZATION_FAILED",
                    diagnostic_message=init_result.error_message or "Runtime initialization failed",
                    duration_ms=duration_ms,
                )

            # 8. Perform initial health check
            health = await new_runtime.health_check()
            if not health.is_healthy:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                await new_runtime.shutdown()
                return ModelActivationResult(
                    is_successful=False,
                    model_id=target_model_id,
                    status=ModelActivationStatus.MODEL_UNAVAILABLE,
                    failure_reason="HEALTH_CHECK_FAILED",
                    diagnostic_message=health.diagnostic_message or "Post-activation health check failed",
                    duration_ms=duration_ms,
                )

            # 9. Clean up previous active runtime if any
            if self._active_runtime is not None:
                prev_id = self._active_runtime.model_id
                try:
                    await self._active_runtime.shutdown()
                    await self._emit_event(
                        EventType.MODEL_DEACTIVATED,
                        payload=ModelEventPayload(
                            model_id=prev_id,
                            provider=self._active_runtime.descriptor.provider.value,
                            generation=self._generation,
                            status="DEACTIVATED",
                        ).model_dump(),
                    )
                except Exception as ex:
                    logger.warning("Error shutting down previous runtime %s: %s", prev_id, ex)

            # 10. Commit new active runtime and increment monotonic generation
            self._generation += 1
            new_runtime.set_active_state(True)
            self._active_runtime = new_runtime

            self._active_context = ActiveModelContext(
                model_id=target_model_id,
                display_name=target_descriptor.display_name or target_descriptor.provider_model_name,
                provider=target_descriptor.provider,
                runtime_kind=new_runtime.runtime_kind,
                runtime_status=ModelRuntimeStatus.ACTIVE,
                health=health,
                activated_at=datetime.now(timezone.utc),
                generation=self._generation,
                capabilities=target_descriptor.capabilities,
                context_window=target_descriptor.context_window,
                endpoint=target_descriptor.endpoint,
                descriptor=target_descriptor,
                metadata=target_descriptor.metadata,
            )

            # 11. Emit MODEL_ACTIVATED
            await self._emit_event(
                EventType.MODEL_ACTIVATED,
                payload=ModelEventPayload(
                    model_id=target_model_id,
                    provider=target_descriptor.provider.value,
                    generation=self._generation,
                    status="ACTIVE",
                    details={
                        "runtime_kind": new_runtime.runtime_kind.value,
                        "capabilities": [c.value for c in target_descriptor.capabilities],
                        "context_window": target_descriptor.context_window,
                    },
                ).model_dump(),
            )

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info("Activated model %s (gen: %d) in %.2fms", target_model_id, self._generation, duration_ms)
            return ModelActivationResult(
                is_successful=True,
                model_id=target_model_id,
                status=ModelActivationStatus.ACTIVATED,
                generation=self._generation,
                active_context=self._active_context,
                duration_ms=duration_ms,
            )

    # =========================================================================
    # Safe Switching API with Transactional Rollback
    # =========================================================================

    async def switch_model(
        self,
        new_model_id: str,
        policy: ModelSwitchPolicy = ModelSwitchPolicy.REJECT_DURING_ACTIVE_TASK,
        timeout_seconds: float = 30.0,
        preload_weights: bool = True,
        required_capabilities: Optional[Set[ModelCapability]] = None,
    ) -> ModelSwitchResult:
        """Switch from currently active model to target model with atomic rollback."""
        start_time = time.perf_counter()

        async with self._lock:
            prev_model_id = self._active_runtime.model_id if self._active_runtime else None

            # 1. Already active check
            if prev_model_id == new_model_id and self._active_runtime and self._active_runtime.is_initialized:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return ModelSwitchResult(
                    is_successful=True,
                    previous_model_id=prev_model_id,
                    active_model_id=new_model_id,
                    generation=self._generation,
                    switched=False,
                    status=ModelActivationStatus.ALREADY_ACTIVE,
                    active_context=self._active_context,
                    duration_ms=duration_ms,
                )

            # 2. Check active task conflict
            if self._is_task_executing_fn and self._is_task_executing_fn():
                if policy == ModelSwitchPolicy.REJECT_DURING_ACTIVE_TASK:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.warning("Rejected switch to %s: autonomous task is actively executing", new_model_id)
                    return ModelSwitchResult(
                        is_successful=False,
                        previous_model_id=prev_model_id,
                        active_model_id=prev_model_id,
                        generation=self._generation,
                        switched=False,
                        status=ModelActivationStatus.ACTIVE_TASK_CONFLICT,
                        active_context=self._active_context,
                        failure_reason="ACTIVE_TASK_CONFLICT",
                        diagnostic_message="Model switch rejected: an autonomous task is currently actively executing",
                        duration_ms=duration_ms,
                    )
                elif policy == ModelSwitchPolicy.CANCEL_AND_SWITCH:
                    if self._task_cancel_fn:
                        logger.info("Cancelling active task to perform model switch to %s", new_model_id)
                        try:
                            res = self._task_cancel_fn()
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception as ex:
                            logger.warning("Error cancelling task for model switch: %s", ex)

            # 3. Resolve target descriptor
            if hasattr(self._registry, "get_model"):
                target_descriptor = await self._registry.get_model(new_model_id)
            else:
                target_descriptor = None

            if target_descriptor is None:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=prev_model_id,
                    active_model_id=prev_model_id,
                    generation=self._generation,
                    switched=False,
                    status=ModelActivationStatus.MODEL_NOT_FOUND,
                    active_context=self._active_context,
                    failure_reason="MODEL_NOT_FOUND",
                    diagnostic_message=f"Target model '{new_model_id}' was not found in registry",
                    duration_ms=duration_ms,
                )

            # 4. Validate capabilities
            if required_capabilities:
                missing = required_capabilities - target_descriptor.capabilities
                if missing:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    missing_str = ", ".join(c.value for c in missing)
                    return ModelSwitchResult(
                        is_successful=False,
                        previous_model_id=prev_model_id,
                        active_model_id=prev_model_id,
                        generation=self._generation,
                        switched=False,
                        status=ModelActivationStatus.SWITCH_REJECTED,
                        active_context=self._active_context,
                        failure_reason="CAPABILITY_MISMATCH",
                        diagnostic_message=f"Target model lacks required capabilities: {missing_str}",
                        duration_ms=duration_ms,
                    )

            # 5. Emit MODEL_SWITCH_REQUESTED and MODEL_SWITCH_STARTED
            await self._emit_event(
                EventType.MODEL_SWITCH_REQUESTED,
                payload=ModelSwitchEventPayload(
                    previous_model_id=prev_model_id,
                    target_model_id=new_model_id,
                    generation=self._generation,
                    is_successful=False,
                ).model_dump(),
            )
            await self._emit_event(
                EventType.MODEL_SWITCH_STARTED,
                payload=ModelSwitchEventPayload(
                    previous_model_id=prev_model_id,
                    target_model_id=new_model_id,
                    generation=self._generation,
                    is_successful=False,
                ).model_dump(),
            )

            # 6. Prepare target runtime instance (Zero destruction of Model A!)
            try:
                candidate_runtime = self._factory.create_runtime(descriptor=target_descriptor)
            except Exception as ex:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                logger.error("Target runtime creation failed for %s: %s (Model %s retained)", new_model_id, ex, prev_model_id)
                await self._emit_switch_failed(prev_model_id, new_model_id, "INSTANTIATION_FAILED", str(ex), duration_ms)
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=prev_model_id,
                    active_model_id=prev_model_id,
                    generation=self._generation,
                    switched=False,
                    status=ModelActivationStatus.INITIALIZATION_FAILED,
                    active_context=self._active_context,
                    failure_reason="INSTANTIATION_FAILED",
                    diagnostic_message=str(ex),
                    duration_ms=duration_ms,
                )

            # 7. Initialize target runtime
            init_res = await candidate_runtime.initialize(
                timeout_seconds=timeout_seconds,
                preload_weights=preload_weights,
            )
            if not init_res.is_success:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                logger.warning("Target initialization failed for %s: %s (Model %s retained)", new_model_id, init_res.error_message, prev_model_id)
                await self._emit_switch_failed(prev_model_id, new_model_id, "INITIALIZATION_FAILED", init_res.error_message or "", duration_ms)
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=prev_model_id,
                    active_model_id=prev_model_id,
                    generation=self._generation,
                    switched=False,
                    status=ModelActivationStatus.INITIALIZATION_FAILED,
                    active_context=self._active_context,
                    failure_reason="INITIALIZATION_FAILED",
                    diagnostic_message=init_res.error_message or "Target model initialization failed",
                    duration_ms=duration_ms,
                )

            # 8. Probe candidate health
            health = await candidate_runtime.health_check()
            if not health.is_healthy:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                await candidate_runtime.shutdown()
                logger.warning("Target health probe failed for %s (Model %s retained)", new_model_id, prev_model_id)
                await self._emit_switch_failed(prev_model_id, new_model_id, "HEALTH_CHECK_FAILED", health.diagnostic_message or "", duration_ms)
                return ModelSwitchResult(
                    is_successful=False,
                    previous_model_id=prev_model_id,
                    active_model_id=prev_model_id,
                    generation=self._generation,
                    switched=False,
                    status=ModelActivationStatus.MODEL_UNAVAILABLE,
                    active_context=self._active_context,
                    failure_reason="HEALTH_CHECK_FAILED",
                    diagnostic_message=health.diagnostic_message or "Target model health probe failed",
                    duration_ms=duration_ms,
                )

            # =================================================================
            # Point of No Return: Commit Switch
            # =================================================================
            old_runtime = self._active_runtime
            if old_runtime is not None:
                try:
                    await old_runtime.shutdown()
                except Exception as ex:
                    logger.warning("Error tearing down old runtime %s: %s", prev_model_id, ex)

            self._generation += 1
            candidate_runtime.set_active_state(True)
            self._active_runtime = candidate_runtime

            self._active_context = ActiveModelContext(
                model_id=new_model_id,
                display_name=target_descriptor.display_name or target_descriptor.provider_model_name,
                provider=target_descriptor.provider,
                runtime_kind=candidate_runtime.runtime_kind,
                runtime_status=ModelRuntimeStatus.ACTIVE,
                health=health,
                activated_at=datetime.now(timezone.utc),
                generation=self._generation,
                capabilities=target_descriptor.capabilities,
                context_window=target_descriptor.context_window,
                endpoint=target_descriptor.endpoint,
                descriptor=target_descriptor,
                metadata=target_descriptor.metadata,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Emit MODEL_SWITCH_SUCCEEDED and MODEL_SWITCHED
            await self._emit_event(
                EventType.MODEL_SWITCH_SUCCEEDED,
                payload=ModelSwitchEventPayload(
                    previous_model_id=prev_model_id,
                    target_model_id=new_model_id,
                    generation=self._generation,
                    is_successful=True,
                    duration_ms=duration_ms,
                ).model_dump(),
            )
            await self._emit_event(
                EventType.MODEL_SWITCHED,
                payload=ModelSwitchEventPayload(
                    previous_model_id=prev_model_id,
                    target_model_id=new_model_id,
                    generation=self._generation,
                    is_successful=True,
                    duration_ms=duration_ms,
                ).model_dump(),
            )

            logger.info("Switched from %s to %s (gen: %d) in %.2fms", prev_model_id, new_model_id, self._generation, duration_ms)
            return ModelSwitchResult(
                is_successful=True,
                previous_model_id=prev_model_id,
                active_model_id=new_model_id,
                generation=self._generation,
                switched=True,
                status=ModelActivationStatus.ACTIVATED,
                active_context=self._active_context,
                duration_ms=duration_ms,
            )

    # =========================================================================
    # Shutdown API
    # =========================================================================

    async def shutdown_active_model(self) -> None:
        """Gracefully release and shut down the currently active model runtime."""
        async with self._lock:
            if self._active_runtime is not None:
                model_id = self._active_runtime.model_id
                provider_str = self._active_runtime.descriptor.provider.value
                try:
                    await self._active_runtime.shutdown()
                except Exception as ex:
                    logger.warning("Error shutting down runtime %s: %s", model_id, ex)

                await self._emit_event(
                    EventType.MODEL_SHUTDOWN,
                    payload=ModelEventPayload(
                        model_id=model_id,
                        provider=provider_str,
                        generation=self._generation,
                        status="STOPPED",
                    ).model_dump(),
                )
                await self._emit_event(
                    EventType.MODEL_DEACTIVATED,
                    payload=ModelEventPayload(
                        model_id=model_id,
                        provider=provider_str,
                        generation=self._generation,
                        status="DEACTIVATED",
                    ).model_dump(),
                )
                self._active_runtime = None
                self._active_context = None

    async def shutdown(self) -> None:
        """Alias for shutdown_active_model()."""
        await self.shutdown_active_model()

    # =========================================================================
    # Generation-Guarded Inference Dispatch
    # =========================================================================

    async def generate(self, request: ModelGenerateRequest) -> ModelGenerateResponse:
        """Execute text completion with monotonic generation safety guard."""
        if self._active_runtime is None or not self._active_runtime.is_initialized:
            raise NoActiveModelError("Cannot generate: no AI model is currently active in ORBIT")

        # Stale generation check
        if request.expected_generation is not None and request.expected_generation != self._generation:
            raise StaleModelGenerationError(
                f"Generation conflict: request expected generation {request.expected_generation}, "
                f"but current active generation is {self._generation}"
            )

        try:
            return await self._active_runtime.generate(request)
        except Exception as ex:
            if self._active_runtime.status == ModelRuntimeStatus.FAILED:
                await self._emit_event(
                    EventType.MODEL_RUNTIME_FAILED,
                    payload=ModelEventPayload(
                        model_id=self._active_runtime.model_id,
                        provider=self._active_runtime.descriptor.provider.value,
                        generation=self._generation,
                        status="FAILED",
                        reason=str(ex),
                    ).model_dump(),
                )
            raise

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        """Execute conversational turn with monotonic generation safety guard."""
        if self._active_runtime is None or not self._active_runtime.is_initialized:
            raise NoActiveModelError("Cannot chat: no AI model is currently active in ORBIT")

        # Stale generation check
        if request.expected_generation is not None and request.expected_generation != self._generation:
            raise StaleModelGenerationError(
                f"Generation conflict: request expected generation {request.expected_generation}, "
                f"but current active generation is {self._generation}"
            )

        try:
            return await self._active_runtime.chat(request)
        except Exception as ex:
            if self._active_runtime.status == ModelRuntimeStatus.FAILED:
                await self._emit_event(
                    EventType.MODEL_RUNTIME_FAILED,
                    payload=ModelEventPayload(
                        model_id=self._active_runtime.model_id,
                        provider=self._active_runtime.descriptor.provider.value,
                        generation=self._generation,
                        status="FAILED",
                        reason=str(ex),
                    ).model_dump(),
                )
            raise

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _check_task_conflict(self, policy: ModelSwitchPolicy) -> Optional[ModelActivationResult]:
        """Check if active task execution prevents model activation."""
        if self._is_task_executing_fn and self._is_task_executing_fn():
            if policy == ModelSwitchPolicy.REJECT_DURING_ACTIVE_TASK:
                return ModelActivationResult(
                    is_successful=False,
                    model_id=self._active_runtime.model_id if self._active_runtime else "",
                    status=ModelActivationStatus.ACTIVE_TASK_CONFLICT,
                    generation=self._generation,
                    active_context=self._active_context,
                    failure_reason="ACTIVE_TASK_CONFLICT",
                    diagnostic_message="Activation rejected: an autonomous task is currently executing",
                )
        return None

    async def _emit_switch_failed(
        self,
        prev_id: Optional[str],
        target_id: str,
        reason: str,
        diag: str,
        duration_ms: float,
    ) -> None:
        """Emit MODEL_SWITCH_FAILED event."""
        await self._emit_event(
            EventType.MODEL_SWITCH_FAILED,
            payload=ModelSwitchEventPayload(
                previous_model_id=prev_id,
                target_model_id=target_id,
                generation=self._generation,
                is_successful=False,
                failure_reason=reason,
                diagnostic_message=diag,
                duration_ms=duration_ms,
            ).model_dump(),
        )

    async def _emit_event(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Emit a secret-sanitized structured event onto the system event bus."""
        if self._event_bus is None:
            return
        self._event_seq += 1
        event = RuntimeEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            event_seq=self._event_seq,
            timestamp=datetime.now(timezone.utc),
            session_id="model_session",
            payload=payload,
        )
        try:
            await self._event_bus.publish(event)
        except Exception as ex:
            logger.warning("Failed to publish model event %s: %s", event_type.value, ex)
