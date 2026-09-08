"""Closed-loop Sense -> Plan -> Validate -> Act -> Verify execution engine for ORBIT."""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import logging
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.adapters.registry import CapabilityRegistry
from orbit.config import is_human_takeover_enabled
from orbit.contracts.capabilities import (
    CapabilityType,
    EmergencySafetyCoordinator,
    HumanTakeoverCapability,
    KeyboardCapability,
    ObservationCapability,
    PointerCapability,
    WorkspaceCapability,
)
from orbit.contracts.runtime import SystemState

from orbit.infrastructure.clock import Clock, SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cancellation import CancellationSource, CancellationToken
from orbit.runtime.execution.context import (
    CancellationReason,
    DispatchStage,
    ExecutionContext,
    PreemptionRecord,
)
from orbit.runtime.execution.models import (
    ClosedLoopExecutionResult,
    ExecutionAttemptRecord,
    ExecutionPolicy,
    ExecutionState,
    RecoveryReason,
)
from orbit.runtime.execution.recovery import RecoveryCoordinator
from orbit.runtime.execution.retry_policy import FailureCategory
from orbit.runtime.execution.safety_gate import (
    AutonomousDispatchGate,
    PreemptionSafetyError,
)
from orbit.runtime.execution.state_machine import ClosedLoopStateMachine
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    ResolvedTarget,
    TargetIntent,
    TargetLocator,
    TargetResolutionStatus,
)
from orbit.runtime.verification import (
    ActionVerificationResult,
    ActionVerifier,
    ExpectedOutcome,
    VerificationOutcome,
)

logger = logging.getLogger(__name__)


