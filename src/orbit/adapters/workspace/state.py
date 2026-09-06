"""Thread-safe Workspace State Machine with strict transition validation and generation tracking."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Set

from orbit.adapters.workspace.types import WorkspaceState

logger = logging.getLogger(__name__)


class WorkspaceStateTransitionError(Exception):
    """Raised when an invalid or forbidden workspace state transition is attempted."""

    def __init__(self, current_state: WorkspaceState, target_state: WorkspaceState, reason: str = "") -> None:
        self.current_state = current_state
        self.target_state = target_state
        msg = f"Cannot transition WorkspaceState from '{current_state.value}' to '{target_state.value}'"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class WorkspaceStateManager:
    """Manages workspace lifecycle state, transition invariants, and desktop generation tracking."""

    _VALID_TRANSITIONS: Dict[WorkspaceState, Set[WorkspaceState]] = {
        WorkspaceState.UNINITIALIZED: {
            WorkspaceState.READY_FLOATING,
            WorkspaceState.FAILED,
            WorkspaceState.STOPPED,
        },
        WorkspaceState.READY_FLOATING: {
            WorkspaceState.REGISTERING,
            WorkspaceState.DEGRADED,
            WorkspaceState.FAILED,
            WorkspaceState.STOPPED,
        },
        WorkspaceState.REGISTERING: {
            WorkspaceState.DOCKED,
            WorkspaceState.READY_FLOATING,
            WorkspaceState.DEGRADED,
            WorkspaceState.FAILED,
            WorkspaceState.STOPPED,
        },
        WorkspaceState.DOCKED: {
            WorkspaceState.RELEASING,
            WorkspaceState.REGISTERING,  # Reconfiguration / edge change
            WorkspaceState.DEGRADED,
            WorkspaceState.FAILED,
            WorkspaceState.STOPPED,
        },
        WorkspaceState.RELEASING: {
            WorkspaceState.READY_FLOATING,
            WorkspaceState.DOCKED,
            WorkspaceState.DEGRADED,
            WorkspaceState.FAILED,
            WorkspaceState.STOPPED,
        },
        WorkspaceState.DEGRADED: {
            WorkspaceState.READY_FLOATING,
            WorkspaceState.FAILED,
            WorkspaceState.STOPPED,
        },
        WorkspaceState.FAILED: {
            WorkspaceState.READY_FLOATING,
            WorkspaceState.STOPPED,
        },
        WorkspaceState.STOPPED: set(),  # Terminal state
    }

    def __init__(self, initial_state: WorkspaceState = WorkspaceState.UNINITIALIZED) -> None:
        self._state: WorkspaceState = initial_state
        self._lock = threading.RLock()
        self._desktop_generation_id: int = 1
        self._topology_generation_id: int = 1
        self._state_change_time_ns: int = time.perf_counter_ns()
        self._last_error: Optional[str] = None
        self._listeners: List[Callable[[WorkspaceState, WorkspaceState, Optional[str]], None]] = []
        self._transition_history: List[Dict[str, Any]] = []

    @property
    def current_state(self) -> WorkspaceState:
        with self._lock:
            return self._state

    @property
    def is_docked(self) -> bool:
        with self._lock:
            return self._state == WorkspaceState.DOCKED

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._state in {WorkspaceState.READY_FLOATING, WorkspaceState.DOCKED}

    @property
    def desktop_generation_id(self) -> int:
        with self._lock:
            return self._desktop_generation_id

    @property
    def topology_generation_id(self) -> int:
        with self._lock:
            return self._topology_generation_id

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def can_transition_to(self, target: WorkspaceState) -> bool:
        """Check whether transition to target state is legally allowed."""
        with self._lock:
            if target == self._state:
                return True
            return target in self._VALID_TRANSITIONS.get(self._state, set())

    def transition_to(
        self,
        target: WorkspaceState,
        reason: Optional[str] = None,
        recovery_token: Optional[str] = None,
    ) -> WorkspaceState:
        """Execute a validated state transition with generation increment on layout mutation."""
        listeners_to_notify = []
        old_state = WorkspaceState.UNINITIALIZED

        with self._lock:
            if target == self._state:
                return self._state

            # Recovery from DEGRADED or FAILED requires confirmation token if recovering directly to READY_FLOATING
            if self._state in {WorkspaceState.DEGRADED, WorkspaceState.FAILED} and target == WorkspaceState.READY_FLOATING:
                if recovery_token not in {"CONFIRM_RESET", "CONFIRM_OPERATOR_MANUAL_RESET"}:
                    raise WorkspaceStateTransitionError(
                        self._state,
                        target,
                        "Recovery requires valid recovery token ('CONFIRM_RESET')",
                    )

            if not self.can_transition_to(target):
                raise WorkspaceStateTransitionError(self._state, target, reason or "Forbidden state transition")

            old_state = self._state
            self._state = target
            now_ns = time.perf_counter_ns()
            self._state_change_time_ns = now_ns

            # Monotonic desktop generation increment on layout changes:
            # Increment when entering DOCKED, leaving DOCKED, or reconfiguring
            if (old_state == WorkspaceState.REGISTERING and target == WorkspaceState.DOCKED) or (
                old_state == WorkspaceState.DOCKED and target in {WorkspaceState.RELEASING, WorkspaceState.READY_FLOATING, WorkspaceState.REGISTERING}
            ):
                self._desktop_generation_id += 1
                logger.info(
                    "Workspace layout mutated: %s -> %s (desktop_generation_id incremented to %d)",
                    old_state.value,
                    target.value,
                    self._desktop_generation_id,
                )

            if target in {WorkspaceState.FAILED, WorkspaceState.DEGRADED}:
                self._last_error = reason

            self._transition_history.append({
                "from_state": old_state.value,
                "to_state": target.value,
                "timestamp_ns": now_ns,
                "reason": reason,
                "desktop_generation_id": self._desktop_generation_id,
            })

            listeners_to_notify = list(self._listeners)

        # Notify listeners outside lock
        for listener in listeners_to_notify:
            try:
                listener(old_state, target, reason)
            except Exception as ex:
                logger.error("Error in WorkspaceState listener callback: %s", ex)

        return target

    def increment_desktop_generation(self) -> int:
        """Increment desktop generation counter on explicit layout or geometry mutation."""
        with self._lock:
            self._desktop_generation_id += 1
            logger.info("Desktop generation explicitly incremented to %d", self._desktop_generation_id)
            return self._desktop_generation_id

    def increment_topology_generation(self) -> int:
        """Increment topology generation counter on display metric / monitor change."""
        with self._lock:
            self._topology_generation_id += 1
            self._desktop_generation_id += 1
            logger.info(
                "Display topology mutated (topology_gen=%d, desktop_gen=%d)",
                self._topology_generation_id,
                self._desktop_generation_id,
            )
            return self._topology_generation_id

    def add_listener(self, callback: Callable[[WorkspaceState, WorkspaceState, Optional[str]], None]) -> None:
        """Register a state transition listener."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[WorkspaceState, WorkspaceState, Optional[str]], None]) -> None:
        """Unregister a state transition listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def get_transition_history(self) -> List[Dict[str, Any]]:
        """Get snapshot of transition history."""
        with self._lock:
            return list(self._transition_history)
