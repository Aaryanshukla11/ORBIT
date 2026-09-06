"""Atomic Pre-Dispatch Safety Gate for cross-capability autonomous execution."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, TypeVar

from orbit.runtime.execution.context import (
    CancellationReason,
    DispatchStage,
    ExecutionContext,
    PreemptionRecord,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PreemptionSafetyError(RuntimeError):
    """Raised when an autonomous action is rejected or preempted by the safety gate."""

    def __init__(
        self,
        message: str,
        dispatch_stage: DispatchStage = DispatchStage.NOT_DISPATCHED,
        reason: CancellationReason = CancellationReason.HUMAN_TAKEOVER,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.dispatch_stage = dispatch_stage
        self.reason = reason
        self.details = details or {}


class AutonomousDispatchGate:
    """Atomic safety gate guarding physical OS event dispatch across all capabilities."""

    def __init__(
        self,
        emergency_safety_fn: Optional[Callable[[], Union[None, Awaitable[None]]]] = None,
    ) -> None:
        self._emergency_safety_fn = emergency_safety_fn
        self._sync_lock = threading.RLock()
        self._async_lock = asyncio.Lock()

    async def can_dispatch(
        self,
        context: ExecutionContext,
        action_name: str = "autonomous_action",
    ) -> Tuple[bool, Optional[str], CancellationReason]:
        """Check whether dispatch is permitted without initiating an action.

        Returns (allowed, rejection_reason, canonical_cancellation_reason).
        """
        # 1. Check if already cancelled
        if context.is_cancelled:
            reason = context.cancellation_reason or CancellationReason.OPERATOR_CANCEL
            msg = f"Dispatch of '{action_name}' rejected: execution cancelled ({reason.value})"
            return False, msg, reason

        # 2. Check live human takeover
        if await context.is_takeover_active():
            reason = CancellationReason.HUMAN_TAKEOVER
            msg = f"Dispatch of '{action_name}' rejected: Human takeover is currently active"
            return False, msg, reason

        return True, None, CancellationReason.OPERATOR_CANCEL

    async def execute_guarded(
        self,
        action_name: str,
        context: ExecutionContext,
        dispatch_fn: Callable[..., Awaitable[T]],
        current_state: str = "DISPATCHING",
        attempt_number: int = 0,
        replan_number: int = 0,
        generation_id: Optional[int] = None,
        target_id: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Tuple[DispatchStage, T]:
        """Atomically validate safety conditions and execute side-effecting OS action.

        Guarantees:
        - If human takeover is active: ZERO OS events dispatched.
        - Raises PreemptionSafetyError fail-closed.
        - Epistemically records in-flight status transitions truthfully.
        """
        async with self._async_lock:
            # Atomic Pre-Dispatch Validation
            allowed, rejection_msg, reason = await self.can_dispatch(context, action_name)
            if not allowed:
                # Record forensic evidence
                rec = PreemptionRecord(
                    execution_id=context.execution_id,
                    reason=reason,
                    state_at_preemption=current_state,
                    attempt_number=attempt_number,
                    replan_number=replan_number,
                    action_dispatched_status=DispatchStage.NOT_DISPATCHED,
                    last_known_observation_generation=generation_id,
                    last_target_resolution_result=target_id,
                    message=rejection_msg,
                )
                context.record_preemption(rec)
                logger.warning("SAFETY GATE REJECTION: %s", rejection_msg)

                # Emergency stop hardware if safety hook wired
                if self._emergency_safety_fn:
                    try:
                        res = self._emergency_safety_fn()
                        if inspect.isawaitable(res):
                            await res
                    except Exception as sft_ex:
                        logger.error("Error running emergency safety fn during pre-dispatch rejection: %s", sft_ex)

                raise PreemptionSafetyError(
                    message=rejection_msg or "Dispatch rejected by safety gate",
                    dispatch_stage=DispatchStage.NOT_DISPATCHED,
                    reason=reason,
                    details={
                        "action_name": action_name,
                        "attempt": attempt_number,
                        "state": current_state,
                    },
                )

            # Stage: DISPATCH_IN_PROGRESS
            dispatch_stage = DispatchStage.DISPATCH_IN_PROGRESS
            t_dispatch_start = asyncio.get_running_loop().time()

            try:
                # Dispatch the actual OS action
                result = await dispatch_fn(*args, **kwargs)
                dispatch_stage = DispatchStage.DISPATCHED
                return dispatch_stage, result

            except asyncio.CancelledError:
                # Cancellation occurred while OS dispatch was executing
                dispatch_stage = DispatchStage.OUTCOME_UNKNOWN
                msg = f"Task cancelled during in-flight OS dispatch of '{action_name}'"
                logger.warning(msg)
                rec = PreemptionRecord(
                    execution_id=context.execution_id,
                    reason=context.cancellation_reason or CancellationReason.OPERATOR_CANCEL,
                    state_at_preemption=current_state,
                    attempt_number=attempt_number,
                    replan_number=replan_number,
                    action_dispatched_status=DispatchStage.OUTCOME_UNKNOWN,
                    last_known_observation_generation=generation_id,
                    last_target_resolution_result=target_id,
                    message=msg,
                )
                context.record_preemption(rec)
                raise PreemptionSafetyError(
                    message=msg,
                    dispatch_stage=DispatchStage.OUTCOME_UNKNOWN,
                    reason=context.cancellation_reason or CancellationReason.OPERATOR_CANCEL,
                )

            except Exception as ex:
                # If an error occurred inside the capability
                dispatch_stage = DispatchStage.OUTCOME_UNKNOWN
                logger.error("Error during OS dispatch of '%s': %s", action_name, ex)
                raise