class ClosedLoopExecutionEngine:
    """Bounded, fail-closed closed-loop execution engine for ORBIT with preemption safety."""

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        observation: Optional[ObservationCapability] = None,
        pointer: Optional[PointerCapability] = None,
        keyboard: Optional[KeyboardCapability] = None,
        takeover: Optional[HumanTakeoverCapability] = None,
        workspace: Optional[WorkspaceCapability] = None,
        safety: Optional[EmergencySafetyCoordinator] = None,
        target_locator: Optional[TargetLocator] = None,
        action_verifier: Optional[ActionVerifier] = None,
        event_bus: Optional[EventBus] = None,
        clock: Optional[Clock] = None,
        system_state_getter: Optional[Callable[[], SystemState]] = None,
        dispatch_gate: Optional[AutonomousDispatchGate] = None,
    ) -> None:
        self._registry = capability_registry
        self._obs = observation
        self._ptr = pointer
        self._kbd = keyboard
        self._tkv = takeover
        self._wsp = workspace
        self._sft = safety
        self._target_locator = target_locator or EvidenceBasedTargetLocator()
        self._action_verifier = action_verifier or ActionVerifier()
        self._event_bus = event_bus
        self._clock = clock or SystemClock()
        self._system_state_getter = system_state_getter
        self._dispatch_gate = dispatch_gate or AutonomousDispatchGate(
            emergency_safety_fn=self._emergency_stop,
        )

    @property
    def observation(self) -> Optional[ObservationCapability]:
        if self._registry and self._registry.has(CapabilityType.OBSERVATION):
            return self._registry.resolve_typed(CapabilityType.OBSERVATION, ObservationCapability)
        return self._obs

    @property
    def pointer(self) -> Optional[PointerCapability]:
        if self._registry and self._registry.has(CapabilityType.POINTER):
            return self._registry.resolve_typed(CapabilityType.POINTER, PointerCapability)
        return self._ptr

    @property
    def keyboard(self) -> Optional[KeyboardCapability]:
        if self._registry and self._registry.has(CapabilityType.KEYBOARD):
            return self._registry.resolve_typed(CapabilityType.KEYBOARD, KeyboardCapability)
        return self._kbd

    @property
    def takeover(self) -> Optional[HumanTakeoverCapability]:
        if self._registry and self._registry.has(CapabilityType.HUMAN_TAKEOVER):
            return self._registry.resolve_typed(CapabilityType.HUMAN_TAKEOVER, HumanTakeoverCapability)
        return self._tkv

    @property
    def workspace(self) -> Optional[WorkspaceCapability]:
        if self._registry and self._registry.has(CapabilityType.WORKSPACE):
            return self._registry.resolve_typed(CapabilityType.WORKSPACE, WorkspaceCapability)
        return self._wsp

    @property
    def safety(self) -> Optional[EmergencySafetyCoordinator]:
        if self._registry and self._registry.has(CapabilityType.SAFETY):
            return self._registry.resolve_typed(CapabilityType.SAFETY, EmergencySafetyCoordinator)
        return self._sft

    @property
    def dispatch_gate(self) -> AutonomousDispatchGate:
        return self._dispatch_gate

    async def _emergency_stop(self) -> None:
        sft = self.safety
        if sft and hasattr(sft, "emergency_stop_all"):
            try:
                await sft.emergency_stop_all()
            except Exception as ex:
                logger.error("Error invoking emergency safety stop: %s", ex)

    async def is_human_takeover_active(self) -> bool:
        """Check whether human takeover is active via system state or takeover adapter."""
        if not is_human_takeover_enabled():
            return False
        tkv = self.takeover
        if tkv and hasattr(tkv, "is_takeover_active"):
            res = tkv.is_takeover_active()
            import inspect
            if inspect.isawaitable(res):
                return await res
            return bool(res)
        if self._system_state_getter:
            if self._system_state_getter() == SystemState.HUMAN_TAKEOVER_ACTIVE:
                return True
        return False


    async def capture_observation_snapshot(self, target_hwnd: Optional[int] = None) -> Optional[ObservationSnapshot]:
        """Safely capture a desktop observation snapshot."""
        obs = self.observation
        if obs is None:
            return None
        if hasattr(obs, "capture_snapshot"):
            try:
                gen_id = None
                if self.workspace and hasattr(self.workspace, "get_desktop_generation"):
                    gen_id = self.workspace.get_desktop_generation()
                if gen_id is not None and hasattr(obs, "sync_generation"):
                    obs.sync_generation(gen_id)
                snap = await obs.capture_snapshot(target_hwnd=target_hwnd)
                return snap
            except Exception as ex:
                logger.warning("Failed to capture observation snapshot: %s", ex)
                return None
        return None

    def _create_preempted_result(
        self,
        context: ExecutionContext,
        sm: ClosedLoopStateMachine,
        coordinator: RecoveryCoordinator,
        attempts: List[ExecutionAttemptRecord],
        last_resolved_target: Optional[ResolvedTarget],
        last_verification_result: Optional[ActionVerificationResult],
        dispatch_stage: DispatchStage = DispatchStage.NOT_DISPATCHED,
        reason: Optional[CancellationReason] = None,
        message: Optional[str] = None,
    ) -> ClosedLoopExecutionResult:
        """Helper to build consistent, truthfully recorded preempted results."""
        eff_reason = reason or context.cancellation_reason or CancellationReason.OPERATOR_CANCEL
        is_takeover = eff_reason == CancellationReason.HUMAN_TAKEOVER
        term_state = ExecutionState.HUMAN_TAKEOVER if is_takeover else ExecutionState.CANCELLED
        eff_msg = message or context.cancellation_message or ("Human takeover active; execution preempted" if is_takeover else "Execution cancelled")

        if not sm.is_terminal:
            sm.transition_to(term_state, eff_msg)

        rec = context.last_preemption_record
        if rec is None:
            rec = PreemptionRecord(
                execution_id=context.execution_id,
                reason=eff_reason,
                state_at_preemption=sm.current_state.value,
                attempt_number=coordinator.total_attempts,
                replan_number=coordinator.recovery_attempts,
                action_dispatched_status=dispatch_stage,
                last_known_observation_generation=last_resolved_target.safe_point.desktop_generation_id if last_resolved_target else None,
                last_target_resolution_result=last_resolved_target.target_id if last_resolved_target else None,
                last_verification_result=last_verification_result.outcome.value if last_verification_result else None,
                message=eff_msg,
            )
            context.record_preemption(rec)

        return ClosedLoopExecutionResult(
            final_state=term_state,
            is_success=False,
            failure_code="HUMAN_TAKEOVER_ACTIVE" if is_takeover else "TASK_CANCELLED",
            failure_reason=eff_msg,
            dispatch_stage=dispatch_stage,
            preemption_record=rec,
            total_attempts=coordinator.total_attempts,
            total_recoveries=coordinator.recovery_attempts,
            total_verification_attempts=coordinator.total_attempts,
            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
            attempts=attempts,
            transition_history=sm.transition_history,
            verification_result=last_verification_result,
            resolved_target=last_resolved_target,
        )

    async def execute_task_action(
        self,
        session_id: str,
        task_id: str,
        prompt: str,
        target_intent: TargetIntent,
        action_type: str = "pointer_click",
        action_parameters: Optional[Dict[str, Any]] = None,
        expected_outcome: Optional[ExpectedOutcome] = None,
        policy: Optional[ExecutionPolicy] = None,
        cancel_token: Optional[CancellationToken] = None,
        context: Optional[ExecutionContext] = None,
        start_time: Optional[float] = None,
    ) -> ClosedLoopExecutionResult:
        """Execute a target-directed action through the bounded closed loop with cross-capability safety."""
        if policy is None:
            policy = ExecutionPolicy(
                allow_inconclusive_as_success=(expected_outcome is None),
            )
        elif isinstance(policy, dict):
            policy = ExecutionPolicy(**policy)
            if expected_outcome is None and not policy.allow_inconclusive_as_success:
                policy = policy.model_copy(update={"allow_inconclusive_as_success": True})
        elif expected_outcome is None and not policy.allow_inconclusive_as_success:
            policy = policy.model_copy(update={"allow_inconclusive_as_success": True})

        if context is None:
            context = ExecutionContext(
                execution_id=task_id,
                parent_token=cancel_token,
                takeover_checker=self.is_human_takeover_active,
            )

        sm = ClosedLoopStateMachine()
        coordinator = RecoveryCoordinator(policy=policy, start_time=start_time)
        attempts: List[ExecutionAttemptRecord] = []
        last_resolved_target: Optional[ResolvedTarget] = None
        last_verification_result: Optional[ActionVerificationResult] = None
        last_dispatch_stage: DispatchStage = DispatchStage.NOT_DISPATCHED
        action_params = action_parameters or {}

        logger.info(
            "Starting closed-loop execution for task %s (prompt: %s, max_attempts: %d)",
            task_id, prompt, policy.max_total_attempts,
        )

        while not sm.is_terminal:
            # 1. Global Preemption & Budget Guards (Boundary 1)
            if coordinator.is_timed_out:
                msg = f"Closed-loop execution timeout exceeded ({coordinator.elapsed_seconds:.2f}s >= {policy.execution_timeout_seconds:.2f}s)"
                logger.error(msg)
                sm.transition_to(ExecutionState.FAILED, msg)
                return ClosedLoopExecutionResult(
                    final_state=ExecutionState.FAILED,
                    is_success=False,
                    failure_code="EXECUTION_TIMEOUT",
                    failure_reason=msg,
                    dispatch_stage=last_dispatch_stage,
                    total_attempts=coordinator.total_attempts,
                    total_recoveries=coordinator.recovery_attempts,
                    total_verification_attempts=coordinator.total_attempts,
                    elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                    attempts=attempts,
                    transition_history=sm.transition_history,
                    verification_result=last_verification_result,
                    resolved_target=last_resolved_target,
                )

            if context.is_cancelled:
                await self._emergency_stop()
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=last_resolved_target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=last_dispatch_stage,
                )

            if await context.is_takeover_active():
                await self._emergency_stop()
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=last_resolved_target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=last_dispatch_stage,
                    reason=CancellationReason.HUMAN_TAKEOVER,
                )

            # 2. Phase: OBSERVING
            sm.transition_to(ExecutionState.OBSERVING, "Capturing fresh pre-action observation")
            snapshot = await self.capture_observation_snapshot(target_hwnd=target_intent.target_hwnd)

            # Post-Observation Preemption Guard (Boundary 2)
            if context.is_cancelled or await context.is_takeover_active():
                await self._emergency_stop()
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=last_resolved_target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=last_dispatch_stage,
                )

            if snapshot is None:
                rec_reason = RecoveryReason.STALE_OBSERVATION
                if coordinator.can_recover(rec_reason):
                    coordinator.record_recovery(rec_reason, {"snapshot_present": False})
                    sm.transition_to(ExecutionState.RECOVERING, "Observation snapshot unavailable; attempting recovery")
                    was_preempted = await context.wait_cancelled(timeout=coordinator.compute_backoff_delay())
                    if was_preempted or await context.is_takeover_active():
                        await self._emergency_stop()
                        return self._create_preempted_result(
                            context=context,
                            sm=sm,
                            coordinator=coordinator,
                            attempts=attempts,
                            last_resolved_target=last_resolved_target,
                            last_verification_result=last_verification_result,
                            dispatch_stage=last_dispatch_stage,
                        )
                    sm.transition_to(ExecutionState.RETRYING, "Retrying observation cycle")
                    continue
                else:
                    exhaustion = coordinator.get_exhaustion_reason(rec_reason)
                    msg = f"Failed to obtain observation snapshot. {exhaustion}"
                    logger.error(msg)
                    sm.transition_to(ExecutionState.FAILED, msg)
                    return ClosedLoopExecutionResult(
                        final_state=ExecutionState.FAILED,
                        is_success=False,
                        failure_code="TARGET_OBSERVATION_UNAVAILABLE",
                        failure_reason=msg,
                        dispatch_stage=last_dispatch_stage,
                        total_attempts=coordinator.total_attempts,
                        total_recoveries=coordinator.recovery_attempts,
                        total_verification_attempts=coordinator.total_attempts,
                        elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                        attempts=attempts,
                        transition_history=sm.transition_history,
                        verification_result=last_verification_result,
                        resolved_target=last_resolved_target,
                    )

            # 3. Phase: RESOLVING_TARGET (Boundary 3)
            if context.is_cancelled or await context.is_takeover_active():
                await self._emergency_stop()
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=last_resolved_target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=last_dispatch_stage,
                )

            sm.transition_to(ExecutionState.RESOLVING_TARGET, "Resolving target against observation evidence")
            resolution = self._target_locator.locate_target(snapshot, target_intent)
            if resolution.status != TargetResolutionStatus.RESOLVED or resolution.target is None:
                if resolution.status == TargetResolutionStatus.STALE_OBSERVATION:
                    rec_reason = RecoveryReason.STALE_OBSERVATION
                elif resolution.status == TargetResolutionStatus.NOT_FOUND:
                    rec_reason = RecoveryReason.TARGET_NOT_FOUND
                else:
                    rec_reason = RecoveryReason.TARGET_AMBIGUOUS

                if coordinator.can_recover(rec_reason):
                    coordinator.record_recovery(
                        rec_reason,
                        {"status": resolution.status.value, "diagnostic": resolution.diagnostic_message},
                    )
                    sm.transition_to(ExecutionState.RECOVERING, f"Target resolution {resolution.status.value}; attempting recovery")
                    was_preempted = await context.wait_cancelled(timeout=coordinator.compute_backoff_delay())
                    if was_preempted or await context.is_takeover_active():
                        await self._emergency_stop()
                        return self._create_preempted_result(
                            context=context,
                            sm=sm,
                            coordinator=coordinator,
                            attempts=attempts,
                            last_resolved_target=last_resolved_target,
                            last_verification_result=last_verification_result,
                            dispatch_stage=last_dispatch_stage,
                        )
                    sm.transition_to(ExecutionState.RETRYING, "Retrying target resolution with fresh observation")
                    continue
                else:
                    exhaustion = coordinator.get_exhaustion_reason(rec_reason)
                    msg = f"Target resolution failed: [{resolution.status.value}] {resolution.diagnostic_message}. {exhaustion}"
                    logger.error(msg)
                    sm.transition_to(ExecutionState.FAILED, msg)
                    return ClosedLoopExecutionResult(
                        final_state=ExecutionState.FAILED,
                        is_success=False,
                        failure_code=f"TARGET_{resolution.status.value}",
                        failure_reason=msg,
                        dispatch_stage=last_dispatch_stage,
                        total_attempts=coordinator.total_attempts,
                        total_recoveries=coordinator.recovery_attempts,
                        total_verification_attempts=coordinator.total_attempts,
                        elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                        attempts=attempts,
                        transition_history=sm.transition_history,
                        verification_result=last_verification_result,
                        resolved_target=None,
                    )

            target = resolution.target
            last_resolved_target = target

            # 4. Phase: VALIDATING (Boundary 4)
            if context.is_cancelled or await context.is_takeover_active():
                await self._emergency_stop()
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=last_resolved_target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=last_dispatch_stage,
                )

            sm.transition_to(ExecutionState.VALIDATING, "Validating target coordinates and workspace generation")
            safe_pt = target.safe_point
            x, y = safe_pt.x, safe_pt.y
            expected_gen = safe_pt.desktop_generation_id

            if self.workspace and hasattr(self.workspace, "validate_coordinate"):
                val_res = self.workspace.validate_coordinate(int(x), int(y), expected_generation=expected_gen)
                if not val_res.is_valid:
                    status_code = getattr(val_res.status, "value", str(val_res.status))
                    rec_reason = (
                        RecoveryReason.GENERATION_MISMATCH
                        if "GENERATION" in status_code
                        else RecoveryReason.COORDINATE_INVALID
                    )
                    if coordinator.can_recover(rec_reason):
                        coordinator.record_recovery(
                            rec_reason,
                            {"status": status_code, "msg": val_res.error_message, "x": x, "y": y},
                        )
                        sm.transition_to(ExecutionState.RECOVERING, f"Workspace coordinate validation failed ({status_code}); attempting recovery")
                        was_preempted = await context.wait_cancelled(timeout=coordinator.compute_backoff_delay())
                        if was_preempted or await context.is_takeover_active():
                            await self._emergency_stop()
                            return self._create_preempted_result(
                                context=context,
                                sm=sm,
                                coordinator=coordinator,
                                attempts=attempts,
                                last_resolved_target=last_resolved_target,
                                last_verification_result=last_verification_result,
                                dispatch_stage=last_dispatch_stage,
                            )
                        sm.transition_to(ExecutionState.RETRYING, "Retrying cycle with fresh generation and coordinates")
                        continue
                    else:
                        exhaustion = coordinator.get_exhaustion_reason(rec_reason)
                        msg = f"Workspace coordinate validation blocked dispatch to ({x}, {y}): [{status_code}] {val_res.error_message}. {exhaustion}"
                        logger.error(msg)
                        sm.transition_to(ExecutionState.FAILED, msg)
                        return ClosedLoopExecutionResult(
                            final_state=ExecutionState.FAILED,
                            is_success=False,
                            failure_code=status_code,
                            failure_reason=msg,
                            dispatch_stage=last_dispatch_stage,
                            total_attempts=coordinator.total_attempts,
                            total_recoveries=coordinator.recovery_attempts,
                            total_verification_attempts=coordinator.total_attempts,
                            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                            attempts=attempts,
                            transition_history=sm.transition_history,
                            verification_result=last_verification_result,
                            resolved_target=target,
                        )

            # 5. Phase: DISPATCHING via Atomic Pre-Dispatch Safety Gate (Boundary 5)
            sm.transition_to(ExecutionState.DISPATCHING, f"Dispatching {action_type} to ({x}, {y})")
            coordinator.record_attempt()
            attempt_idx = coordinator.total_attempts
            t_attempt_start = time.perf_counter()

            try:
                if action_type == "pointer_click":
                    ptr = self.pointer
                    if ptr is None:
                        msg = "Pointer capability is not available for pointer_click dispatch"
                        sm.transition_to(ExecutionState.FAILED, msg)
                        return ClosedLoopExecutionResult(
                            final_state=ExecutionState.FAILED,
                            is_success=False,
                            failure_code="CAPABILITY_UNAVAILABLE",
                            failure_reason=msg,
                            dispatch_stage=DispatchStage.NOT_DISPATCHED,
                            total_attempts=coordinator.total_attempts,
                            total_recoveries=coordinator.recovery_attempts,
                            total_verification_attempts=coordinator.total_attempts,
                            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                            attempts=attempts,
                            transition_history=sm.transition_history,
                            verification_result=last_verification_result,
                            resolved_target=target,
                        )
                    btn = action_params.get("button", "left")
                    count = action_params.get("count", 1)
                    target_hwnd = action_params.get("target_hwnd", target_intent.target_hwnd) or target.target_hwnd or (target.evidence.raw_metadata.get("hwnd") if target.evidence else None)
                    if target_hwnd and sys.platform == "win32":
                        try:
                            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                            EvidenceBasedTargetLocator._force_foreground_window(int(target_hwnd))
                        except Exception:
                            pass
                    last_dispatch_stage, _ = await self._dispatch_gate.execute_guarded(
                        "pointer_click",
                        context,
                        ptr.click,
                        sm.current_state.value,
                        attempt_idx,
                        coordinator.recovery_attempts,
                        expected_gen,
                        target.target_id,
                        int(x),
                        int(y),
                        button=btn,
                        count=count,
                        cancellation_token=context.token,
                    )
                elif action_type == "pointer_move":
                    ptr = self.pointer
                    if ptr is None:
                        msg = "Pointer capability is not available for pointer_move dispatch"
                        sm.transition_to(ExecutionState.FAILED, msg)
                        return ClosedLoopExecutionResult(
                            final_state=ExecutionState.FAILED,
                            is_success=False,
                            failure_code="CAPABILITY_UNAVAILABLE",
                            failure_reason=msg,
                            dispatch_stage=DispatchStage.NOT_DISPATCHED,
                            total_attempts=coordinator.total_attempts,
                            total_recoveries=coordinator.recovery_attempts,
                            total_verification_attempts=coordinator.total_attempts,
                            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                            attempts=attempts,
                            transition_history=sm.transition_history,
                            verification_result=last_verification_result,
                            resolved_target=target,
                        )
                    target_hwnd = action_params.get("target_hwnd", target_intent.target_hwnd) or target.target_hwnd or (target.evidence.raw_metadata.get("hwnd") if target.evidence else None)
                    if target_hwnd and sys.platform == "win32":
                        try:
                            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                            EvidenceBasedTargetLocator._force_foreground_window(int(target_hwnd))
                        except Exception:
                            pass
                    last_dispatch_stage, _ = await self._dispatch_gate.execute_guarded(
                        "pointer_move",
                        context,
                        ptr.move_to,
                        sm.current_state.value,
                        attempt_idx,
                        coordinator.recovery_attempts,
                        expected_gen,
                        target.target_id,
                        int(x),
                        int(y),
                        cancellation_token=context.token,
                    )
                elif action_type == "type_text":
                    kbd = self.keyboard
                    if kbd is None:
                        msg = "Keyboard capability is not available for type_text dispatch"
                        sm.transition_to(ExecutionState.FAILED, msg)
                        return ClosedLoopExecutionResult(
                            final_state=ExecutionState.FAILED,
                            is_success=False,
                            failure_code="CAPABILITY_UNAVAILABLE",
                            failure_reason=msg,
                            dispatch_stage=DispatchStage.NOT_DISPATCHED,
                            total_attempts=coordinator.total_attempts,
                            total_recoveries=coordinator.recovery_attempts,
                            total_verification_attempts=coordinator.total_attempts,
                            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                            attempts=attempts,
                            transition_history=sm.transition_history,
                            verification_result=last_verification_result,
                            resolved_target=target,
                        )
                    text = action_params.get("text", "")
                    target_hwnd = action_params.get("target_hwnd", target_intent.target_hwnd) or target.target_hwnd or (target.evidence.raw_metadata.get("hwnd") if target.evidence else None)
                    if target_hwnd and sys.platform == "win32":
                        try:
                            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                            EvidenceBasedTargetLocator._force_foreground_window(int(target_hwnd))
                        except Exception:
                            pass
                    last_dispatch_stage, _ = await self._dispatch_gate.execute_guarded(
                        "type_text",
                        context,
                        kbd.type_text,
                        sm.current_state.value,
                        attempt_idx,
                        coordinator.recovery_attempts,
                        expected_gen,
                        target.target_id,
                        text,
                        target_hwnd=target_hwnd,
                        cancellation_token=context.token,
                    )
                elif action_type in {"shortcut", "press_shortcut"}:
                    kbd = self.keyboard
                    if kbd is None:
                        msg = "Keyboard capability is not available for press_shortcut dispatch"
                        sm.transition_to(ExecutionState.FAILED, msg)
                        return ClosedLoopExecutionResult(
                            final_state=ExecutionState.FAILED,
                            is_success=False,
                            failure_code="CAPABILITY_UNAVAILABLE",
                            failure_reason=msg,
                            dispatch_stage=DispatchStage.NOT_DISPATCHED,
                            total_attempts=coordinator.total_attempts,
                            total_recoveries=coordinator.recovery_attempts,
                            total_verification_attempts=coordinator.total_attempts,
                            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                            attempts=attempts,
                            transition_history=sm.transition_history,
                            verification_result=last_verification_result,
                            resolved_target=target,
                        )
                    comb = action_params.get("combination", "ctrl+s")
                    target_hwnd = action_params.get("target_hwnd", target_intent.target_hwnd) or target.target_hwnd or (target.evidence.raw_metadata.get("hwnd") if target.evidence else None)
                    if target_hwnd and sys.platform == "win32":
                        try:
                            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                            EvidenceBasedTargetLocator._force_foreground_window(int(target_hwnd))
                        except Exception:
                            pass
                    last_dispatch_stage, _ = await self._dispatch_gate.execute_guarded(
                        "press_shortcut",
                        context,
                        kbd.press_shortcut,
                        sm.current_state.value,
                        attempt_idx,
                        coordinator.recovery_attempts,
                        expected_gen,
                        target.target_id,
                        comb,
                        target_hwnd=target_hwnd,
                        cancellation_token=context.token,
                    )
                elif action_type == "draw_strokes":
                    ptr = self.pointer
                    if ptr is None:
                        msg = "Pointer capability is not available for draw_strokes dispatch"
                        sm.transition_to(ExecutionState.FAILED, msg)
                        return ClosedLoopExecutionResult(
                            final_state=ExecutionState.FAILED,
                            is_success=False,
                            failure_code="CAPABILITY_UNAVAILABLE",
                            failure_reason=msg,
                            dispatch_stage=DispatchStage.NOT_DISPATCHED,
                            total_attempts=coordinator.total_attempts,
                            total_recoveries=coordinator.recovery_attempts,
                            total_verification_attempts=coordinator.total_attempts,
                            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                            attempts=attempts,
                            transition_history=sm.transition_history,
                            verification_result=last_verification_result,
                            resolved_target=target,
                        )
                    target_hwnd = action_params.get("target_hwnd", target_intent.target_hwnd) or target.target_hwnd or (target.evidence.raw_metadata.get("hwnd") if target.evidence else None)
                    if target_hwnd and sys.platform == "win32":
                        try:
                            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                            EvidenceBasedTargetLocator._force_foreground_window(int(target_hwnd))
                        except Exception:
                            pass

                    strokes = action_params.get("strokes", [])

                    async def _execute_all_strokes(strokes_list: list, center_x: int, center_y: int, cancellation_token=None) -> bool:
                        for stroke in strokes_list:
                            if not stroke:
                                continue
                            if context.is_cancelled or (cancellation_token and cancellation_token.is_cancelled):
                                break
                            start_x = center_x + stroke[0][0]
                            start_y = center_y + stroke[0][1]
                            await ptr.move_to(int(start_x), int(start_y))
                            await asyncio.sleep(0.02)
                            await ptr.press_down(button="left")
                            await asyncio.sleep(0.02)

                            for pt in stroke[1:]:
                                if context.is_cancelled or (cancellation_token and cancellation_token.is_cancelled):
                                    break
                                wx = center_x + pt[0]
                                wy = center_y + pt[1]
                                await ptr.move_to(int(wx), int(wy))
                                await asyncio.sleep(0.03)

                            await ptr.release_up(button="left")
                            await asyncio.sleep(0.03)
                        return True

                    last_dispatch_stage, _ = await self._dispatch_gate.execute_guarded(
                        "draw_strokes",
                        context,
                        _execute_all_strokes,
                        sm.current_state.value,
                        attempt_idx,
                        coordinator.recovery_attempts,
                        expected_gen,
                        target.target_id,
                        strokes,
                        int(x),
                        int(y),
                        cancellation_token=context.token,
                    )
                elif action_type == "observe":
                    last_dispatch_stage = DispatchStage.NOT_DISPATCHED
                    target_hwnd = action_params.get("target_hwnd", target_intent.target_hwnd) or target.target_hwnd or (target.evidence.raw_metadata.get("hwnd") if target.evidence else None)
                    if target_hwnd and sys.platform == "win32":
                        try:
                            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                            EvidenceBasedTargetLocator._force_foreground_window(int(target_hwnd))
                        except Exception:
                            pass
            except PreemptionSafetyError as pse:
                logger.warning("Action dispatch preempted by safety gate: %s", pse.message)
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=pse.dispatch_stage,
                    reason=pse.reason,
                    message=pse.message,
                )
            except Exception as ex:
                logger.error("Action dispatch failed with exception: %s", ex)
                rec_reason = RecoveryReason.DISPATCH_FAILED
                if coordinator.can_recover(rec_reason):
                    coordinator.record_recovery(rec_reason, {"error": str(ex), "attempt": attempt_idx})
                    sm.transition_to(ExecutionState.RECOVERING, f"Action dispatch failed ({ex}); attempting recovery")
                    was_preempted = await context.wait_cancelled(timeout=coordinator.compute_backoff_delay())
                    if was_preempted or await context.is_takeover_active():
                        await self._emergency_stop()
                        return self._create_preempted_result(
                            context=context,
                            sm=sm,
                            coordinator=coordinator,
                            attempts=attempts,
                            last_resolved_target=target,
                            last_verification_result=last_verification_result,
                            dispatch_stage=last_dispatch_stage,
                        )
                    sm.transition_to(ExecutionState.RETRYING, "Retrying action dispatch")
                    continue
                else:
                    exhaustion = coordinator.get_exhaustion_reason(rec_reason)
                    msg = f"Action dispatch failed: {ex}. {exhaustion}"
                    sm.transition_to(ExecutionState.FAILED, msg)
                    return ClosedLoopExecutionResult(
                        final_state=ExecutionState.FAILED,
                        is_success=False,
                        failure_code="DISPATCH_FAILED",
                        failure_reason=msg,
                        dispatch_stage=last_dispatch_stage,
                        total_attempts=coordinator.total_attempts,
                        total_recoveries=coordinator.recovery_attempts,
                        total_verification_attempts=coordinator.total_attempts,
                        elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                        attempts=attempts,
                        transition_history=sm.transition_history,
                        verification_result=last_verification_result,
                        resolved_target=target,
                    )

            # Post-dispatch preemption check (Boundary 6)
            if context.is_cancelled or await context.is_takeover_active():
                await self._emergency_stop()
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=last_dispatch_stage,
                )

            # 6. Phase: RE_OBSERVING (Boundary 7)
            sm.transition_to(ExecutionState.RE_OBSERVING, "Capturing fresh post-action observation")
            eff_hwnd = target_intent.target_hwnd or (target.target_hwnd if target else None)
            post_snapshot = await self.capture_observation_snapshot(target_hwnd=eff_hwnd)

            # Post-Re-Observe Preemption Guard (Boundary 8)
            if context.is_cancelled or await context.is_takeover_active():
                await self._emergency_stop()
                return self._create_preempted_result(
                    context=context,
                    sm=sm,
                    coordinator=coordinator,
                    attempts=attempts,
                    last_resolved_target=target,
                    last_verification_result=last_verification_result,
                    dispatch_stage=last_dispatch_stage,
                )

            # 7. Phase: VERIFYING
            sm.transition_to(ExecutionState.VERIFYING, "Evaluating verification against post-action evidence")
            verif_res = self._action_verifier.verify(
                pre_snapshot=snapshot,
                post_snapshot=post_snapshot,
                expected_outcome=expected_outcome,
            )
            last_verification_result = verif_res
            attempt_dur_ms = (time.perf_counter() - t_attempt_start) * 1000.0

            attempts.append(
                ExecutionAttemptRecord(
                    attempt_index=attempt_idx,
                    state_at_start=ExecutionState.DISPATCHING,
                    target_id=target.target_id,
                    dispatch_point=(int(x), int(y)),
                    generation_id=expected_gen,
                    verification_outcome=verif_res.outcome,
                    failure_reason=verif_res.failure_reason,
                    duration_ms=attempt_dur_ms,
                )
            )

            # Check verification verdict
            if verif_res.outcome == VerificationOutcome.VERIFIED_SUCCESS:
                msg = f"Target '{target.target_id}' verified successfully on attempt #{attempt_idx}"
                logger.info(msg)
                sm.transition_to(ExecutionState.SUCCEEDED, msg)
                return ClosedLoopExecutionResult(
                    final_state=ExecutionState.SUCCEEDED,
                    is_success=True,
                    dispatch_stage=last_dispatch_stage,
                    total_attempts=coordinator.total_attempts,
                    total_recoveries=coordinator.recovery_attempts,
                    total_verification_attempts=coordinator.total_attempts,
                    elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                    attempts=attempts,
                    transition_history=sm.transition_history,
                    verification_result=verif_res,
                    resolved_target=target,
                )

            if verif_res.outcome == VerificationOutcome.INCONCLUSIVE and policy.allow_inconclusive_as_success:
                msg = f"Target '{target.target_id}' inconclusive verification accepted as success by policy"
                logger.info(msg)
                sm.transition_to(ExecutionState.SUCCEEDED, msg)
                return ClosedLoopExecutionResult(
                    final_state=ExecutionState.SUCCEEDED,
                    is_success=True,
                    dispatch_stage=last_dispatch_stage,
                    total_attempts=coordinator.total_attempts,
                    total_recoveries=coordinator.recovery_attempts,
                    total_verification_attempts=coordinator.total_attempts,
                    elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                    attempts=attempts,
                    transition_history=sm.transition_history,
                    verification_result=verif_res,
                    resolved_target=target,
                )

            # Verification failed, stale, or inconclusive without permission (Boundary 9 & 10)
            rec_reason = (
                RecoveryReason.STALE_OBSERVATION
                if verif_res.outcome == VerificationOutcome.STALE_EVIDENCE
                else RecoveryReason.VERIFICATION_FAILED
            )

            if coordinator.can_recover(rec_reason):
                coordinator.record_recovery(
                    rec_reason,
                    {
                        "outcome": verif_res.outcome.value,
                        "reason": verif_res.failure_reason,
                        "attempt": attempt_idx,
                    },
                )
                sm.transition_to(ExecutionState.RECOVERING, f"Verification {verif_res.outcome.value}; initiating bounded recovery")
                was_preempted = await context.wait_cancelled(timeout=coordinator.compute_backoff_delay())
                if was_preempted or await context.is_takeover_active():
                    await self._emergency_stop()
                    return self._create_preempted_result(
                        context=context,
                        sm=sm,
                        coordinator=coordinator,
                        attempts=attempts,
                        last_resolved_target=target,
                        last_verification_result=last_verification_result,
                        dispatch_stage=last_dispatch_stage,
                    )
                sm.transition_to(ExecutionState.RETRYING, "Retrying closed loop with fresh observation")
                continue
            else:
                exhaustion = coordinator.get_exhaustion_reason(rec_reason)
                msg = f"Action verification failed ({verif_res.outcome.value}): {verif_res.failure_reason}. {exhaustion}"
                logger.error(msg)
                sm.transition_to(ExecutionState.FAILED, msg)
                return ClosedLoopExecutionResult(
                    final_state=ExecutionState.FAILED,
                    is_success=False,
                    failure_code=verif_res.outcome.value,
                    failure_reason=msg,
                    dispatch_stage=last_dispatch_stage,
                    total_attempts=coordinator.total_attempts,
                    total_recoveries=coordinator.recovery_attempts,
                    total_verification_attempts=coordinator.total_attempts,
                    elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
                    attempts=attempts,
                    transition_history=sm.transition_history,
                    verification_result=verif_res,
                    resolved_target=target,
                )

        # Fallback terminal outcome
        return ClosedLoopExecutionResult(
            final_state=sm.current_state,
            is_success=sm.current_state == ExecutionState.SUCCEEDED,
            failure_code=sm.current_state.value if sm.current_state != ExecutionState.SUCCEEDED else None,
            failure_reason="Execution terminated in non-success terminal state",
            dispatch_stage=last_dispatch_stage,
            total_attempts=coordinator.total_attempts,
            total_recoveries=coordinator.recovery_attempts,
            total_verification_attempts=coordinator.total_attempts,
            elapsed_duration_ms=coordinator.elapsed_seconds * 1000.0,
            attempts=attempts,
            transition_history=sm.transition_history,
            verification_result=last_verification_result,
            resolved_target=last_resolved_target,
        )
