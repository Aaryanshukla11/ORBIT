"""
Pointer State Manager for ORBIT Prototype E.
(Phase 2C — Pointer Ownership State Machine & Hard Lockout Engine)

CRITICAL INVARIANTS & SAFETY CONTRACTS:
1. PRIMARY OWNERSHIP INVARIANT:
   $$\\boxed{\\text{ORBIT MUST NEVER LOSE TRACK OF A BUTTON STATE IT SYNTHETICALLY CREATED}}$$
2. SEPARATE OWNERSHIP LAYERS:
   - ORBIT Internal Synthetic State: Tracked exclusively by this state manager.
   - Native Dispatch Result: The User32 SendInput return value (N requested vs M accepted).
   - Observable OS Input State: Polled point-in-time state (e.g., GetAsyncKeyState).
   Never conflate these three distinct layers.
3. FAIL-CLOSED HARD LOCKOUT (UNRESOLVED_LOCKED):
   - If an emergency sanitization dispatch fails, or if a multi-packet dispatch produces
     an indeterminate state, the state machine enters UNRESOLVED_LOCKED.
   - While locked:
     * All future button and click transactions are strictly rejected fail-closed.
     * No background timer or automated routine may silently clear the lock.
     * Cancellation tokens or new action requests cannot bypass the lock.
     * Recovery requires an explicit manual operator confirmation call.
"""

import ctypes
from ctypes import wintypes
import threading
import time
from typing import Optional, Tuple

from app_types import (
    ButtonTransactionState,
    SyntheticButtonState,
    LockoutReason,
    PointerButton,
    PointerStateSnapshot,
)

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04

# User32 for observable state inspection
user32 = ctypes.windll.user32
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT


def query_windows_observable_button_pressed(vkey: int = VK_LBUTTON) -> bool:
    """
    Queries the Windows observable asynchronous keystate for a mouse button.
    
    EPISTEMIC LIMITATION NOTE:
    GetAsyncKeyState returns whether the key/button is physically or logically
    down at the moment of query. It does NOT distinguish between human input
    and synthetic injection, nor does it guarantee absence of user-mode race conditions.
    It is used strictly as an observable diagnostic heuristic.
    """
    state = user32.GetAsyncKeyState(vkey)
    # High bit indicates key/button is currently down
    return bool(state & 0x8000)


