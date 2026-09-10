"""Central ORBIT Runtime Orchestrator coordinating task lifecycles and capabilities."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityNotFoundError,
    CapabilityUnavailableError,
)
from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.takeover.state import TakeoverState
from orbit.config import is_human_takeover_enabled

from orbit.contracts.capabilities import (
    CapabilityLifecycleState,
    CapabilityType,
    EmergencySafetyCoordinator,
    HumanTakeoverCapability,
    KeyboardCapability,
    ObservationCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.contracts.events import (
    ActionStagePayload,
    ErrorEventPayload,
    EventType,
    PlanUpdatedPayload,
    RuntimeEvent,
    RuntimeStatusPayload,
    TaskStatePayload,
    TakeoverEventPayload,
)
from orbit.contracts.runtime import (
    Action,
    ActionStage,
    ActionTier,
    ErrorDetail,
    ExecutionPlan,
    Step,
    SystemState,
    Task,
    TaskStatus,
    VerificationResult,
    VerificationStatus,
)
from orbit.infrastructure.clock import Clock, SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cancellation import CancellationSource, CancellationToken
from orbit.runtime.perception import SemanticPerceptionEngine
from orbit.runtime.state_machine import ActionStateMachine, SystemStateMachine
from orbit.runtime.task_manager import TaskManager
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    ResolvedTarget,
    TargetIntent,
    TargetLocator,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetStrategy,
)
from orbit.runtime.verification import (
    ActionVerificationResult,
    ActionVerifier,
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
    VerificationStrategy,
)
from orbit.runtime.task_completion import (
    GoalVerificationResult,
    GoalVerifier,
    TaskExecutionResult,
)
from orbit.runtime.cognitive import (
    AgentExecutionLoop,
    AgentExecutionResult,
)
from orbit.runtime.models import (
    ActiveModelSession,
    InventoryReport,
    ModelManager,
    ModelRuntimeAdapter,
)
from orbit.runtime.models.models import (
    CloudProviderKind,
    ModelGenerateRequest,
    ModelProviderKind,
)
from orbit.runtime.model_runtime import (
    ActiveModelContext,
    ModelActivationRequest,
    ModelRouter,
    ModelSessionManager,
    RoutingPolicy,
)
from orbit.runtime.model_providers import (
    OllamaProvider,
    LMStudioProvider,
    CloudModelProvider,
)

from orbit.runtime.history import (
    CompletionEvidenceRecord,
    ExecutionHistoryStore,
    ExecutionRecord,
    ExecutionStatus,
    ExecutionStepRecord,
    ReplanAuditRecord,
)
from orbit.runtime.diagnostics.service import DiagnosticService

logger = logging.getLogger(__name__)


class OrbitOrchestrator:
    """Core runtime engine for ORBIT."""

    def __init__(
        self,
        event_bus: EventBus,
        registry: Optional[CapabilityRegistry] = None,
        observation: Optional[ObservationCapability] = None,
        pointer: Optional[PointerCapability] = None,
        keyboard: Optional[KeyboardCapability] = None,
        takeover: Optional[HumanTakeoverCapability] = None,
        workspace: Optional[WorkspaceCapability] = None,
        safety: Optional[EmergencySafetyCoordinator] = None,
        clock: Optional[Clock] = None,
        perception_engine: Optional[SemanticPerceptionEngine] = None,
        target_locator: Optional[TargetLocator] = None,
        action_verifier: Optional[ActionVerifier] = None,
        model_manager: Optional[ModelManager] = None,
        model_session_manager: Optional[ModelSessionManager] = None,
        history_store: Optional[ExecutionHistoryStore] = None,
        auto_activate_models: bool = False,
        human_takeover_enabled: Optional[bool] = None,
    ) -> None:
        self._event_bus = event_bus
        self._clock = clock or SystemClock()
        self._auto_activate_models = auto_activate_models
        self._human_takeover_enabled = human_takeover_enabled
        self._perception_engine = perception_engine or SemanticPerceptionEngine()
        self._target_locator = target_locator or EvidenceBasedTargetLocator(perception_engine=self._perception_engine)
        self._action_verifier = action_verifier or ActionVerifier()

        # Set up registry: use provided or build from passed capabilities
        if registry is not None:
            self._registry = registry
        else:
            self._registry = CapabilityRegistry()
            if observation and isinstance(observation, BaseCapabilityAdapter):
                self._registry.register(CapabilityType.OBSERVATION, observation)
            if pointer and isinstance(pointer, BaseCapabilityAdapter):
                self._registry.register(CapabilityType.POINTER, pointer)
            if keyboard and isinstance(keyboard, BaseCapabilityAdapter):
                self._registry.register(CapabilityType.KEYBOARD, keyboard)
            if takeover and isinstance(takeover, BaseCapabilityAdapter):
                self._registry.register(CapabilityType.HUMAN_TAKEOVER, takeover)
            if workspace and isinstance(workspace, BaseCapabilityAdapter):
                self._registry.register(CapabilityType.WORKSPACE, workspace)
            if safety and isinstance(safety, BaseCapabilityAdapter):
                self._registry.register(CapabilityType.SAFETY, safety)

        # Wire safety coordinator with registry if supported
        sft_adapter = self._registry.get_optional(CapabilityType.SAFETY)
        if sft_adapter and hasattr(sft_adapter, "set_registry"):
            sft_adapter.set_registry(self._registry)

        self._task_manager = TaskManager()
        self._system_sm = SystemStateMachine(SystemState.BOOTING)
        cloud_provs = [
            CloudModelProvider(cloud_kind=CloudProviderKind.OPENAI),
            CloudModelProvider(cloud_kind=CloudProviderKind.ANTHROPIC),
            CloudModelProvider(cloud_kind=CloudProviderKind.GEMINI),
        ]
        self._model_manager = model_manager or ModelManager(
            providers=[OllamaProvider(), LMStudioProvider()],
            cloud_providers=cloud_provs,
            event_bus=self._event_bus,
        )
        if self._model_manager.event_bus is None:
            self._model_manager.set_event_bus(self._event_bus)
        self._model_session_manager = model_session_manager or ModelSessionManager(
            registry=self._model_manager.registry,
            providers=self._model_manager.providers + cloud_provs,
            event_bus=self._event_bus,
            is_task_executing_fn=lambda: self.is_task_executing,
        )
        if self._model_session_manager.event_bus is None:
            self._model_session_manager.set_event_bus(self._event_bus)
        self._model_session_manager.set_task_executing_predicate(lambda: self.is_task_executing)
        self._model_router = ModelRouter(session_manager=self._model_session_manager)
        self._goal_verifier = GoalVerifier(
            perception_engine=self._perception_engine,
        )
        self._agent_loop = AgentExecutionLoop(
            router=self._model_router,
            model_session_manager=self._model_session_manager,
            workspace=self.workspace,
            pointer=self.pointer,
            keyboard=self.keyboard,
            observation=self.observation,
            goal_verifier=self._goal_verifier,
            target_locator=self._target_locator,
            event_bus=self._event_bus,
        )
        self._cognitive_loop = self._agent_loop
        self._history_store = history_store or ExecutionHistoryStore()
        self._diagnostic_service = DiagnosticService(orchestrator=self)
        self._active_cancellation_sources: Dict[str, CancellationSource] = {}
        self._active_execution_tasks: Dict[str, asyncio.Task] = {}
        self._active_desktop_tasks: Set[str] = set()
        self._last_takeover_info: Dict[str, Any] = {}
        self._takeover_history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    @property
    def is_human_takeover_enabled(self) -> bool:
        """Query whether Human Takeover preemption feature is active."""
        if self._human_takeover_enabled is not None:
            return self._human_takeover_enabled
        return is_human_takeover_enabled()

    @property
    def diagnostic_service(self) -> DiagnosticService:
        return self._diagnostic_service

    @property
    def history_store(self) -> ExecutionHistoryStore:
        return self._history_store

    @property
    def system_state(self) -> SystemState:
        return self._system_sm.current_state

    @property
    def last_takeover_info(self) -> Dict[str, Any]:
        return dict(self._last_takeover_info)

    @property
    def takeover_history(self) -> List[Dict[str, Any]]:
        return list(self._takeover_history)

    async def is_human_takeover_active(self) -> bool:
        """Check whether human takeover is actively preempting execution."""
        if not self.is_human_takeover_enabled:
            return False
        tkv = self.takeover
        if tkv and hasattr(tkv, "is_takeover_active"):
            res = tkv.is_takeover_active()
            import inspect
            if inspect.isawaitable(res):
                return await res
            return bool(res)
        return self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE


    @property
    def task_manager(self) -> TaskManager:
        return self._task_manager

    @property
    def agent_loop(self) -> AgentExecutionLoop:
        return self._agent_loop

    @property
    def model_router(self) -> ModelRouter:
        return self._model_router

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def target_locator(self) -> TargetLocator:
        return self._target_locator

    @property
    def action_verifier(self) -> ActionVerifier:
        return self._action_verifier

    @property
    def perception_engine(self) -> SemanticPerceptionEngine:
        return self._perception_engine


    # Capability helpers
    @property
    def observation(self) -> Optional[ObservationCapability]:
        adapter = self._registry.get_optional(CapabilityType.OBSERVATION)
        return adapter if isinstance(adapter, ObservationCapability) else None

    @property
    def pointer(self) -> Optional[PointerCapability]:
        adapter = self._registry.get_optional(CapabilityType.POINTER)
        return adapter if isinstance(adapter, PointerCapability) else None

    @property
    def keyboard(self) -> Optional[KeyboardCapability]:
        adapter = self._registry.get_optional(CapabilityType.KEYBOARD)
        return adapter if isinstance(adapter, KeyboardCapability) else None

    @property
    def takeover(self) -> Optional[HumanTakeoverCapability]:
        adapter = self._registry.get_optional(CapabilityType.HUMAN_TAKEOVER)
        return adapter if isinstance(adapter, HumanTakeoverCapability) else None

    @property
    def workspace(self) -> Optional[WorkspaceCapability]:
        adapter = self._registry.get_optional(CapabilityType.WORKSPACE)
        return adapter if isinstance(adapter, WorkspaceCapability) else None

    @property
    def safety(self) -> Optional[EmergencySafetyCoordinator]:
        adapter = self._registry.get_optional(CapabilityType.SAFETY)
        return adapter if isinstance(adapter, EmergencySafetyCoordinator) else None

    @property
    def is_task_executing(self) -> bool:
        """Whether an autonomous task or plan is currently actively executing."""
        running_tasks = [t for t in self._active_execution_tasks.values() if not t.done()]
        return bool(running_tasks) or (self._system_sm.current_state == SystemState.BUSY) or bool(self._active_desktop_tasks)

    @property
    def model_manager(self) -> ModelManager:
        return self._model_manager

    @property
    def model_session_manager(self) -> ModelSessionManager:
        """Central Model Session Manager (M1.9 Step 4)."""
        return self._model_session_manager

    @property
    def active_model_context(self) -> Optional[ActiveModelContext]:
        """Current immutable snapshot of the active AI model context (M1.9 Step 4)."""
        return self._model_session_manager.get_active_context()

    @property
    def active_model_session(self) -> Optional[ActiveModelSession]:
        """Current immutable snapshot of the active AI model session."""
        return self._model_manager.get_active_session()

    @property
    def active_model_generation(self) -> int:
        """Current monotonic active model generation counter."""
        return self._model_manager.get_active_generation()

    @property
    def is_model_active(self) -> bool:
        """Whether an active AI model is loaded and ready for inference."""
        return self._model_manager.is_model_active()

    @property
    def active_model_runtime(self) -> Optional[ModelRuntimeAdapter]:
        """Unified runtime adapter for the active AI model."""
        return self._model_manager.get_active_runtime()

    async def get_model_inventory_report(self) -> InventoryReport:
        """Get the latest AI model system inventory report without blocking."""
        return await self._model_manager.get_inventory_report()

    async def refresh_model_inventory(
        self,
        include_runtimes: bool = True,
        include_cloud: bool = True,
        include_files: bool = True,
    ) -> InventoryReport:
        """Execute a full inventory refresh across all available model sources."""
        return await self._model_manager.refresh_inventory(
            include_runtimes=include_runtimes,
            include_cloud=include_cloud,
            include_files=include_files,
        )

    async def initialize(self) -> None:
        """Initialize capabilities and transition system state to IDLE."""
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            # Initialize all capabilities via registry
            health_reports = await self._registry.initialize_all()

            # Register takeover hook callback if takeover capability is registered and ready
            if self._registry.is_ready(CapabilityType.HUMAN_TAKEOVER):
                tkv = self._registry.resolve_typed(CapabilityType.HUMAN_TAKEOVER, HumanTakeoverCapability)
                await tkv.start_monitoring(self._on_physical_takeover_detected)
                if hasattr(tkv, "state_manager"):
                    tkv.state_manager.add_listener(self._on_takeover_state_changed)

            # Reset any stale takeover state on startup if feature is disabled
            if not self.is_human_takeover_enabled:
                self._last_takeover_info = {}
                tkv = self.takeover
                if tkv and hasattr(tkv, "reset_takeover_state"):
                    await tkv.reset_takeover_state()

            # Wire takeover check to workspace capability if supported
            wsp_adapter = self._registry.get_optional(CapabilityType.WORKSPACE)
            if wsp_adapter:
                setattr(wsp_adapter, "is_takeover_active_fn", lambda: self.is_human_takeover_enabled and self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE)

            self._system_sm.transition_to(SystemState.IDLE)


        # Build capability status dictionary for telemetry
        cap_summary = {
            cap_type.value: report.lifecycle_state.value
            for cap_type, report in health_reports.items()
        }

        await self._emit_event(
            EventType.RUNTIME_STATUS,
            session_id="system",
            payload=RuntimeStatusPayload(
                system_state=self._system_sm.current_state,
                capabilities=cap_summary,
            ).model_dump(),
        )
        logger.info("OrbitOrchestrator initialized and state is IDLE (Capabilities: %s)", cap_summary)

        # Auto-discover local models and register descriptors in ModelSessionManager
        try:
            inv_report = await self._model_manager.refresh_inventory()
            for desc in inv_report.models:
                await self._model_session_manager.register_descriptor(desc)
            if self._auto_activate_models and not self._model_session_manager.is_model_active() and inv_report.models:
                # Prefer Ollama local models first
                local_candidates = [m for m in inv_report.models if m.provider == ModelProviderKind.OLLAMA]
                chosen = local_candidates[0] if local_candidates else inv_report.models[0]
                await self._model_session_manager.activate_model(chosen.model_id)
                logger.info("Auto-activated default model runtime: %s", chosen.model_id)
        except Exception as ex:
            logger.warning("Initial model auto-discovery on startup: %s", ex)

    async def shutdown(self) -> None:
        """Gracefully shut down orchestrator, cancel in-flight tasks, and shut down capability registry."""
        logger.info("OrbitOrchestrator shutting down...")
        async with self._lock:
            # Cancel all running tasks
            for tid, src in list(self._active_cancellation_sources.items()):
                src.cancel("Orchestrator shutdown")

            # Await in-flight task completions
            tasks = list(self._active_execution_tasks.values())
            for t in tasks:
                t.cancel()

            # Trigger emergency stop if safety capability is available
            sft = self.safety
            if sft:
                try:
                    await sft.emergency_stop_all()
                except Exception as ex:
                    logger.warning("Error calling emergency_stop_all during shutdown: %s", ex)

            # Stop takeover monitoring if active
            tkv = self.takeover
            if tkv:
                try:
                    await tkv.stop_monitoring()
                except Exception as ex:
                    logger.warning("Error stopping takeover monitoring: %s", ex)

            # Shutdown all adapters in registry
            await self._registry.shutdown_all()

            # Shutdown model manager and model session manager
            await self._model_manager.shutdown()
            await self._model_session_manager.shutdown()

            self._system_sm.transition_to(SystemState.SHUTDOWN)

    def _on_takeover_state_changed(self, old_state: Any, new_state: Any, evidence: Optional[Any] = None) -> None:
        """Callback from TakeoverStateManager when physical takeover state transitions."""
        new_state_str = new_state.value if hasattr(new_state, "value") else str(new_state)
        if new_state_str in ("MONITORING", "STOPPED"):
            # If no desktop tasks are currently executing, auto-reconcile system state to IDLE
            if not self.is_task_executing and not self._active_desktop_tasks:
                if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                    if hasattr(self, "_loop") and self._loop and not self._loop.is_closed():
                        asyncio.run_coroutine_threadsafe(
                            self._auto_release_stale_takeover(
                                source="quiet_period_expired",
                                reason="Human inactivity quiet period elapsed",
                            ),
                            self._loop,
                        )
                    else:
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(self._auto_release_stale_takeover(
                                source="quiet_period_expired",
                                reason="Human inactivity quiet period elapsed",
                            ))
                        except Exception:
                            pass

    def _on_physical_takeover_detected(self, evidence: Optional[Any] = None) -> None:
        """Callback triggered when physical human input is detected."""
        if not self.is_human_takeover_enabled:
            logger.debug("Physical human input detected but Human Takeover is disabled (ORBIT_HUMAN_TAKEOVER_ENABLED=false); ignoring.")
            return

        if self._system_sm.current_state in {SystemState.SHUTDOWN, SystemState.HUMAN_TAKEOVER_ACTIVE}:
            return

        reason = "Physical human input detected"
        source = "human_input"
        if evidence and hasattr(evidence, "reason"):
            reason = str(evidence.reason)
        if evidence and hasattr(evidence, "source"):
            source = str(evidence.source.value if hasattr(evidence.source, "value") else evidence.source)
        asyncio.create_task(self.handle_human_takeover(reason=reason, source=source, evidence=evidence))

    async def handle_human_takeover(
        self,
        reason: str = "Human takeover triggered",
        source: str = "human_input",
        evidence: Optional[Any] = None,
    ) -> None:
        """Preempt active execution fail-closed on human takeover."""
        if not self.is_human_takeover_enabled:
            logger.debug("handle_human_takeover invoked but feature is disabled (ORBIT_HUMAN_TAKEOVER_ENABLED=false); bypassing.")
            return

        now_utc = datetime.now(timezone.utc).isoformat()
        logger.warning("HUMAN TAKEOVER TRIGGERED (%s): %s", source, reason)


        takeover_record = {
            "timestamp_utc": now_utc,
            "timestamp_ns": time.perf_counter_ns(),
            "source": source,
            "reason": reason,
            "is_active": True,
            "active_tasks": list(self._active_desktop_tasks),
            "evidence": evidence.model_dump() if hasattr(evidence, "model_dump") else str(evidence) if evidence else None,
        }
        self._last_takeover_info = takeover_record
        self._takeover_history.append(takeover_record)
        if len(self._takeover_history) > 50:
            self._takeover_history = self._takeover_history[-50:]

        # Sync with capability adapter
        tkv = self.takeover
        if tkv and hasattr(tkv, "state_manager"):
            if tkv.state_manager.can_transition_to(TakeoverState.TAKEOVER_ACTIVE):
                tkv.state_manager.transition_to(TakeoverState.TAKEOVER_ACTIVE, reason=reason, evidence=evidence)
            elif tkv.state_manager.current_state == TakeoverState.STOPPED:
                tkv.state_manager.transition_to(TakeoverState.STARTING, reason="Starting from takeover")
                tkv.state_manager.transition_to(TakeoverState.MONITORING, reason="Monitoring for takeover")
                tkv.state_manager.transition_to(TakeoverState.TAKEOVER_ACTIVE, reason=reason, evidence=evidence)
        elif tkv:
            if hasattr(tkv, "_takeover_active"):
                setattr(tkv, "_takeover_active", True)
            if hasattr(tkv, "_is_active"):
                setattr(tkv, "_is_active", True)

        async with self._lock:
            if self._system_sm.can_transition_to(SystemState.HUMAN_TAKEOVER_ACTIVE):
                self._system_sm.transition_to(SystemState.HUMAN_TAKEOVER_ACTIVE)

            # Cancel active desktop execution tokens
            for tid in list(self._active_desktop_tasks):
                src = self._active_cancellation_sources.get(tid)
                if src:
                    src.cancel(f"Preempted by human takeover: {reason}")
            for tid, src in list(self._active_cancellation_sources.items()):
                src.cancel(f"Preempted by human takeover: {reason}")

        # Sanitize hardware immediately via safety coordinator
        sft = self.safety
        if sft:
            try:
                await sft.emergency_stop_all()
            except Exception as ex:
                logger.error("Error invoking emergency safety stop: %s", ex)

        await self._emit_event(
            EventType.TAKEOVER_EVENT,
            session_id="system",
            payload=TakeoverEventPayload(
                is_active=True,
                source=source,
                reason=reason,
            ).model_dump(),
        )

    async def release_takeover(self) -> bool:
        """Release human takeover and return system to IDLE."""
        async with self._lock:
            if self._system_sm.current_state != SystemState.HUMAN_TAKEOVER_ACTIVE:
                return False
            tkv = self.takeover
            if tkv:
                await tkv.reset_takeover_state()
            self._system_sm.transition_to(SystemState.IDLE)
            if self._last_takeover_info:
                self._last_takeover_info["is_active"] = False
                self._last_takeover_info["released_at_utc"] = datetime.now(timezone.utc).isoformat()
                self._last_takeover_info["release_reason"] = "Operator released takeover lock"

        await self._emit_event(
            EventType.TAKEOVER_EVENT,
            session_id="system",
            payload=TakeoverEventPayload(
                is_active=False,
                source="operator_release",
                reason="Operator released takeover lock",
            ).model_dump(),
        )
        return True

    async def _auto_release_stale_takeover(self, source: str = "auto_recovery", reason: str = "Stale takeover auto-released") -> bool:
        """Safely release stale takeover when no task is executing."""
        async with self._lock:
            if self._system_sm.current_state != SystemState.HUMAN_TAKEOVER_ACTIVE:
                return False
            tkv = self.takeover
            if tkv:
                await tkv.reset_takeover_state()
            self._system_sm.transition_to(SystemState.IDLE)
            if self._last_takeover_info:
                self._last_takeover_info["is_active"] = False
                self._last_takeover_info["released_at_utc"] = datetime.now(timezone.utc).isoformat()
                self._last_takeover_info["release_reason"] = reason

        logger.info("Auto-released stale HUMAN_TAKEOVER_ACTIVE state to IDLE (%s: %s)", source, reason)
        await self._emit_event(
            EventType.TAKEOVER_EVENT,
            session_id="system",
            payload=TakeoverEventPayload(
                is_active=False,
                source=source,
                reason=reason,
            ).model_dump(),
        )
        return True

    async def recover_locked_state(self, recovery_token: str) -> bool:
        """Clear hard fail-closed UNRESOLVED_LOCKED state."""
        async with self._lock:
            self._system_sm.transition_to(SystemState.IDLE, recovery_token=recovery_token)
            sft = self.safety
            if sft:
                await sft.emergency_stop_all()

        await self._emit_event(
            EventType.RECOVERY_EVENT,
            session_id="system",
            payload={"status": "RECOVERED", "recovered_to": "IDLE"},
        )
        return True



    async def execute_agent_task(
        self,
        prompt: str,
        session_id: str = "default_session",
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        routing_policy: Optional[RoutingPolicy] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> AgentExecutionResult:
        """Execute a user prompt directly through the unified AI-native Agent Execution Loop."""
        return await self._agent_loop.run(
            prompt=prompt,
            session_id=session_id,
            task_id=task_id,
            context=context,
            routing_policy=routing_policy,
            cancel_token=cancel_token,
        )

    async def execute_cognitive_task(
        self,
        prompt: str,
        session_id: str = "default_session",
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> CognitiveExecutionResult:
        """Execute a user prompt directly through the closed-loop Cognitive Intent & Decision Engine."""
        return await self._agent_loop.run(
            prompt=prompt,
            session_id=session_id,
            task_id=task_id,
            context=context,
            cancel_token=cancel_token,
        )

    async def execute_task(
        self,
        goal: Optional[str] = None,
        prompt: Optional[str] = None,
        session_id: str = "default_session",
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        policy: Optional[ExecutionPolicy] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> TaskExecutionResult:
        """Execute a natural-language task goal end-to-end with independent goal verification (ASTRA-6 Authoritative Loop)."""
        target_goal = goal or prompt or ""
        # Default authoritative production execution path: ASTRA AgentExecutionLoop
        agent_res = await self._agent_loop.run(
            prompt=target_goal,
            session_id=session_id,
            task_id=task_id,
            context=context,
            cancel_token=cancel_token,
        )
        verification_result = GoalVerificationResult(
            status=agent_res.final_status,
            is_completed=agent_res.is_success,
            failure_reason=agent_res.failure_reason,
            failure_code=agent_res.failure_code,
        )
        return TaskExecutionResult(
            task_id=agent_res.task_id,
            session_id=session_id,
            goal=target_goal,
            goal_verification_result=verification_result,
            completion_status=agent_res.final_status,
            is_success=agent_res.is_success,
            failure_reason=agent_res.failure_reason,
            failure_code=agent_res.failure_code,
            elapsed_duration_ms=agent_res.elapsed_duration_ms,
        )

    async def submit_task(
        self,
        session_id: str,
        prompt: str,
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Submit a new task for validation and background execution."""
        task = await self._task_manager.create_task(
            session_id=session_id,
            prompt=prompt,
            task_id=task_id,
            metadata=context or {},
        )

        active_ctx = self._model_session_manager.get_active_context() if hasattr(self._model_session_manager, "get_active_context") else None
        active_model_id = active_ctx.model_id if active_ctx else None
        model_prov = active_ctx.provider.value if active_ctx and hasattr(active_ctx.provider, "value") else (str(active_ctx.provider) if active_ctx else None)

        history_rec = ExecutionRecord(
            task_id=task.task_id,
            session_id=session_id,
            goal=prompt,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            active_model=active_model_id,
            model_provider=model_prov,
        )
        await self._history_store.save_record(history_rec)

        await self._emit_event(
            EventType.TASK_STATE_CHANGED,
            session_id=session_id,
            correlation_id=task.task_id,
            payload=TaskStatePayload(
                task_id=task.task_id,
                session_id=session_id,
                status=task.status,
                prompt=task.prompt,
            ).model_dump(),
        )
        await self._emit_event(
            EventType.EXECUTION_RECORD_UPDATED,
            session_id=session_id,
            correlation_id=task.task_id,
            payload={"record": history_rec.model_dump(mode="json")},
        )

        # Launch execution in background task
        is_conversational = bool(context and context.get("conversational"))
        if not is_conversational:
            self._active_desktop_tasks.add(task.task_id)

        if not is_conversational and self._system_sm.current_state in (
            SystemState.HUMAN_TAKEOVER_ACTIVE,
            SystemState.UNRESOLVED_LOCKED,
        ):
            if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                if not self.is_human_takeover_enabled:
                    logger.info(
                        "Auto-recovering stale HUMAN_TAKEOVER_ACTIVE state to IDLE (takeover disabled) for task %s",
                        task.task_id,
                    )
                    await self._auto_release_stale_takeover(
                        source="submit_task",
                        reason=f"Human takeover disabled; stale state auto-released on task submission ({task.task_id})",
                    )
                else:
                    is_active = await self.is_human_takeover_active()
                    if not is_active:
                        logger.info(
                            "Auto-recovering stale HUMAN_TAKEOVER_ACTIVE state to IDLE upon submission of task %s",
                            task.task_id,
                        )
                        await self._auto_release_stale_takeover(
                            source="submit_task",
                            reason=f"Auto-recovered stale takeover on task submission ({task.task_id})",
                        )
                    else:
                        self._active_desktop_tasks.discard(task.task_id)
                        diag = {}
                        tkv = self.takeover
                        if tkv and hasattr(tkv, "get_diagnostics"):
                            diag = tkv.get_diagnostics()
                        last_src = self._last_takeover_info.get("source", "unknown") if self._last_takeover_info else "unknown"
                        last_ts = self._last_takeover_info.get("timestamp_utc", "unknown") if self._last_takeover_info else "unknown"
                        prev_tasks = self._last_takeover_info.get("active_tasks", []) if self._last_takeover_info else []

                        err_msg = (
                            f"Cannot execute task while in state HUMAN_TAKEOVER_ACTIVE. "
                            f"Active human takeover detected (source: {last_src}, triggered_at: {last_ts}, "
                            f"previous_tasks: {prev_tasks}, diagnostics: {diag})"
                        )
                        err_detail = ErrorDetail(
                            code="HUMAN_TAKEOVER_ACTIVE",
                            message=err_msg,
                            recoverable=False,
                            details={
                                "system_state": self._system_sm.current_state.value,
                                "task_id": task.task_id,
                                "session_id": session_id,
                                "takeover_source": last_src,
                                "takeover_timestamp": last_ts,
                                "is_stale": False,
                                "previous_tasks": prev_tasks,
                                "diagnostics": diag,
                                "takeover_history": self._takeover_history[-5:],
                            },
                        )
                        history_rec.status = ExecutionStatus.FAILED
                        history_rec.failure_code = "HUMAN_TAKEOVER_ACTIVE"
                        history_rec.failure_reason = err_msg
                        history_rec.completed_at = datetime.now(timezone.utc)
                        history_rec.duration_ms = (history_rec.completed_at - history_rec.started_at).total_seconds() * 1000.0
                        await self._history_store.save_record(history_rec)
                        await self._emit_event(
                            EventType.EXECUTION_RECORD_UPDATED,
                            session_id=session_id,
                            correlation_id=task.task_id,
                            payload={"record": history_rec.model_dump(mode="json")},
                        )
                        await self._task_manager.update_status(task.task_id, TaskStatus.FAILED, error=err_detail)
                        await self._emit_task_event(task.task_id, TaskStatus.FAILED, error=err_detail)
                        return task

            elif self._system_sm.current_state == SystemState.UNRESOLVED_LOCKED:
                self._active_desktop_tasks.discard(task.task_id)
                err_detail = ErrorDetail(
                    code="UNRESOLVED_LOCKED",
                    message="Cannot execute task: System is in UNRESOLVED_LOCKED state. Manual operator reset required.",
                    recoverable=False,
                )
                history_rec.status = ExecutionStatus.FAILED
                history_rec.failure_code = "UNRESOLVED_LOCKED"
                history_rec.failure_reason = err_detail.message
                history_rec.completed_at = datetime.now(timezone.utc)
                history_rec.duration_ms = (history_rec.completed_at - history_rec.started_at).total_seconds() * 1000.0
                await self._history_store.save_record(history_rec)
                await self._emit_event(
                    EventType.EXECUTION_RECORD_UPDATED,
                    session_id=session_id,
                    correlation_id=task.task_id,
                    payload={"record": history_rec.model_dump(mode="json")},
                )
                await self._task_manager.update_status(task.task_id, TaskStatus.FAILED, error=err_detail)
                await self._emit_task_event(task.task_id, TaskStatus.FAILED, error=err_detail)
                return task

        cancel_source = CancellationSource()
        self._active_cancellation_sources[task.task_id] = cancel_source

        exec_task = asyncio.create_task(
            self._execute_task_lifecycle(task.task_id, cancel_source.token)
        )
        self._active_execution_tasks[task.task_id] = exec_task

        return task

    async def cancel_task(self, task_id: str, reason: str = "Operator requested cancellation") -> bool:
        """Cancel an in-flight or queued task."""
        cancel_source = self._active_cancellation_sources.get(task_id)
        if cancel_source:
            cancel_source.cancel(reason)

        task = await self._task_manager.get_task(task_id)
        if task and task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            updated = await self._task_manager.update_status(
                task_id,
                TaskStatus.CANCELLED,
                error=ErrorDetail(code="TASK_CANCELLED", message=reason, recoverable=False),
            )
            rec = await self._history_store.get_record_by_task_id(task_id)
            if rec:
                rec.status = ExecutionStatus.CANCELLED
                rec.cancellation_reason = reason
                rec.completed_at = datetime.now(timezone.utc)
                rec.duration_ms = (rec.completed_at - rec.started_at).total_seconds() * 1000.0
                await self._history_store.save_record(rec)
                await self._emit_event(
                    EventType.EXECUTION_RECORD_UPDATED,
                    session_id=updated.session_id,
                    correlation_id=task_id,
                    payload={"record": rec.model_dump(mode="json")},
                )

            await self._emit_event(
                EventType.TASK_STATE_CHANGED,
                session_id=updated.session_id,
                correlation_id=task_id,
                payload=TaskStatePayload(
                    task_id=task_id,
                    session_id=updated.session_id,
                    status=updated.status,
                    prompt=updated.prompt,
                    error=updated.error,
                ).model_dump(),
            )
            return True
        return False

    async def pause_task(self, task_id: str, reason: str = "Operator paused task") -> bool:
        """Pause execution of an in-flight task."""
        task = await self._task_manager.get_task(task_id)
        if task and task.status in {TaskStatus.RUNNING, TaskStatus.VALIDATING, TaskStatus.READY}:
            updated = await self._task_manager.update_status(task_id, TaskStatus.PAUSED)
            await self._emit_task_event(task_id, TaskStatus.PAUSED)
            return True
        return False

    async def resume_task(self, task_id: str) -> bool:
        """Resume execution of a paused task."""
        task = await self._task_manager.get_task(task_id)
        if task and task.status == TaskStatus.PAUSED:
            updated = await self._task_manager.update_status(task_id, TaskStatus.RUNNING)
            await self._emit_task_event(task_id, TaskStatus.RUNNING)
            return True
        return False

    async def authorize_action(self, task_id: str, action_id: str, approved: bool, reason: Optional[str] = None) -> bool:
        """Handle human authorization response for a gated action."""
        await self._emit_event(
            EventType.ACTION_AUTHORIZATION_RESOLVED,
            session_id="system",
            correlation_id=task_id,
            payload={"task_id": task_id, "action_id": action_id, "approved": approved, "reason": reason},
        )
        return True

    async def _execute_task_lifecycle(self, task_id: str, cancel_token: CancellationToken) -> None:
        """Core execution pipeline executing task steps safely."""
        task = await self._task_manager.get_task(task_id)
        if not task:
            return

        session_id = task.session_id

        try:
            if cancel_token.is_cancelled:
                await self._handle_cancellation(task_id, cancel_token.reason)
                return

            # 1. Validation Phase
            await self._task_manager.update_status(task_id, TaskStatus.VALIDATING)
            await self._emit_task_event(task_id, TaskStatus.VALIDATING)

            if cancel_token.is_cancelled:
                await self._handle_cancellation(task_id, cancel_token.reason)
                return

            # Conversational Chatbot Mode: Execute pure LLM inference directly without OS desktop side-effects or takeover checks
            is_conversational = bool(task.metadata and task.metadata.get("conversational"))
            if is_conversational:
                await self._task_manager.update_status(task_id, TaskStatus.READY)
                await self._emit_task_event(task_id, TaskStatus.READY)

                await self._task_manager.update_status(task_id, TaskStatus.RUNNING)
                await self._emit_task_event(task_id, TaskStatus.RUNNING)

                active_ctx = self._model_session_manager.get_active_context() if hasattr(self._model_session_manager, "get_active_context") else None
                if active_ctx:
                    try:
                        resp = await self._model_session_manager.generate(
                            ModelGenerateRequest(
                                prompt=task.prompt,
                                system_prompt="You are ORBIT, an executive AI desktop co-pilot. Respond directly, politely, and helpfully to the user.",
                            )
                        )
                        rec = await self._history_store.get_record_by_task_id(task_id)
                        if rec:
                            rec.status = ExecutionStatus.COMPLETED
                            rec.completed_at = datetime.now(timezone.utc)
                            await self._history_store.save_record(rec)

                        await self._task_manager.update_status(task_id, TaskStatus.COMPLETED)
                        await self._emit_task_event(task_id, TaskStatus.COMPLETED)
                        await self._emit_event(
                            EventType.MODEL_GENERATE_RESPONSE,
                            session_id=session_id,
                            correlation_id=task_id,
                            payload={"text": resp.content, "task_id": task_id},
                        )
                        return
                    except Exception as gen_err:
                        logger.warning("Conversational model generation exception: %s", gen_err)
                        err_detail = ErrorDetail(code="MODEL_ERROR", message=str(gen_err), recoverable=True)
                        await self._task_manager.update_status(task_id, TaskStatus.FAILED, error=err_detail)
                        await self._emit_task_event(task_id, TaskStatus.FAILED, error=err_detail)
                        return
                else:
                    err_detail = ErrorDetail(code="NO_ACTIVE_MODEL", message="No AI model is currently active for chat. Please activate a model in Settings.", recoverable=True)
                    await self._task_manager.update_status(task_id, TaskStatus.FAILED, error=err_detail)
                    await self._emit_task_event(task_id, TaskStatus.FAILED, error=err_detail)
                    return

            # Check system state and ensure ready for execution of autonomous desktop actions
            async with self._lock:
                if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                    if not self.is_human_takeover_enabled:
                        logger.info("Auto-recovering stale HUMAN_TAKEOVER_ACTIVE state to IDLE (takeover disabled) for task %s", task_id)
                        tkv = self.takeover
                        if tkv and hasattr(tkv, "reset_takeover_state"):
                            await tkv.reset_takeover_state()
                        self._system_sm.transition_to(SystemState.IDLE)
                    elif await self.is_human_takeover_active():
                        raise RuntimeError(f"Cannot execute task while in state {self._system_sm.current_state.value}")
                    else:
                        logger.info("Auto-recovering stale HUMAN_TAKEOVER_ACTIVE state to IDLE for task %s", task_id)
                        tkv = self.takeover
                        if tkv:
                            await tkv.reset_takeover_state()
                        self._system_sm.transition_to(SystemState.IDLE)
                elif self._system_sm.current_state == SystemState.UNRESOLVED_LOCKED:
                    raise RuntimeError(f"Cannot execute task while in state {self._system_sm.current_state.value}")

                if self._system_sm.current_state == SystemState.IDLE:
                    self._system_sm.transition_to(SystemState.BUSY)


            # 2. Ready Phase
            await self._task_manager.update_status(task_id, TaskStatus.READY)
            await self._emit_task_event(task_id, TaskStatus.READY)

            # 3. Running Phase
            await self._task_manager.update_status(task_id, TaskStatus.RUNNING)
            await self._emit_task_event(task_id, TaskStatus.RUNNING)

            # Step 1: Capture Observation
            if not self._registry.is_ready(CapabilityType.OBSERVATION):
                adapter = self._registry.get_optional(CapabilityType.OBSERVATION)
                state = adapter.lifecycle_state if adapter else CapabilityLifecycleState.STOPPED
                raise CapabilityUnavailableError(
                    CapabilityType.OBSERVATION,
                    state,
                    "Observation capability is required to observe screen but is not ready",
                )

            obs = self._registry.resolve_typed(CapabilityType.OBSERVATION, ObservationCapability)
            frame = await obs.capture_screen(display_index=0)
            await self._emit_event(
                EventType.OBSERVATION_FRAME,
                session_id=session_id,
                correlation_id=task_id,
                payload={
                    "frame_id": frame.frame_id,
                    "resolution": frame.resolution.model_dump(),
                    "format": frame.format,
                },
            )

            if cancel_token.is_cancelled:
                await self._handle_cancellation(task_id, cancel_token.reason)
                return

            # Conversational Mode: If conversational intent or Chatbot mode, query active LLM directly
            if task.metadata.get("conversational"):
                active_ctx = self._model_session_manager.get_active_context() if hasattr(self._model_session_manager, "get_active_context") else None
                if active_ctx:
                    try:
                        resp = await self._model_session_manager.generate(
                            ModelGenerateRequest(
                                prompt=task.prompt,
                                system_prompt="You are ORBIT, an executive AI desktop co-pilot. Respond directly, politely, and helpfully to the user.",
                            )
                        )
                        rec = await self._history_store.get_record_by_task_id(task_id)
                        if rec:
                            rec.status = ExecutionStatus.COMPLETED
                            rec.completed_at = datetime.now(timezone.utc)
                            await self._history_store.save_record(rec)

                        await self._task_manager.update_status(task_id, TaskStatus.COMPLETED)
                        await self._emit_task_event(task_id, TaskStatus.COMPLETED)
                        await self._emit_event(
                            EventType.MODEL_GENERATE_RESPONSE,
                            session_id=session_id,
                            correlation_id=task_id,
                            payload={"text": resp.content, "task_id": task_id},
                        )
                        return
                    except Exception as gen_err:
                        logger.warning("Conversational model turn exception: %s", gen_err)

            # Production Path: Execute Natural Language Autonomous Task end-to-end via unified AgentExecutionLoop
            logger.info("Executing autonomous task %s via AgentExecutionLoop: '%s'", task_id, task.prompt)
            agent_res: AgentExecutionResult = await self._agent_loop.run(
                prompt=task.prompt,
                session_id=session_id,
                task_id=task_id,
                context=task.metadata,
                cancel_token=cancel_token,
            )

            task.metadata["agent_execution_result"] = agent_res.model_dump()
            task.metadata["task_objective"] = agent_res.objective.model_dump()

            # Emit Plan if formulated from step history
            if agent_res.step_history:
                try:
                    ui_plan = ExecutionPlan(
                        plan_id=agent_res.objective.objective_id,
                        task_id=task_id,
                        description=agent_res.objective.user_goal or task.prompt,
                        steps=[
                            Step(
                                step_id=f"step_{s.step_index}",
                                step_index=s.step_index,
                                description=s.decision.decision_summary or f"Step {s.step_index + 1}",
                            )
                            for s in agent_res.step_history
                        ],
                    )
                    await self._task_manager.set_plan(task_id, ui_plan)
                    await self._emit_event(
                        EventType.PLAN_UPDATED,
                        session_id=session_id,
                        correlation_id=task_id,
                        payload=PlanUpdatedPayload(task_id=task_id, plan=ui_plan).model_dump(),
                    )
                except Exception as plan_err:
                    logger.debug("Plan conversion notice: %s", plan_err)

            # Update history store record
            rec = await self._history_store.get_record_by_task_id(task_id)
            is_successful = agent_res.is_success
            comp_status = agent_res.final_status
            if rec:
                if comp_status and comp_status.value in ExecutionStatus.__members__:
                    rec.status = ExecutionStatus[comp_status.value]
                else:
                    rec.status = ExecutionStatus.COMPLETED if is_successful else ExecutionStatus.FAILED
                rec.completed_at = datetime.now(timezone.utc)
                rec.duration_ms = agent_res.elapsed_duration_ms
                rec.failure_reason = agent_res.failure_reason
                rec.failure_code = agent_res.failure_code
                rec.total_steps = len(agent_res.step_history)
                rec.steps_completed = len(agent_res.step_history) if is_successful else max(0, len(agent_res.step_history) - 1)
                await self._history_store.save_record(rec)
                await self._emit_event(
                    EventType.EXECUTION_RECORD_UPDATED,
                    session_id=session_id,
                    correlation_id=task_id,
                    payload={"record": rec.model_dump(mode="json")},
                )

            if is_successful:
                await self._task_manager.update_status(task_id, TaskStatus.VERIFYING, metadata=task.metadata)
                await self._emit_task_event(task_id, TaskStatus.VERIFYING)
                await self._task_manager.update_status(task_id, TaskStatus.COMPLETED, metadata=task.metadata)
                await self._emit_task_event(task_id, TaskStatus.COMPLETED)
            else:
                err_code = agent_res.failure_code or "TASK_EXECUTION_FAILED"
                err_msg = agent_res.failure_reason or "Task goal could not be verified or completed"
                logger.warning("Task %s failed physical execution: [%s] %s", task_id, err_code, err_msg)
                err_detail = ErrorDetail(
                    code=err_code,
                    message=err_msg,
                    recoverable=False,
                )
                terminal_status = (
                    TaskStatus.CANCELLED
                    if (comp_status and comp_status.value == "CANCELLED")
                    else TaskStatus.FAILED
                )
                await self._task_manager.update_status(task_id, terminal_status, error=err_detail, metadata=task.metadata)
                await self._emit_task_event(task_id, terminal_status, error=err_detail)

        except Exception as ex:
            logger.exception("Task execution failed for task %s: %s", task_id, ex)
            error_detail = ErrorDetail(
                code="EXECUTION_ERROR" if not isinstance(ex, CapabilityUnavailableError) else "CAPABILITY_UNAVAILABLE",
                message=str(ex),
                recoverable=True,
            )
            try:
                await self._task_manager.update_status(task_id, TaskStatus.FAILED, error=error_detail)
                await self._emit_task_event(task_id, TaskStatus.FAILED, error=error_detail)
            except Exception:
                pass
        finally:
            async with self._lock:
                self._active_desktop_tasks.discard(task_id)
                self._active_cancellation_sources.pop(task_id, None)
                self._active_execution_tasks.pop(task_id, None)

                if not self._active_desktop_tasks:
                    is_active = False
                    tkv = self.takeover
                    if tkv and hasattr(tkv, "is_takeover_active"):
                        res = tkv.is_takeover_active()
                        import inspect
                        is_active = await res if inspect.isawaitable(res) else bool(res)

                    if not is_active:
                        if self._system_sm.current_state in (
                            SystemState.BUSY,
                            SystemState.PAUSED,
                        ):
                            logger.info(
                                "Terminal task %s cleanup: transitioning %s -> IDLE",
                                task_id,
                                self._system_sm.current_state.value,
                            )
                            self._system_sm.transition_to(SystemState.IDLE)

    async def _execute_action(
        self,
        session_id: str,
        action: Action,
        cancel_token: CancellationToken,
    ) -> None:
        """Execute an individual action through its stage transitions."""
        action_sm = ActionStateMachine(ActionStage.PENDING)

        # Transition: PENDING -> DISPATCHED
        action.stage = action_sm.transition_to(ActionStage.DISPATCHED)
        action.dispatched_at = datetime.now(timezone.utc)
        await self._emit_action_event(session_id, action)

        if cancel_token.is_cancelled:
            action.stage = action_sm.transition_to(ActionStage.CANCELLED)
            await self._emit_action_event(session_id, action)
            return

        # Determine required capability
        required_cap = self._resolve_required_capability(action.action_type)
        if required_cap:
            if not self._registry.is_ready(required_cap):
                adapter = self._registry.get_optional(required_cap)
                state = adapter.lifecycle_state if adapter else CapabilityLifecycleState.STOPPED
                err = CapabilityUnavailableError(
                    required_cap,
                    state,
                    f"Action '{action.action_type}' requires capability '{required_cap.value}' which is not ready",
                )
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="CAPABILITY_UNAVAILABLE", message=str(err), recoverable=False)
                await self._emit_action_event(session_id, action)
                raise err

        # Transition: DISPATCHED -> EXECUTING
        action.stage = action_sm.transition_to(ActionStage.EXECUTING)
        await self._emit_action_event(session_id, action)

        # Determine if action requires full observation-based verification
        expected_outcome = action.parameters.get("expected_outcome")
        if expected_outcome is not None and isinstance(expected_outcome, dict):
            try:
                expected_outcome = ExpectedOutcome.model_validate(expected_outcome)
            except Exception:
                pass

        is_synthetic = action.parameters.get("is_synthetic_development", False)
        explicit_verify = action.parameters.get("verify", False)
        has_snapshot_param = "pre_snapshot" in action.parameters or "post_snapshot" in action.parameters

        should_verify = (
            expected_outcome is not None
            or explicit_verify
            or has_snapshot_param
            or (action.action_type in {"pointer_click", "type_text", "shortcut"} and not is_synthetic and not action.parameters.get("is_test", False))
        )

        # Acquire pre-action observation snapshot if observation capability is ready
        pre_snapshot = None
        if should_verify:
            pre_snapshot = action.parameters.get("pre_snapshot")
            if pre_snapshot is None and self.observation and self._registry.is_ready(CapabilityType.OBSERVATION):
                if hasattr(self.observation, "capture_snapshot"):
                    try:
                        pre_snapshot = await self.observation.capture_snapshot(
                            target_hwnd=action.parameters.get("target_hwnd")
                        )
                    except Exception as ex:
                        logger.warning("Failed to capture pre-action observation snapshot: %s", ex)
                        pre_snapshot = None
            elif isinstance(pre_snapshot, dict):
                try:
                    pre_snapshot = ObservationSnapshot.model_validate(pre_snapshot)
                except Exception:
                    pre_snapshot = None

        # Dispatch to capabilities
        if action.action_type in {"pointer_click", "pointer_move"}:
            ptr = self._registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
            x = action.parameters.get("x")
            y = action.parameters.get("y")
            if x is None or y is None:
                err_msg = f"Action '{action.action_type}' rejected: missing required 'x' and 'y' coordinates in parameters"
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="INVALID_COORDINATES", message=err_msg, recoverable=False)
                await self._emit_action_event(session_id, action)
                raise ValueError(err_msg)

            # Pre-dispatch human takeover check
            if self.is_human_takeover_enabled and self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                err_msg = "Pointer action blocked: Human takeover is currently active"
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
                await self._emit_action_event(session_id, action)
                raise RuntimeError(err_msg)

            # Pre-dispatch cancellation check
            if cancel_token.is_cancelled:
                action.stage = action_sm.transition_to(ActionStage.CANCELLED)
                await self._emit_action_event(session_id, action)
                return

            # Pre-dispatch Workspace Validation Gate
            wsp = self.workspace
            expected_gen = action.parameters.get("desktop_generation_id")
            if expected_gen is None:
                expected_gen = action.parameters.get("expected_generation")

            if wsp is not None and hasattr(wsp, "validate_coordinate"):
                val_res = wsp.validate_coordinate(int(x), int(y), expected_generation=expected_gen)
                if not val_res.is_valid:
                    status_code = getattr(val_res.status, "value", str(val_res.status))
                    err_msg = (
                        f"Workspace coordinate validation blocked dispatch to ({x}, {y}): "
                        f"[{status_code}] {val_res.error_message}"
                    )
                    logger.error(err_msg)
                    action.stage = action_sm.transition_to(ActionStage.FAILED)
                    action.error = ErrorDetail(
                        code=status_code,
                        message=err_msg,
                        recoverable=False,
                        details={
                            "x": x,
                            "y": y,
                            "status": status_code,
                            "active_generation": getattr(val_res, "active_generation_id", None),
                            "tested_generation": expected_gen,
                        },
                    )
                    await self._emit_action_event(session_id, action)
                    raise RuntimeError(err_msg)

            # Final pre-dispatch cancellation check
            if cancel_token.is_cancelled:
                action.stage = action_sm.transition_to(ActionStage.CANCELLED)
                await self._emit_action_event(session_id, action)
                return

            if action.action_type == "pointer_click":
                btn = action.parameters.get("button", "left")
                count = action.parameters.get("count", 1)
                await ptr.click(int(x), int(y), button=btn, count=count)
            elif action.action_type == "pointer_move":
                await ptr.move_to(int(x), int(y))

        elif action.action_type == "type_text":
            if self.is_human_takeover_enabled and self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                err_msg = "Keyboard action blocked: Human takeover is currently active"
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
                await self._emit_action_event(session_id, action)
                raise RuntimeError(err_msg)
            if cancel_token.is_cancelled:
                action.stage = action_sm.transition_to(ActionStage.CANCELLED)
                await self._emit_action_event(session_id, action)
                return
            kbd = self._registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
            text = action.parameters.get("text", "")
            target_hwnd = action.parameters.get("target_hwnd")
            await kbd.type_text(text, target_hwnd=target_hwnd)
        elif action.action_type == "shortcut":
            if self.is_human_takeover_enabled and self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                err_msg = "Keyboard action blocked: Human takeover is currently active"
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
                await self._emit_action_event(session_id, action)
                raise RuntimeError(err_msg)
            if cancel_token.is_cancelled:
                action.stage = action_sm.transition_to(ActionStage.CANCELLED)
                await self._emit_action_event(session_id, action)
                return
            kbd = self._registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
            comb = action.parameters.get("combination", "ctrl+s")
            target_hwnd = action.parameters.get("target_hwnd")
            await kbd.press_shortcut(comb, target_hwnd=target_hwnd)
        elif action.action_type == "observe":
            if self.is_human_takeover_enabled and self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                err_msg = "Observation blocked: Human takeover is currently active"
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
                await self._emit_action_event(session_id, action)
                raise RuntimeError(err_msg)
            if cancel_token.is_cancelled:
                action.stage = action_sm.transition_to(ActionStage.CANCELLED)
                await self._emit_action_event(session_id, action)
                return
            obs = self._registry.resolve_typed(CapabilityType.OBSERVATION, ObservationCapability)
            await obs.capture_screen()
        elif action.action_type in {"workspace_dock", "workspace_reserve"}:
            if self.is_human_takeover_enabled and self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                err_msg = "Workspace action blocked: Human takeover is currently active"
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
                await self._emit_action_event(session_id, action)
                raise RuntimeError(err_msg)
            if cancel_token.is_cancelled:
                action.stage = action_sm.transition_to(ActionStage.CANCELLED)
                await self._emit_action_event(session_id, action)
                return
            wsp = self._registry.resolve_typed(CapabilityType.WORKSPACE, WorkspaceCapability)
            edge = action.parameters.get("edge", "right")
            size = action.parameters.get("size", 480)
            await wsp.register_appbar(edge=edge, size=size)
        elif action.action_type == "workspace_undock":
            if self.is_human_takeover_enabled and self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
                err_msg = "Workspace action blocked: Human takeover is currently active"
                action.stage = action_sm.transition_to(ActionStage.FAILED)
                action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
                await self._emit_action_event(session_id, action)
                raise RuntimeError(err_msg)

            if cancel_token.is_cancelled:
                action.stage = action_sm.transition_to(ActionStage.CANCELLED)
                await self._emit_action_event(session_id, action)
                return
            wsp = self._registry.resolve_typed(CapabilityType.WORKSPACE, WorkspaceCapability)
            await wsp.unregister_appbar()

        if cancel_token.is_cancelled:
            action.stage = action_sm.transition_to(ActionStage.CANCELLED)
            await self._emit_action_event(session_id, action)
            return

        if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
            err_msg = "Pointer action blocked: Human takeover is currently active"
            action.stage = action_sm.transition_to(ActionStage.FAILED)
            action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
            await self._emit_action_event(session_id, action)
            raise RuntimeError(err_msg)

        # Transition: EXECUTING -> VERIFYING
        action.stage = action_sm.transition_to(ActionStage.VERIFYING)
        await self._emit_action_event(session_id, action)

        if not should_verify:
            action.verification = VerificationResult(
                status=VerificationStatus.PASSED,
                confidence=1.0,
                details={"verification_mode": "mock_immediate"},
            )
            # Transition: VERIFYING -> COMPLETED
            action.stage = action_sm.transition_to(ActionStage.COMPLETED)
            action.completed_at = datetime.now(timezone.utc)
            await self._emit_action_event(session_id, action)
            return

        # Acquire post-action observation snapshot
        post_snapshot = action.parameters.get("post_snapshot")
        if post_snapshot is None and self.observation and self._registry.is_ready(CapabilityType.OBSERVATION):
            if hasattr(self.observation, "capture_snapshot"):
                try:
                    post_snapshot = await self.observation.capture_snapshot(
                        target_hwnd=action.parameters.get("target_hwnd")
                    )
                except Exception as ex:
                    logger.warning("Failed to capture post-action observation snapshot: %s", ex)
                    post_snapshot = None
        elif isinstance(post_snapshot, dict):
            try:
                post_snapshot = ObservationSnapshot.model_validate(post_snapshot)
            except Exception:
                post_snapshot = None

        if expected_outcome is not None and isinstance(expected_outcome, dict):
            try:
                expected_outcome = ExpectedOutcome.model_validate(expected_outcome)
            except Exception:
                expected_outcome = None
        elif not isinstance(expected_outcome, ExpectedOutcome):
            expected_outcome = None

        verif_res: ActionVerificationResult = self._action_verifier.verify(
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            expected_outcome=expected_outcome,
        )

        status_map = {
            VerificationOutcome.VERIFIED_SUCCESS: VerificationStatus.PASSED,
            VerificationOutcome.VERIFIED_FAILURE: VerificationStatus.FAILED,
            VerificationOutcome.INCONCLUSIVE: VerificationStatus.INCONCLUSIVE,
            VerificationOutcome.STALE_EVIDENCE: VerificationStatus.FAILED,
            VerificationOutcome.UNSUPPORTED: VerificationStatus.FAILED,
        }
        verif_status = status_map.get(verif_res.outcome, VerificationStatus.FAILED)

        action.verification = VerificationResult(
            status=verif_status,
            confidence=verif_res.confidence,
            details={
                "outcome": verif_res.outcome.value,
                "strategy_used": verif_res.strategy_used.value,
                "confidence": verif_res.confidence,
                "pre_generation_id": verif_res.pre_generation_id,
                "post_generation_id": verif_res.post_generation_id,
                "detected_changes": verif_res.detected_changes,
                "failure_reason": verif_res.failure_reason,
            },
        )

        if cancel_token.is_cancelled:
            action.stage = action_sm.transition_to(ActionStage.CANCELLED)
            await self._emit_action_event(session_id, action)
            return

        if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
            err_msg = "Human takeover active during action verification"
            action.stage = action_sm.transition_to(ActionStage.FAILED)
            action.error = ErrorDetail(code="HUMAN_TAKEOVER_ACTIVE", message=err_msg, recoverable=False)
            await self._emit_action_event(session_id, action)
            raise RuntimeError(err_msg)

        if verif_res.outcome in {
            VerificationOutcome.VERIFIED_FAILURE,
            VerificationOutcome.STALE_EVIDENCE,
            VerificationOutcome.UNSUPPORTED,
        }:
            err_msg = f"Action verification failed ({verif_res.outcome.value}): {verif_res.failure_reason}"
            logger.error(err_msg)
            action.stage = action_sm.transition_to(ActionStage.FAILED)
            action.error = ErrorDetail(
                code=verif_res.outcome.value,
                message=err_msg,
                recoverable=False,
                details=action.verification.details or {},
            )
            await self._emit_action_event(session_id, action)
            raise RuntimeError(err_msg)

        # Transition: VERIFYING -> COMPLETED
        action.stage = action_sm.transition_to(ActionStage.COMPLETED)
        action.completed_at = datetime.now(timezone.utc)
        await self._emit_action_event(session_id, action)

    def _resolve_required_capability(self, action_type: str) -> Optional[CapabilityType]:
        """Map action type to required capability."""
        if action_type in {"pointer_click", "pointer_move", "pointer_down", "pointer_up"}:
            return CapabilityType.POINTER
        if action_type in {"type_text", "shortcut", "key_press", "key_release"}:
            return CapabilityType.KEYBOARD
        if action_type in {"observe", "capture_screen"}:
            return CapabilityType.OBSERVATION
        if action_type in {"workspace_dock", "workspace_undock", "workspace_reserve"}:
            return CapabilityType.WORKSPACE
        return None

    def _build_target_resolved_plan(
        self,
        task_id: str,
        prompt: str,
        target: ResolvedTarget,
        expected_outcome: Optional[ExpectedOutcome] = None,
    ) -> ExecutionPlan:
        """Create an execution plan bound to a verified resolved target and desktop generation."""
        safe_pt = target.safe_point
        click_params: Dict[str, Any] = {
            "x": safe_pt.x,
            "y": safe_pt.y,
            "button": "left",
            "desktop_generation_id": safe_pt.desktop_generation_id,
            "target_id": target.target_id,
            "source": target.evidence.source,
        }
        if expected_outcome is not None:
            click_params["expected_outcome"] = expected_outcome

        step_1 = Step(
            step_id=f"step_1_{uuid4().hex[:6]}",
            step_index=0,
            description=f"Position cursor and interact with resolved target '{target.target_id}'",
            actions=[
                Action(
                    action_id=f"act_move_{uuid4().hex[:6]}",
                    task_id=task_id,
                    action_type="pointer_move",
                    tier=ActionTier.TIER_1_SAFE,
                    parameters={
                        "x": safe_pt.x,
                        "y": safe_pt.y,
                        "desktop_generation_id": safe_pt.desktop_generation_id,
                        "target_id": target.target_id,
                        "source": target.evidence.source,
                    },
                ),
                Action(
                    action_id=f"act_click_{uuid4().hex[:6]}",
                    task_id=task_id,
                    action_type="pointer_click",
                    tier=ActionTier.TIER_2_CONSTRAINED,
                    parameters=click_params,
                ),
            ],
        )
        return ExecutionPlan(
            plan_id=f"plan_{uuid4().hex[:8]}",
            task_id=task_id,
            description=f"Target-resolved execution plan for: {prompt} (Target: {target.target_id})",
            steps=[step_1],
        )

    def _build_synthetic_plan(
        self,
        task_id: str,
        prompt: str,
        generation_id: int = 0,
    ) -> ExecutionPlan:
        """Create an isolated development/test synthetic execution plan.

        SAFETY INVARIANT:
        This plan contains static/synthetic placeholder coordinates (500, 300) and is strictly
        isolated to explicit development and test harnesses. It can ONLY be reached when a task
        explicitly includes `is_synthetic_development=True` or `allow_synthetic_fallback=True` in metadata.
        All production autonomous tasks omit this flag and fail closed with TARGET_INTENT_REQUIRED.
        """
        step_1 = Step(
            step_id=f"step_1_{uuid4().hex[:6]}",
            step_index=0,
            description="Observe display and position cursor (Synthetic Development)",
            actions=[
                Action(
                    action_id=f"act_1_{uuid4().hex[:6]}",
                    task_id=task_id,
                    action_type="pointer_move",
                    tier=ActionTier.TIER_1_SAFE,
                    parameters={
                        "x": 500,
                        "y": 300,
                        "desktop_generation_id": generation_id,
                        "is_synthetic_development": True,
                    },
                ),
                Action(
                    action_id=f"act_2_{uuid4().hex[:6]}",
                    task_id=task_id,
                    action_type="pointer_click",
                    tier=ActionTier.TIER_2_CONSTRAINED,
                    parameters={
                        "x": 500,
                        "y": 300,
                        "button": "left",
                        "desktop_generation_id": generation_id,
                        "is_synthetic_development": True,
                    },
                ),
            ],
        )
        step_2 = Step(
            step_id=f"step_2_{uuid4().hex[:6]}",
            step_index=1,
            description="Type input content",
            actions=[
                Action(
                    action_id=f"act_3_{uuid4().hex[:6]}",
                    task_id=task_id,
                    action_type="type_text",
                    tier=ActionTier.TIER_2_CONSTRAINED,
                    parameters={
                        "text": f"ORBIT automated input: {prompt}",
                        "is_synthetic_development": True,
                    },
                ),
            ],
        )
        return ExecutionPlan(
            plan_id=f"plan_{uuid4().hex[:8]}",
            task_id=task_id,
            description=f"Development synthetic plan for: {prompt}",
            steps=[step_1, step_2],
        )


    async def _handle_cancellation(self, task_id: str, reason: Optional[str]) -> None:
        """Handle task cancellation cleanly."""
        task = await self._task_manager.get_task(task_id)
        if task:
            error = ErrorDetail(code="TASK_CANCELLED", message=reason or "Task cancelled", recoverable=False)
            await self._task_manager.update_status(task_id, TaskStatus.CANCELLED, error=error)
            await self._emit_task_event(task_id, TaskStatus.CANCELLED, error=error)

        sft = self.safety
        if sft:
            try:
                await sft.emergency_stop_all()
            except Exception as ex:
                logger.error("Error invoking emergency safety stop on cancel: %s", ex)

    async def _emit_task_event(
        self,
        task_id: str,
        status: TaskStatus,
        error: Optional[ErrorDetail] = None,
    ) -> None:
        task = await self._task_manager.get_task(task_id)
        if task:
            rec = await self._history_store.get_record_by_task_id(task_id)
            if rec:
                now_utc = datetime.now(timezone.utc)
                if status == TaskStatus.COMPLETED:
                    rec.status = ExecutionStatus.COMPLETED
                    rec.completed_at = now_utc
                    rec.duration_ms = (now_utc - rec.started_at).total_seconds() * 1000.0
                    rec.steps_completed = len(rec.steps)
                    if task.plan and not rec.steps:
                        rec.steps = [
                            ExecutionStepRecord(
                                step_id=s.step_id,
                                name=s.description,
                                status="COMPLETED",
                                action_type=s.actions[0].action_type if s.actions else None,
                            )
                            for s in task.plan.steps
                        ]
                        rec.total_steps = len(rec.steps)
                        rec.steps_completed = len(rec.steps)
                elif status == TaskStatus.FAILED:
                    rec.status = ExecutionStatus.FAILED
                    rec.completed_at = now_utc
                    rec.duration_ms = (now_utc - rec.started_at).total_seconds() * 1000.0
                    rec.failure_reason = error.message if error else "Task execution failed"
                    rec.failure_code = error.code if error else "FAILED"
                elif status == TaskStatus.CANCELLED:
                    rec.status = ExecutionStatus.CANCELLED
                    rec.completed_at = now_utc
                    rec.duration_ms = (now_utc - rec.started_at).total_seconds() * 1000.0
                    rec.cancellation_reason = error.message if error else "Cancelled"
                elif status == TaskStatus.RUNNING:
                    rec.status = ExecutionStatus.RUNNING
                    if task.plan and not rec.steps:
                        rec.steps = [
                            ExecutionStepRecord(
                                step_id=s.step_id,
                                name=s.description,
                                status="PENDING",
                                action_type=s.actions[0].action_type if s.actions else None,
                            )
                            for s in task.plan.steps
                        ]
                        rec.total_steps = len(rec.steps)

                await self._history_store.save_record(rec)
                await self._emit_event(
                    EventType.EXECUTION_RECORD_UPDATED,
                    session_id=task.session_id,
                    correlation_id=task_id,
                    payload={"record": rec.model_dump(mode="json")},
                )

            await self._emit_event(
                EventType.TASK_STATE_CHANGED,
                session_id=task.session_id,
                correlation_id=task_id,
                payload=TaskStatePayload(
                    task_id=task_id,
                    session_id=task.session_id,
                    status=status,
                    prompt=task.prompt,
                    error=error or task.error,
                ).model_dump(),
            )

    async def _emit_action_event(self, session_id: str, action: Action) -> None:
        await self._emit_event(
            EventType.ACTION_STAGE_CHANGED,
            session_id=session_id,
            correlation_id=action.task_id,
            payload=ActionStagePayload(
                action_id=action.action_id,
                task_id=action.task_id,
                stage=action.stage,
                action=action,
            ).model_dump(),
        )

    async def _emit_event(
        self,
        event_type: EventType,
        session_id: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> None:
        event = RuntimeEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=event_type,
            event_seq=self._event_bus.next_sequence(),
            timestamp=self._clock.now_utc(),
            session_id=session_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload,
        )
        await self._event_bus.publish(event)
