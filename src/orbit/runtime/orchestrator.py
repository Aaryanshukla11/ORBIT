"""Central ORBIT Runtime Orchestrator coordinating task lifecycles and capabilities."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityNotFoundError,
    CapabilityUnavailableError,
)
from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.adapters.registry import CapabilityRegistry
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
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ClosedLoopExecutionResult,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.verification import (
    ActionVerificationResult,
    ActionVerifier,
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
    VerificationStrategy,
)
from orbit.runtime.task_understanding import (
    TaskUnderstandingEngine,
    TaskUnderstandingResult,
)
from orbit.runtime.planning import (
    ExecutableTaskPlan,
    TaskPlanningEngine,
)
from orbit.runtime.plan_execution import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanExecutor,
)
from orbit.runtime.replanning import DynamicReplanner
from orbit.runtime.task_completion import (
    GoalVerifier,
    TaskCompletionEngine,
    TaskExecutionResult,
)

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
        execution_engine: Optional[ClosedLoopExecutionEngine] = None,
        replanner: Optional[DynamicReplanner] = None,
    ) -> None:
        self._event_bus = event_bus
        self._clock = clock or SystemClock()
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
        self._task_understanding_engine = TaskUnderstandingEngine()
        self._task_planning_engine = TaskPlanningEngine(understanding_engine=self._task_understanding_engine)
        self._execution_engine = execution_engine or ClosedLoopExecutionEngine(
            capability_registry=self._registry,
            target_locator=self._target_locator,
            action_verifier=self._action_verifier,
            event_bus=self._event_bus,
            clock=self._clock,
            system_state_getter=lambda: self.system_state,
        )
        self._replanner = replanner or DynamicReplanner(observation=self.observation)
        self._plan_executor = PlanExecutor(
            execution_engine=self._execution_engine,
            replanner=self._replanner,
            event_bus=self._event_bus,
        )
        self._task_completion_engine = TaskCompletionEngine(
            plan_executor=self._plan_executor,
            observation=self.observation,
            task_understanding_engine=self._task_understanding_engine,
            task_planning_engine=self._task_planning_engine,
            perception_engine=self._perception_engine,
        )
        self._active_cancellation_sources: Dict[str, CancellationSource] = {}
        self._active_execution_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    @property
    def system_state(self) -> SystemState:
        return self._system_sm.current_state

    @property
    def task_manager(self) -> TaskManager:
        return self._task_manager

    @property
    def task_understanding_engine(self) -> TaskUnderstandingEngine:
        return self._task_understanding_engine

    @property
    def task_planning_engine(self) -> TaskPlanningEngine:
        return self._task_planning_engine

    @property
    def plan_executor(self) -> PlanExecutor:
        return self._plan_executor

    @property
    def task_completion_engine(self) -> TaskCompletionEngine:
        return self._task_completion_engine

    @property
    def replanner(self) -> DynamicReplanner:
        return self._replanner

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def execution_engine(self) -> ClosedLoopExecutionEngine:
        return self._execution_engine

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

    async def initialize(self) -> None:
        """Initialize capabilities and transition system state to IDLE."""
        async with self._lock:
            # Initialize all capabilities via registry
            health_reports = await self._registry.initialize_all()

            # Register takeover hook callback if takeover capability is registered and ready
            if self._registry.is_ready(CapabilityType.HUMAN_TAKEOVER):
                tkv = self._registry.resolve_typed(CapabilityType.HUMAN_TAKEOVER, HumanTakeoverCapability)
                await tkv.start_monitoring(self._on_physical_takeover_detected)

            # Wire takeover check to workspace capability if supported
            wsp_adapter = self._registry.get_optional(CapabilityType.WORKSPACE)
            if wsp_adapter and hasattr(wsp_adapter, "is_takeover_active_fn"):
                wsp_adapter.is_takeover_active_fn = lambda: self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE

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

            self._system_sm.transition_to(SystemState.SHUTDOWN)

    def _on_physical_takeover_detected(self, evidence: Optional[Any] = None) -> None:
        """Callback triggered when physical human input is detected."""
        reason = "Physical human input detected"
        source = "human_input"
        if evidence and hasattr(evidence, "reason"):
            reason = str(evidence.reason)
        if evidence and hasattr(evidence, "source"):
            source = str(evidence.source.value if hasattr(evidence.source, "value") else evidence.source)
        asyncio.create_task(self.handle_human_takeover(reason=reason, source=source))

    async def handle_human_takeover(
        self,
        reason: str = "Human takeover triggered",
        source: str = "human_input",
    ) -> None:
        """Preempt active execution fail-closed on human takeover."""
        logger.warning("HUMAN TAKEOVER TRIGGERED (%s): %s", source, reason)
        async with self._lock:
            if self._system_sm.can_transition_to(SystemState.HUMAN_TAKEOVER_ACTIVE):
                self._system_sm.transition_to(SystemState.HUMAN_TAKEOVER_ACTIVE)

            # Cancel active execution tokens
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

    def understand_task(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskUnderstandingResult:
        """Interpret a natural-language prompt into a validated structured task representation (M1.8 Step 1)."""
        return self._task_understanding_engine.understand(prompt, metadata=context or {})

    def plan_task(
        self,
        understanding_or_prompt: Union[TaskUnderstandingResult, str],
        task_id: Optional[str] = None,
    ) -> ExecutableTaskPlan:
        """Generate a validated, dependency-aware execution plan from structured understanding or raw prompt (M1.8 Step 2)."""
        return self._task_planning_engine.plan_task(understanding_or_prompt, task_id=task_id)

    async def execute_plan(
        self,
        plan: ExecutableTaskPlan,
        session_id: str,
        task_id: Optional[str] = None,
        policy: Optional[ExecutionPolicy] = None,
        cancel_token: Optional[CancellationToken] = None,
    ) -> PlanExecutionResult:
        """Execute a validated ExecutableTaskPlan sequentially with dynamic replanning and recovery (M1.8 Step 4)."""
        return await self._plan_executor.execute_plan(
            plan=plan,
            session_id=session_id,
            task_id=task_id,
            policy=policy,
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
        """Execute a natural-language task goal end-to-end with independent goal verification (M1.8 Step 5)."""
        target_goal = goal or prompt or ""
        return await self._task_completion_engine.execute_task(
            goal=target_goal,
            session_id=session_id,
            task_id=task_id,
            context=context,
            policy=policy,
            cancel_token=cancel_token,
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

        # Launch execution in background task
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

            # Check system state
            async with self._lock:
                if self._system_sm.current_state in {SystemState.HUMAN_TAKEOVER_ACTIVE, SystemState.UNRESOLVED_LOCKED}:
                    raise RuntimeError(f"Cannot execute task while in state {self._system_sm.current_state}")
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

            # Step 2: Target Resolution & Plan Generation
            target_intent_data = task.metadata.get("target_intent")
            if target_intent_data:
                # 1. Parse TargetIntent
                if isinstance(target_intent_data, TargetIntent):
                    intent = target_intent_data
                elif isinstance(target_intent_data, dict):
                    intent = TargetIntent(**target_intent_data)
                else:
                    raise ValueError(f"Invalid target_intent type: {type(target_intent_data)}")

                exp_outcome = None
                if intent:
                    if isinstance(intent, dict):
                        exp_outcome = intent.get("expected_outcome")
                    else:
                        exp_outcome = getattr(intent, "expected_outcome", None)
                if exp_outcome is not None and isinstance(exp_outcome, dict):
                    try:
                        exp_outcome = ExpectedOutcome.model_validate(exp_outcome)
                    except Exception:
                        pass

                exec_policy = task.metadata.get("execution_policy")
                if exec_policy is not None and isinstance(exec_policy, dict):
                    try:
                        exec_policy = ExecutionPolicy.model_validate(exec_policy)
                    except Exception:
                        exec_policy = None

                act_type = task.metadata.get("action_type", "pointer_click")
                act_params = task.metadata.get("action_parameters", {})

                # Delegate to ClosedLoopExecutionEngine
                exec_result: ClosedLoopExecutionResult = await self._execution_engine.execute_task_action(
                    session_id=session_id,
                    task_id=task_id,
                    prompt=task.prompt,
                    target_intent=intent,
                    action_type=act_type,
                    action_parameters=act_params,
                    expected_outcome=exp_outcome,
                    policy=exec_policy,
                    cancel_token=cancel_token,
                )

                task.metadata["execution_result"] = exec_result.model_dump()

                if not exec_result.is_success:
                    err_code = exec_result.failure_code or exec_result.final_state.value
                    err_msg = exec_result.failure_reason or f"Closed-loop execution failed in state {err_code}"
                    error_detail = ErrorDetail(
                        code=err_code,
                        message=err_msg,
                        recoverable=False,
                        details={
                            "final_state": exec_result.final_state.value,
                            "total_attempts": exec_result.total_attempts,
                            "total_recoveries": exec_result.total_recoveries,
                            "elapsed_duration_ms": exec_result.elapsed_duration_ms,
                        },
                    )
                    terminal_status = (
                        TaskStatus.CANCELLED
                        if exec_result.final_state == ExecutionState.CANCELLED
                        else TaskStatus.FAILED
                    )
                    await self._task_manager.update_status(task_id, terminal_status, error=error_detail)
                    await self._emit_task_event(task_id, terminal_status, error=error_detail)
                    return

                # Record verified plan representation
                if exec_result.resolved_target:
                    plan = self._build_target_resolved_plan(
                        task_id, task.prompt, exec_result.resolved_target, expected_outcome=exp_outcome
                    )
                    await self._task_manager.set_plan(task_id, plan)
                    await self._emit_event(
                        EventType.PLAN_UPDATED,
                        session_id=session_id,
                        correlation_id=task_id,
                        payload=PlanUpdatedPayload(task_id=task_id, plan=plan).model_dump(),
                    )

                # Transition to VERIFYING then COMPLETED
                await self._task_manager.update_status(task_id, TaskStatus.VERIFYING)
                await self._emit_task_event(task_id, TaskStatus.VERIFYING)

                await self._task_manager.update_status(task_id, TaskStatus.COMPLETED)
                await self._emit_task_event(task_id, TaskStatus.COMPLETED)
                return
            else:
                # M1.8 Step 1 & Step 2: Execute Task Understanding and Task Planning on raw prompt
                if "task_understanding" not in task.metadata:
                    understanding = self._task_understanding_engine.understand(
                        task.prompt, metadata=task.metadata
                    )
                    task.metadata["task_understanding"] = understanding.model_dump()
                else:
                    understanding = TaskUnderstandingResult.model_validate(task.metadata["task_understanding"])

                if "task_plan" not in task.metadata and understanding.has_intents:
                    plan_obj = self._task_planning_engine.plan_task(understanding, task_id=task_id)
                    task.metadata["task_plan"] = plan_obj.model_dump()
                elif "task_plan" in task.metadata:
                    plan_obj = ExecutableTaskPlan.model_validate(task.metadata["task_plan"])
                else:
                    plan_obj = None

                should_execute_plan = bool(
                    task.metadata.get("execute_plan", False)
                    or task.metadata.get("auto_execute_plan", False)
                )

                if should_execute_plan and plan_obj is not None:
                    exec_policy = None
                    policy_data = task.metadata.get("execution_policy")
                    if policy_data and isinstance(policy_data, dict):
                        try:
                            exec_policy = ExecutionPolicy.model_validate(policy_data)
                        except Exception:
                            exec_policy = None

                    plan_res = await self._plan_executor.execute_plan(
                        plan=plan_obj,
                        session_id=session_id,
                        task_id=task_id,
                        policy=exec_policy,
                        cancel_token=cancel_token,
                    )
                    task.metadata["plan_execution_result"] = plan_res.model_dump()

                    if not plan_res.is_success:
                        err_code = plan_res.failure_code or "PLAN_EXECUTION_FAILED"
                        err_msg = plan_res.failure_reason or f"Plan execution failed with status {plan_res.final_status.value}"
                        terminal_status = (
                            TaskStatus.CANCELLED
                            if plan_res.final_status == PlanExecutionStatus.CANCELLED
                            else TaskStatus.FAILED
                        )
                        error_detail = ErrorDetail(
                            code=err_code,
                            message=err_msg,
                            recoverable=False,
                            details={
                                "final_status": plan_res.final_status.value,
                                "total_steps": plan_res.total_steps,
                                "completed_steps": plan_res.completed_steps,
                                "failed_steps": plan_res.failed_steps,
                                "blocked_steps": plan_res.blocked_steps,
                            },
                        )
                        await self._task_manager.update_status(task_id, terminal_status, error=error_detail)
                        await self._emit_task_event(task_id, terminal_status, error=error_detail)
                        return

                    # Plan succeeded
                    await self._task_manager.update_status(task_id, TaskStatus.VERIFYING)
                    await self._emit_task_event(task_id, TaskStatus.VERIFYING)
                    await self._task_manager.update_status(task_id, TaskStatus.COMPLETED)
                    await self._emit_task_event(task_id, TaskStatus.COMPLETED)
                    return

                is_synthetic_dev = bool(
                    task.metadata.get("is_synthetic_development", False)
                    or task.metadata.get("allow_synthetic_fallback", False)
                )
                if not is_synthetic_dev:
                    err_msg = (
                        "Autonomous task execution rejected: missing required 'target_intent' in task metadata. "
                        "Production autonomous execution fails closed when no valid structured TargetIntent exists."
                    )
                    logger.error("Task %s rejected: %s", task_id, err_msg)
                    error_detail = ErrorDetail(
                        code="TARGET_INTENT_REQUIRED",
                        message=err_msg,
                        recoverable=False,
                    )
                    await self._task_manager.update_status(task_id, TaskStatus.FAILED, error=error_detail)
                    await self._emit_task_event(task_id, TaskStatus.FAILED, error=error_detail)
                    return

                # Isolated development synthetic plan explicitly requested
                active_gen = self.workspace.get_desktop_generation() if self.workspace and hasattr(self.workspace, "get_desktop_generation") else 0
                plan = self._build_synthetic_plan(task_id, task.prompt, generation_id=active_gen)

                await self._task_manager.set_plan(task_id, plan)
                await self._emit_event(
                    EventType.PLAN_UPDATED,
                    session_id=session_id,
                    correlation_id=task_id,
                    payload=PlanUpdatedPayload(task_id=task_id, plan=plan).model_dump(),
                )

                # Step 3: Execute Planned Steps
                for step_idx, step in enumerate(plan.steps):
                    if cancel_token.is_cancelled:
                        await self._handle_cancellation(task_id, cancel_token.reason)
                        return

                    await self._task_manager.set_current_step(task_id, step_idx)

                    for action in step.actions:
                        if cancel_token.is_cancelled:
                            await self._handle_cancellation(task_id, cancel_token.reason)
                            return

                        await self._execute_action(session_id, action, cancel_token)

                # 4. Verifying Phase
                await self._task_manager.update_status(task_id, TaskStatus.VERIFYING)
                await self._emit_task_event(task_id, TaskStatus.VERIFYING)

                # 5. Completed Phase
                await self._task_manager.update_status(task_id, TaskStatus.COMPLETED)
                await self._emit_task_event(task_id, TaskStatus.COMPLETED)

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
                if self._system_sm.current_state == SystemState.BUSY:
                    self._system_sm.transition_to(SystemState.IDLE)
                self._active_cancellation_sources.pop(task_id, None)
                self._active_execution_tasks.pop(task_id, None)

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
            if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
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
                await ptr.click(int(x), int(y), button=btn, count=count, cancellation_token=cancel_token)
            elif action.action_type == "pointer_move":
                await ptr.move_to(int(x), int(y), cancellation_token=cancel_token)

        elif action.action_type == "type_text":
            if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
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
            await kbd.type_text(text, target_hwnd=target_hwnd, cancellation_token=cancel_token)
        elif action.action_type == "shortcut":
            if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
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
            await kbd.press_shortcut(comb, target_hwnd=target_hwnd, cancellation_token=cancel_token)
        elif action.action_type == "observe":
            if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
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
            if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
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
            if self._system_sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
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

        expected_outcome = action.parameters.get("expected_outcome")
        if expected_outcome is not None and isinstance(expected_outcome, dict):
            try:
                expected_outcome = ExpectedOutcome.model_validate(expected_outcome)
            except Exception:
                pass

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
                    parameters={"text": f"ORBIT automated input: {prompt}"},
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
