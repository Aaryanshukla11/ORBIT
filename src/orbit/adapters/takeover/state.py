"""Thread-safe Takeover State Machine with strict transition invariants and deduplication."""

from __future__ import annotations

from enum import Enum
import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Set

from orbit.adapters.takeover.classifier import TakeoverEvidence

logger = logging.getLogger(__name__)


class TakeoverState(str, Enum):
    """Discrete states for Human Takeover capability."""
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    MONITORING = "MONITORING"
    TAKEOVER_TRIGGERED = "TAKEOVER_TRIGGERED"
    TAKEOVER_ACTIVE = "TAKEOVER_ACTIVE"
    RELEASE_PENDING = "RELEASE_PENDING"
    RELEASING = "RELEASING"
    FAILED = "FAILED"


class TakeoverStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, current_state: TakeoverState, target_state: TakeoverState, reason: str = ""):
        self.current_state = current_state
        self.target_state = target_state
        msg = f"Cannot transition TakeoverState from '{current_state.value}' to '{target_state.value}'"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class TakeoverStateManager:
    """Manages takeover state lifecycle, event deduplication, and quiet-period tracking."""

    _VALID_TRANSITIONS: Dict[TakeoverState, Set[TakeoverState]] = {
        TakeoverState.STOPPED: {
            TakeoverState.STARTING,
            TakeoverState.MONITORING,
            TakeoverState.FAILED,
        },
        TakeoverState.STARTING: {
            TakeoverState.MONITORING,
            TakeoverState.TAKEOVER_TRIGGERED,
            TakeoverState.TAKEOVER_ACTIVE,
            TakeoverState.FAILED,
            TakeoverState.STOPPED,
        },
        TakeoverState.MONITORING: {
            TakeoverState.TAKEOVER_TRIGGERED,
            TakeoverState.TAKEOVER_ACTIVE,
            TakeoverState.STOPPED,
            TakeoverState.FAILED,
        },
        TakeoverState.TAKEOVER_TRIGGERED: {
            TakeoverState.TAKEOVER_ACTIVE,
            TakeoverState.STOPPED,
            TakeoverState.FAILED,
        },
        TakeoverState.TAKEOVER_ACTIVE: {
            TakeoverState.RELEASE_PENDING,
            TakeoverState.RELEASING,
            TakeoverState.MONITORING,
            TakeoverState.STOPPED,
            TakeoverState.FAILED,
        },
        TakeoverState.RELEASE_PENDING: {
            TakeoverState.TAKEOVER_ACTIVE,
            TakeoverState.RELEASING,
            TakeoverState.MONITORING,
            TakeoverState.STOPPED,
            TakeoverState.FAILED,
        },
        TakeoverState.RELEASING: {
            TakeoverState.MONITORING,
            TakeoverState.TAKEOVER_ACTIVE,
            TakeoverState.STOPPED,
            TakeoverState.FAILED,
        },
        TakeoverState.FAILED: {TakeoverState.STOPPED, TakeoverState.STARTING, TakeoverState.TAKEOVER_ACTIVE},
    }

    def __init__(self, quiet_period_seconds: float = 1.0) -> None:
        self._state: TakeoverState = TakeoverState.STOPPED
        self._lock = threading.RLock()
        self._state_change_time_ns: int = time.perf_counter_ns()
        self._last_evidence: Optional[TakeoverEvidence] = None
        self._last_activity_time_ns: int = 0
        self._quiet_period_seconds = quiet_period_seconds
        self._quiet_timer: Optional[threading.Timer] = None
        self._listeners: List[Callable[[TakeoverState, TakeoverState, Optional[TakeoverEvidence]], None]] = []

    @property
    def current_state(self) -> TakeoverState:
        with self._lock:
            return self._state

    @property
    def last_evidence(self) -> Optional[TakeoverEvidence]:
        with self._lock:
            return self._last_evidence

    @property
    def is_monitoring(self) -> bool:
        with self._lock:
            return self._state in (TakeoverState.MONITORING, TakeoverState.TAKEOVER_TRIGGERED, TakeoverState.TAKEOVER_ACTIVE, TakeoverState.RELEASE_PENDING)

    @property
    def is_takeover_active(self) -> bool:
        with self._lock:
            return self._state in (TakeoverState.TAKEOVER_TRIGGERED, TakeoverState.TAKEOVER_ACTIVE)

    @property
    def last_activity_time_ns(self) -> int:
        with self._lock:
            return self._last_activity_time_ns

    @property
    def last_activity_elapsed_ms(self) -> float:
        with self._lock:
            if not self._last_activity_time_ns:
                return float("inf")
            return max(0.0, (time.perf_counter_ns() - self._last_activity_time_ns) / 1_000_000.0)

    def get_diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "current_state": self._state.value,
                "is_takeover_active": self.is_takeover_active,
                "last_activity_elapsed_ms": round(self.last_activity_elapsed_ms, 2),
                "quiet_period_seconds": self._quiet_period_seconds,
                "last_evidence": self._last_evidence.model_dump() if self._last_evidence else None,
            }

    def add_listener(self, listener: Callable[[TakeoverState, TakeoverState, Optional[TakeoverEvidence]], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def can_transition_to(self, target: TakeoverState) -> bool:
        with self._lock:
            if target == self._state:
                return True
            return target in self._VALID_TRANSITIONS.get(self._state, set())

    def transition_to(
        self,
        target: TakeoverState,
        reason: str = "",
        evidence: Optional[TakeoverEvidence] = None,
    ) -> bool:
        with self._lock:
            if target == self._state:
                return False

            if not self.can_transition_to(target):
                raise TakeoverStateTransitionError(self._state, target, reason)

            old_state = self._state
            self._state = target
            self._state_change_time_ns = time.perf_counter_ns()

            if evidence:
                self._last_evidence = evidence
                self._last_activity_time_ns = evidence.timestamp_ns or time.perf_counter_ns()
            elif target in (TakeoverState.TAKEOVER_TRIGGERED, TakeoverState.TAKEOVER_ACTIVE):
                self._last_activity_time_ns = time.perf_counter_ns()

            # Manage quiet timer
            if target == TakeoverState.TAKEOVER_ACTIVE:
                self._arm_quiet_timer()
            elif target in (TakeoverState.MONITORING, TakeoverState.STOPPED, TakeoverState.FAILED):
                self._disarm_quiet_timer()

            listeners_copy = list(self._listeners)

        for listener in listeners_copy:
            try:
                listener(old_state, target, evidence)
            except Exception as ex:
                logger.warning("Error in takeover state change listener: %s", ex)

        return True

    def handle_takeover_event(self, evidence: TakeoverEvidence) -> bool:
        """Processes a takeover evidence packet with deduplication.

        Returns True if this event triggered a NEW takeover transition, False if deduplicated.
        """
        with self._lock:
            self._last_activity_time_ns = evidence.timestamp_ns

            if self._state == TakeoverState.MONITORING:
                # Primary takeover trigger
                self.transition_to(TakeoverState.TAKEOVER_TRIGGERED, reason=evidence.reason, evidence=evidence)
                self.transition_to(TakeoverState.TAKEOVER_ACTIVE, reason=evidence.reason, evidence=evidence)
                return True
            elif self._state in (TakeoverState.TAKEOVER_TRIGGERED, TakeoverState.TAKEOVER_ACTIVE, TakeoverState.RELEASE_PENDING):
                # Deduplicated: refresh quiet period timer and record latest evidence
                if self._state == TakeoverState.RELEASE_PENDING:
                    self.transition_to(TakeoverState.TAKEOVER_ACTIVE, reason="User activity resumed", evidence=evidence)
                else:
                    self._last_evidence = evidence
                    self._arm_quiet_timer()
                return False
            else:
                return False

    def _arm_quiet_timer(self) -> None:
        self._disarm_quiet_timer()

        def on_quiet():
            with self._lock:
                if self._state == TakeoverState.TAKEOVER_ACTIVE:
                    try:
                        self.transition_to(TakeoverState.RELEASE_PENDING, reason=f"Inactivity quiet period ({self._quiet_period_seconds}s)")
                    except Exception as ex:
                        logger.warning("Quiet period transition failed: %s", ex)

        self._quiet_timer = threading.Timer(self._quiet_period_seconds, on_quiet)
        self._quiet_timer.daemon = True
        self._quiet_timer.start()

    def _disarm_quiet_timer(self) -> None:
        if self._quiet_timer:
            self._quiet_timer.cancel()
            self._quiet_timer = None
