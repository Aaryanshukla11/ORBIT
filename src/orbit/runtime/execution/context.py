"""Authoritative Execution Context and Cancellation Authority for ORBIT."""

from __future__ import annotations

from collections import deque
from enum import Enum
import inspect
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Deque, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from orbit.config import is_human_takeover_enabled
from orbit.runtime.cancellation import CancellationSource, CancellationToken

logger = logging.getLogger(__name__)


class CancellationReason(str, Enum):

    """Canonical reasons for cancelling or preempting autonomous execution."""

    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    RUNTIME_SHUTDOWN = "RUNTIME_SHUTDOWN"
    OPERATOR_CANCEL = "OPERATOR_CANCEL"
    SAFETY_ABORT = "SAFETY_ABORT"
    TIMEOUT = "TIMEOUT"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class DispatchStage(str, Enum):
    """Truthful epistemic status of an autonomous OS input action."""

    NOT_DISPATCHED = "NOT_DISPATCHED"
    DISPATCH_IN_PROGRESS = "DISPATCH_IN_PROGRESS"
    DISPATCHED = "DISPATCHED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class PreemptionRecord(BaseModel):
    """Structured forensic evidence recorded when an execution is preempted."""

    model_config = ConfigDict(frozen=True)

    execution_id: str
    reason: CancellationReason
    state_at_preemption: str
    attempt_number: int = 0
    replan_number: int = 0
    action_dispatched_status: DispatchStage = DispatchStage.NOT_DISPATCHED
    last_known_observation_generation: Optional[int] = None
    last_target_resolution_result: Optional[str] = None
    last_verification_result: Optional[str] = None
    message: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class ExecutionContext:
    """Canonical authority managing execution lifecycle, cancellation, and preemption."""

    def __init__(
        self,
        execution_id: Optional[str] = None,
        parent_token: Optional[CancellationToken] = None,
        takeover_checker: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
        max_history: int = 50,
    ) -> None:
        self._execution_id: str = execution_id or f"exec-{uuid4().hex[:12]}"
        self._source: CancellationSource = CancellationSource(parent=parent_token)
        self._takeover_checker = takeover_checker
        self._cancellation_reason: Optional[CancellationReason] = None
        self._cancellation_message: Optional[str] = None
        self._lock = threading.RLock()
        self._preemption_history: Deque[PreemptionRecord] = deque(maxlen=max_history)

        # Wire parent cancellation to map to OPERATOR_CANCEL by default if triggered
        if parent_token:
            parent_token.register_callback(self._on_parent_cancelled)

    @property
    def execution_id(self) -> str:
        return self._execution_id

    @property
    def token(self) -> CancellationToken:
        return self._source.token

    @property
    def is_cancelled(self) -> bool:
        return self._source.is_cancelled

    @property
    def cancellation_reason(self) -> Optional[CancellationReason]:
        with self._lock:
            return self._cancellation_reason

    @property
    def cancellation_message(self) -> Optional[str]:
        with self._lock:
            return self._cancellation_message or self._source.reason

    @property
    def last_preemption_record(self) -> Optional[PreemptionRecord]:
        with self._lock:
            return self._preemption_history[-1] if self._preemption_history else None

    def get_preemption_records(self) -> List[PreemptionRecord]:
        with self._lock:
            return list(self._preemption_history)

    def cancel(
        self,
        reason: Union[CancellationReason, str] = CancellationReason.OPERATOR_CANCEL,
        message: Optional[str] = None,
    ) -> None:
        """Idempotently trigger cancellation with canonical reason."""
        with self._lock:
            canonical_reason: CancellationReason
            if isinstance(reason, CancellationReason):
                canonical_reason = reason
            else:
                try:
                    canonical_reason = CancellationReason(str(reason))
                except ValueError:
                    # Map free-form strings
                    upper = str(reason).upper()
                    if "TAKEOVER" in upper:
                        canonical_reason = CancellationReason.HUMAN_TAKEOVER
                    elif "SHUTDOWN" in upper:
                        canonical_reason = CancellationReason.RUNTIME_SHUTDOWN
                    elif "TIMEOUT" in upper:
                        canonical_reason = CancellationReason.TIMEOUT
                    elif "ABORT" in upper:
                        canonical_reason = CancellationReason.SAFETY_ABORT
                    elif "FAIL" in upper or "ERROR" in upper:
                        canonical_reason = CancellationReason.INTERNAL_FAILURE
                    else:
                        canonical_reason = CancellationReason.OPERATOR_CANCEL

            if not self._cancellation_reason:
                self._cancellation_reason = canonical_reason
            if message and not self._cancellation_message:
                self._cancellation_message = message

            detail = message or f"Execution cancelled: {canonical_reason.value}"
            self._source.cancel(detail)

    def _on_parent_cancelled(self) -> None:
        parent_reason = self._source.reason or "Parent token cancelled"
        self.cancel(CancellationReason.OPERATOR_CANCEL, message=parent_reason)

    async def is_takeover_active(self) -> bool:
        """Poll takeover state. If active, automatically latch HUMAN_TAKEOVER cancellation."""
        if not is_human_takeover_enabled():
            return False
        if self._takeover_checker is None:
            return False
        try:
            res = self._takeover_checker()
            if inspect.isawaitable(res):
                is_active = bool(await res)
            else:
                is_active = bool(res)
        except Exception as ex:
            logger.error("Error evaluating takeover checker in ExecutionContext: %s", ex)
            return False

        if is_active and not self.is_cancelled:
            self.cancel(
                reason=CancellationReason.HUMAN_TAKEOVER,
                message="Human takeover active; execution preempted fail-closed",
            )
        return is_active


    async def wait_cancelled(self, timeout: Optional[float] = None) -> bool:
        """Wait for cancellation or timeout. Returns True if cancelled, False if timed out."""
        if self.is_cancelled:
            return True
        if timeout is None:
            await self._source.wait_cancelled()
            return True

        import asyncio
        try:
            await asyncio.wait_for(self._source.wait_cancelled(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return self.is_cancelled

    def record_preemption(self, record: PreemptionRecord) -> None:
        """Store structured preemption evidence in bounded history."""
        with self._lock:
            self._preemption_history.append(record)
            if not self._cancellation_reason:
                self._cancellation_reason = record.reason
            if not self._cancellation_message and record.message:
                self._cancellation_message = record.message
