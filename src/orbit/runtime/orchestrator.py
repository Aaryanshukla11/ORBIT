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
from orbit.runtime.state_machine import ActionStateMachine, SystemStateMachine
from orbit.runtime.task_manager import TaskManager

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
    ) -> None:
        self._event_bus = event_bus
        self._clock = clock or SystemClock()

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
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

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

            # Step 2: Generate Execution Plan
            plan = self._build_synthetic_plan(task_id, task.prompt)
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

        # Dispatch to capabilities
        if action.action_type == "pointer_click":
            ptr = self._registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
            x = action.parameters.get("x", 100)
            y = action.parameters.get("y", 100)
            btn = action.parameters.get("button", "left")
            await ptr.click(x, y, button=btn)
        elif action.action_type == "pointer_move":
            ptr = self._registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
            x = action.parameters.get("x", 100)
            y = action.parameters.get("y", 100)
            await ptr.move_to(x, y)
        elif action.action_type == "type_text":
            kbd = self._registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
            text = action.parameters.get("text", "")
            await kbd.type_text(text)
        elif action.action_type == "shortcut":
            kbd = self._registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
            comb = action.parameters.get("combination", "ctrl+s")
            await kbd.press_shortcut(comb)
        elif action.action_type == "observe":
            obs = self._registry.resolve_typed(CapabilityType.OBSERVATION, ObservationCapability)
            await obs.capture_screen()

        if cancel_token.is_cancelled:
            action.stage = action_sm.transition_to(ActionStage.CANCELLED)
            await self._emit_action_event(session_id, action)
            return

        # Transition: EXECUTING -> VERIFYING
        action.stage = action_sm.transition_to(ActionStage.VERIFYING)
        await self._emit_action_event(session_id, action)

        action.verification = VerificationResult(
            status=VerificationStatus.PASSED,
            confidence=1.0,
            details={"verification_mode": "mock_immediate"},
        )

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
        return None

    def _build_synthetic_plan(self, task_id: str, prompt: str) -> ExecutionPlan:
        """Create a structured execution plan for task fulfillment."""
        step_1 = Step(
            step_id=f"step_1_{uuid4().hex[:6]}",
            step_index=0,
            description="Observe display and position cursor",
            actions=[
                Action(
                    action_id=f"act_1_{uuid4().hex[:6]}",
                    task_id=task_id,
                    action_type="pointer_move",
                    tier=ActionTier.TIER_1_SAFE,
                    parameters={"x": 500, "y": 300},
                ),
                Action(
                    action_id=f"act_2_{uuid4().hex[:6]}",
                    task_id=task_id,
                    action_type="pointer_click",
                    tier=ActionTier.TIER_2_CONSTRAINED,
                    parameters={"x": 500, "y": 300, "button": "left"},
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
            description=f"Automated execution plan for: {prompt}",
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
