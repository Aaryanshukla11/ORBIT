"""Production Pointer State Manager & Fail-Closed Hard Lockout Engine for ORBIT M1.2B."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import threading
import time
from typing import Dict, Optional, Set
from uuid import uuid4

from orbit.adapters.pointer.safety import MouseButton


class PointerTransactionState(str, Enum):
    """Authoritative state machine states for synthetic pointer ownership."""

    IDLE = "IDLE"
    BUTTON_DOWN_IN_PROGRESS = "BUTTON_DOWN_IN_PROGRESS"
    BUTTON_HELD_SYNTHETIC = "BUTTON_HELD_SYNTHETIC"
    BUTTON_UP_IN_PROGRESS = "BUTTON_UP_IN_PROGRESS"
    PARTIAL_DISPATCH = "PARTIAL_DISPATCH"
    SANITIZATION_PENDING = "SANITIZATION_PENDING"
    SANITIZED_RECOVERED = "SANITIZED_RECOVERED"
    UNRESOLVED_LOCKED = "UNRESOLVED_LOCKED"


class SyntheticButtonState(str, Enum):
    """Synthetic button state tracked internally by ORBIT."""

    RELEASED = "RELEASED"
    PRESSED = "PRESSED"


class LockoutReason(str, Enum):
    """Root cause classifications for entering UNRESOLVED_LOCKED state."""

    NONE = "NONE"
    BUTTON_UP_DISPATCH_FAILED = "BUTTON_UP_DISPATCH_FAILED"
    SANITIZATION_DISPATCH_FAILED = "SANITIZATION_DISPATCH_FAILED"
    PARTIAL_DISPATCH_UNRESOLVED = "PARTIAL_DISPATCH_UNRESOLVED"
    UNEXPECTED_TRANSACTION_FAULT = "UNEXPECTED_TRANSACTION_FAULT"
    MANUAL_ADMIN_LOCKOUT = "MANUAL_ADMIN_LOCKOUT"


@dataclass(frozen=True)
class PointerStateSnapshot:
    """Immutable point-in-time snapshot of the pointer state machine."""

    transaction_state: PointerTransactionState
    held_buttons: Set[MouseButton]
    is_locked: bool
    lockout_reason: LockoutReason
    recovery_token_required: bool
    consecutive_sanitizations: int
    last_transition_timestamp_ns: int
    active_in_flight_button: Optional[MouseButton]


class PointerStateManager:
    """Authoritative thread-safe state machine managing synthetic button ownership,

    transaction lifecycles, emergency sanitization, and fail-closed hard lockout.

    CRITICAL INVARIANTS:
    1. PRIMARY OWNERSHIP INVARIANT:
       ORBIT must never lose track of a button state it synthetically created.
    2. HARD LOCKOUT IMMUTABILITY:
       When UNRESOLVED_LOCKED, all subsequent actions are rejected fail-closed.
       No timer or silent reset may clear the lock.
       Only an explicit recovery call with a valid recovery token can restore IDLE.
    3. EPISTEMIC SEPARATION:
       Internal synthetic state != Win32 dispatch return != OS observable state.
    """

    def __init__(self) -> None:
        self._mutex = threading.RLock()
        self._transaction_state = PointerTransactionState.IDLE
        self._held_buttons: Set[MouseButton] = set()
        self._in_flight_button: Optional[MouseButton] = None
        self._is_locked = False
        self._lockout_reason = LockoutReason.NONE
        self._active_recovery_token: Optional[str] = None
        self._consecutive_sanitizations = 0
        self._last_transition_timestamp_ns = time.perf_counter_ns()

    @property
    def transaction_state(self) -> PointerTransactionState:
        with self._mutex:
            return self._transaction_state

    @property
    def is_locked(self) -> bool:
        with self._mutex:
            return self._is_locked

    @property
    def lockout_reason(self) -> LockoutReason:
        with self._mutex:
            return self._lockout_reason

    @property
    def held_buttons(self) -> Set[MouseButton]:
        with self._mutex:
            return set(self._held_buttons)

    def get_snapshot(self) -> PointerStateSnapshot:
        """Returns an immutable snapshot of current state."""
        with self._mutex:
            return PointerStateSnapshot(
                transaction_state=self._transaction_state,
                held_buttons=set(self._held_buttons),
                is_locked=self._is_locked,
                lockout_reason=self._lockout_reason,
                recovery_token_required=self._is_locked,
                consecutive_sanitizations=self._consecutive_sanitizations,
                last_transition_timestamp_ns=self._last_transition_timestamp_ns,
                active_in_flight_button=self._in_flight_button,
            )

    # ------------------------------------------------------------------
    # State Machine Transitions
    # ------------------------------------------------------------------

    def start_button_down(self, button: MouseButton) -> None:
        """Initiate BUTTON_DOWN transaction."""
        with self._mutex:
            if self._is_locked:
                raise RuntimeError(f"Pointer is UNRESOLVED_LOCKED (reason: {self._lockout_reason.value}). Actions rejected.")
            if self._transaction_state != PointerTransactionState.IDLE:
                raise RuntimeError(
                    f"Cannot start BUTTON_DOWN from state {self._transaction_state.value}. Must be IDLE."
                )
            if button in self._held_buttons:
                raise RuntimeError(f"Button {button.value} is already synthetically HELD.")

            self._transaction_state = PointerTransactionState.BUTTON_DOWN_IN_PROGRESS
            self._in_flight_button = button
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def confirm_button_down(self, button: MouseButton) -> None:
        """Confirm successful native dispatch (M=1) of BUTTON_DOWN."""
        with self._mutex:
            if self._transaction_state != PointerTransactionState.BUTTON_DOWN_IN_PROGRESS:
                raise RuntimeError(
                    f"Cannot confirm BUTTON_DOWN from state {self._transaction_state.value}."
                )
            self._held_buttons.add(button)
            self._in_flight_button = None
            self._transaction_state = PointerTransactionState.BUTTON_HELD_SYNTHETIC
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def abort_button_down(self, button: MouseButton) -> None:
        """Abort BUTTON_DOWN on zero dispatch (M=0) or pre-dispatch cancellation."""
        with self._mutex:
            if self._transaction_state != PointerTransactionState.BUTTON_DOWN_IN_PROGRESS:
                raise RuntimeError(
                    f"Cannot abort BUTTON_DOWN from state {self._transaction_state.value}."
                )
            self._in_flight_button = None
            self._transaction_state = PointerTransactionState.IDLE
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def start_button_up(self, button: MouseButton) -> None:
        """Initiate BUTTON_UP transaction."""
        with self._mutex:
            if self._is_locked:
                raise RuntimeError(f"Pointer is UNRESOLVED_LOCKED (reason: {self._lockout_reason.value}). Actions rejected.")
            if self._transaction_state != PointerTransactionState.BUTTON_HELD_SYNTHETIC:
                raise RuntimeError(
                    f"Cannot start BUTTON_UP from state {self._transaction_state.value}. Must be BUTTON_HELD_SYNTHETIC."
                )
            if button not in self._held_buttons:
                raise RuntimeError(f"Button {button.value} is not in held synthetic button set: {self._held_buttons}")

            self._transaction_state = PointerTransactionState.BUTTON_UP_IN_PROGRESS
            self._in_flight_button = button
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def confirm_button_up(self, button: MouseButton) -> None:
        """Confirm successful native dispatch (M=1) of BUTTON_UP."""
        with self._mutex:
            if self._transaction_state != PointerTransactionState.BUTTON_UP_IN_PROGRESS:
                raise RuntimeError(
                    f"Cannot confirm BUTTON_UP from state {self._transaction_state.value}."
                )
            self._held_buttons.discard(button)
            self._in_flight_button = None
            if len(self._held_buttons) == 0:
                self._transaction_state = PointerTransactionState.IDLE
            else:
                self._transaction_state = PointerTransactionState.BUTTON_HELD_SYNTHETIC
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def fail_button_up_and_lock(self, button: MouseButton, reason: LockoutReason) -> str:
        """Fail BUTTON_UP and transition immediately to UNRESOLVED_LOCKED.

        Generates and returns a unique recovery token.
        """
        with self._mutex:
            self._transaction_state = PointerTransactionState.UNRESOLVED_LOCKED
            self._is_locked = True
            self._lockout_reason = reason
            self._in_flight_button = None
            token = f"rec_ptr_{uuid4().hex[:16]}"
            self._active_recovery_token = token
            self._last_transition_timestamp_ns = time.perf_counter_ns()
            return token

    def start_emergency_sanitization(self) -> None:
        """Initiate emergency sanitization to release held synthetic buttons."""
        with self._mutex:
            if self._is_locked:
                raise RuntimeError(f"Cannot sanitize while UNRESOLVED_LOCKED.")
            self._transaction_state = PointerTransactionState.SANITIZATION_PENDING
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def confirm_emergency_sanitization(self) -> None:
        """Confirm all held synthetic buttons successfully released via native UP dispatches."""
        with self._mutex:
            if self._transaction_state != PointerTransactionState.SANITIZATION_PENDING:
                raise RuntimeError(
                    f"Cannot confirm sanitization from state {self._transaction_state.value}."
                )
            self._held_buttons.clear()
            self._in_flight_button = None
            self._consecutive_sanitizations += 1
            self._transaction_state = PointerTransactionState.SANITIZED_RECOVERED
            # Seamlessly transition SANITIZED_RECOVERED -> IDLE
            self._transaction_state = PointerTransactionState.IDLE
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def fail_emergency_sanitization_and_lock(self, reason: LockoutReason) -> str:
        """Emergency sanitization dispatch failed. Lock out immediately."""
        with self._mutex:
            self._transaction_state = PointerTransactionState.UNRESOLVED_LOCKED
            self._is_locked = True
            self._lockout_reason = reason
            self._in_flight_button = None
            token = f"rec_ptr_{uuid4().hex[:16]}"
            self._active_recovery_token = token
            self._last_transition_timestamp_ns = time.perf_counter_ns()
            return token

    def recover_locked_state(self, recovery_token: str) -> bool:
        """Recover from UNRESOLVED_LOCKED using an explicit administrative recovery token."""
        with self._mutex:
            if not self._is_locked:
                return True
            if not recovery_token or recovery_token != self._active_recovery_token:
                return False

            self._is_locked = False
            self._lockout_reason = LockoutReason.NONE
            self._active_recovery_token = None
            self._held_buttons.clear()
            self._in_flight_button = None
            self._transaction_state = PointerTransactionState.IDLE
            self._last_transition_timestamp_ns = time.perf_counter_ns()
            return True
