"""
Thread-Safe, Monotonic Cancellation Contract for ORBIT Prototype E.
(Phase 1 Cancellation & Preemption Token)

Enforces cooperative, monotonic, and idempotent cancellation propagation
across observation, planning, validation, and future execution loops.
"""

import threading
import time
from typing import Callable, List, Optional

from app_types import ActionCancellationState


class CancellationToken:
    """
    Thread-safe, monotonic, and idempotent cancellation token.
    Once cancelled, the token remains permanently in the cancelled state
    for the duration of its lifecycle.
    """

    def __init__(self, token_id: Optional[str] = None):
        self._token_id = token_id or f"token_{time.perf_counter_ns()}"
        self._is_cancelled_event = threading.Event()
        self._reason: str = "NONE"
        self._cancelled_timestamp_ns: int = 0
        self._callbacks: List[Callable[[], None]] = []
        self._lock = threading.Lock()

    @property
    def token_id(self) -> str:
        return self._token_id

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled_event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def cancelled_timestamp_ns(self) -> int:
        return self._cancelled_timestamp_ns

    @property
    def state(self) -> ActionCancellationState:
        return ActionCancellationState(
            is_cancelled=self.is_cancelled,
            reason=self._reason,
            timestamp_ns=self._cancelled_timestamp_ns,
        )

    def cancel(self, reason: str = "USER_TAKEOVER") -> bool:
        """
        Signals cancellation monotonically and idempotently.
        Returns True if this call transitioned the state from active to cancelled,
        or False if the token was already cancelled.
        """
        callbacks_to_invoke: List[Callable[[], None]] = []

        with self._lock:
            if self._is_cancelled_event.is_set():
                return False  # Already cancelled

            self._reason = reason
            self._cancelled_timestamp_ns = time.perf_counter_ns()
            self._is_cancelled_event.set()
            callbacks_to_invoke = list(self._callbacks)

        # Invoke callbacks outside lock to prevent deadlocks
        for callback in callbacks_to_invoke:
            try:
                callback()
            except Exception:
                pass  # Telemetry / logging in higher layers

        return True

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Registers a callback to be invoked immediately upon cancellation."""
        should_invoke_now = False
        with self._lock:
            if self._is_cancelled_event.is_set():
                should_invoke_now = True
            else:
                self._callbacks.append(callback)

        if should_invoke_now:
            try:
                callback()
            except Exception:
                pass

    def check_cancelled(self) -> None:
        """Raises an InterruptedError if cancellation was requested."""
        if self.is_cancelled:
            raise InterruptedError(f"Action cancelled: {self._reason}")
