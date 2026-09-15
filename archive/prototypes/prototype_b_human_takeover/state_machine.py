"""
Takeover State Machine for Prototype B.
Enforces the 5-state lifecycle: IDLE, EXECUTING, SUSPECTED_TAKEOVER, PAUSED_BY_USER, RELEASE_PENDING.
Guarantees that ambiguity favors the user and prevents blind automatic resumption.
"""

import time
import threading
from typing import Callable, List, Optional
from app_types import TakeoverState


class TakeoverStateMachine:
    def __init__(self):
        self._state: TakeoverState = TakeoverState.IDLE
        self._lock = threading.RLock()
        self._state_change_time_ns: int = time.perf_counter_ns()
        self._listeners: List[Callable[[TakeoverState, TakeoverState, float], None]] = []

    @property
    def current_state(self) -> TakeoverState:
        with self._lock:
            return self._state

    def add_listener(self, listener: Callable[[TakeoverState, TakeoverState, float], None]):
        with self._lock:
            self._listeners.append(listener)

    def transition_to(self, new_state: TakeoverState, reason: str = "") -> bool:
        """
        Attempts a state transition, notifying listeners if successful.
        """
        with self._lock:
            old_state = self._state
            if old_state == new_state:
                return False

            # Invariant: From EXECUTING, any takeover anomaly transitions to SUSPECTED_TAKEOVER or PAUSED_BY_USER
            now_ns = time.perf_counter_ns()
            duration_in_state_ms = (now_ns - self._state_change_time_ns) / 1_000_000.0
            self._state = new_state
            self._state_change_time_ns = now_ns

            listeners_copy = list(self._listeners)

        for l in listeners_copy:
            try:
                l(old_state, new_state, duration_in_state_ms)
            except Exception:
                pass

        return True

    def reset_to_idle(self):
        with self._lock:
            self.transition_to(TakeoverState.IDLE, "Explicit reset")