class PointerStateManager:
    """
    Authoritative state machine managing synthetic button ownership,
    transaction lifecycles, emergency sanitization status, and hard lockout.
    """
    _instance: Optional["PointerStateManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._mutex = threading.RLock()
        self._transaction_state = ButtonTransactionState.IDLE
        self._left_button_state = SyntheticButtonState.RELEASED
        self._is_locked = False
        self._lockout_reason = LockoutReason.NONE
        self._consecutive_sanitizations = 0
        self._last_transition_timestamp_ns = time.perf_counter_ns()

    @property
    def transaction_state(self) -> ButtonTransactionState:
        with self._mutex:
            return self._transaction_state

    @property
    def left_button_state(self) -> SyntheticButtonState:
        with self._mutex:
            return self._left_button_state

    @property
    def is_locked(self) -> bool:
        with self._mutex:
            return self._is_locked

    @property
    def lockout_reason(self) -> LockoutReason:
        with self._mutex:
            return self._lockout_reason

    def get_snapshot(self) -> PointerStateSnapshot:
        """Returns an immutable point-in-time snapshot of the pointer state machine."""
        with self._mutex:
            return PointerStateSnapshot(
                transaction_state=self._transaction_state,
                left_button_state=self._left_button_state,
                is_locked=self._is_locked,
                lockout_reason=self._lockout_reason,
                consecutive_sanitizations=self._consecutive_sanitizations,
                last_transition_timestamp_ns=self._last_transition_timestamp_ns,
            )

    def can_begin_transaction(self) -> bool:
        """Returns True if the state machine is ready for a new button transaction."""
        with self._mutex:
            return (
                not self._is_locked
                and self._transaction_state in (
                    ButtonTransactionState.IDLE,
                    ButtonTransactionState.SANITIZED_RECOVERED,
                )
            )

    def require_unlocked(self) -> None:
        """Raises RuntimeError if the state machine is in a hard lockout condition."""
        with self._mutex:
            if self._is_locked or self._transaction_state == ButtonTransactionState.UNRESOLVED_LOCKED:
                raise RuntimeError(
                    f"Pointer state is UNRESOLVED_LOCKED (Reason: {self._lockout_reason.value}). "
                    f"All pointer button actions are blocked fail-closed."
                )

    # ------------------------------------------------------------------
    # State Machine Transitions
    # ------------------------------------------------------------------

    def transition_to_down_pending(self) -> None:
        """Transitions IDLE -> DOWN_DISPATCH_PENDING before dispatching LEFTDOWN."""
        with self._mutex:
            self.require_unlocked()
            if self._left_button_state == SyntheticButtonState.PRESSED:
                raise ValueError("Cannot transition to DOWN_DISPATCH_PENDING: button is already PRESSED.")
            self._transaction_state = ButtonTransactionState.DOWN_DISPATCH_PENDING
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def transition_to_button_down(self) -> None:
        """Transitions DOWN_DISPATCH_PENDING -> ORBIT_BUTTON_DOWN upon successful SendInput."""
        with self._mutex:
            self._transaction_state = ButtonTransactionState.ORBIT_BUTTON_DOWN
            self._left_button_state = SyntheticButtonState.PRESSED
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def transition_down_failed_to_idle(self) -> None:
        """Transitions DOWN_DISPATCH_PENDING -> IDLE when DOWN dispatch returned M=0."""
        with self._mutex:
            self._transaction_state = ButtonTransactionState.IDLE
            self._left_button_state = SyntheticButtonState.RELEASED
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def transition_to_up_pending(self) -> None:
        """Transitions ORBIT_BUTTON_DOWN -> UP_DISPATCH_PENDING before dispatching LEFTUP."""
        with self._mutex:
            self.require_unlocked()
            if self._left_button_state != SyntheticButtonState.PRESSED:
                raise ValueError("Cannot transition to UP_DISPATCH_PENDING: button is not in PRESSED state.")
            self._transaction_state = ButtonTransactionState.UP_DISPATCH_PENDING
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def transition_to_idle_after_up(self) -> None:
        """Transitions UP_DISPATCH_PENDING -> IDLE upon successful SendInput LEFTUP."""
        with self._mutex:
            self._transaction_state = ButtonTransactionState.IDLE
            self._left_button_state = SyntheticButtonState.RELEASED
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def transition_to_partial_or_failed(self) -> None:
        """Transitions to PARTIAL_OR_FAILED_DISPATCH when a dispatch anomaly occurs."""
        with self._mutex:
            self._transaction_state = ButtonTransactionState.PARTIAL_OR_FAILED_DISPATCH
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def transition_to_sanitization_pending(self) -> None:
        """Transitions to SANITIZATION_PENDING when initiating an emergency UP dispatch."""
        with self._mutex:
            self._transaction_state = ButtonTransactionState.SANITIZATION_PENDING
            self._consecutive_sanitizations += 1
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def transition_to_sanitized_recovered(self) -> None:
        """Transitions SANITIZATION_PENDING -> SANITIZED_RECOVERED after emergency UP succeeds."""
        with self._mutex:
            self._transaction_state = ButtonTransactionState.SANITIZED_RECOVERED
            self._left_button_state = SyntheticButtonState.RELEASED
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def reset_recovered_to_idle(self) -> None:
        """Resets SANITIZED_RECOVERED -> IDLE."""
        with self._mutex:
            if self._transaction_state == ButtonTransactionState.SANITIZED_RECOVERED:
                self._transaction_state = ButtonTransactionState.IDLE
                self._last_transition_timestamp_ns = time.perf_counter_ns()

    def enter_hard_lockout(self, reason: LockoutReason) -> None:
        """
        Enters UNRESOLVED_LOCKED fail-closed state.
        Blocks all future pointer operations until manual operator recovery.
        """
        with self._mutex:
            self._transaction_state = ButtonTransactionState.UNRESOLVED_LOCKED
            self._is_locked = True
            self._lockout_reason = reason
            self._left_button_state = SyntheticButtonState.INDETERMINATE
            self._last_transition_timestamp_ns = time.perf_counter_ns()

    def request_manual_recovery(self, confirmation_token: str) -> bool:
        """
        Explicit operator recovery procedure to reset an UNRESOLVED_LOCKED state machine.
        Requires exact confirmation token to prevent accidental unlocking.
        """
        EXPECTED_TOKEN = "CONFIRM_OPERATOR_MANUAL_RESET"
        with self._mutex:
            if confirmation_token != EXPECTED_TOKEN:
                return False
            self._is_locked = False
            self._lockout_reason = LockoutReason.NONE
            self._left_button_state = SyntheticButtonState.RELEASED
            self._transaction_state = ButtonTransactionState.IDLE
            self._consecutive_sanitizations = 0
            self._last_transition_timestamp_ns = time.perf_counter_ns()
            return True
