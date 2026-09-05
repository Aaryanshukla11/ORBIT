"""
Safe Single-Button Controller for ORBIT Prototype E.
(Phase 2C — Single-Button State Transactions, Multi-Packet Handling & Emergency Sanitization)

CRITICAL SAFETY & EXECUTION INVARIANTS:
1. PRIMARY OWNERSHIP INVARIANT:
   $$\\boxed{\\text{ORBIT MUST NEVER LOSE TRACK OF A BUTTON STATE IT SYNTHETICALLY CREATED}}$$
2. EXPLICIT NAMED CONSTANTS & SIGNATURE:
   - MOUSEEVENTF_LEFTDOWN = 0x0002
   - MOUSEEVENTF_LEFTUP   = 0x0004
   - dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE (0x50524F544F425F31)
3. SINGLE AUTHORITATIVE DISPATCH GATEWAY:
   All SendInput calls route strictly through NativeDispatchGateway.
   Zero ad-hoc SendInput, SetCursorPos, or mouse_event calls exist elsewhere.
4. FAIL-CLOSED HARD LOCKOUT:
   If an emergency sanitization dispatch fails, or if a partial multi-packet dispatch
   produces an indeterminate state, the state machine enters UNRESOLVED_LOCKED.
   While locked, all future button/click actions are refused fail-closed.
5. NO DESKTOP SWITCHING:
   Zero OpenInputDesktop or SetThreadDesktop calls exist in this production module.
6. CANCEL-SAFE TRANSACTIONS:
   Cancellation checkpoints exist before DOWN, during dwell (between DOWN and UP),
   and after UP. If cancellation occurs while the button is DOWN, an emergency
   synthetic UP sanitization is dispatched immediately.
"""

import ctypes
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app_types import (
    ButtonTransactionState,
    SyntheticButtonState,
    LockoutReason,
    PointerButton,
    ButtonExecutionStatus,
    ClickExecutionStatus,
    ButtonDiagnosticReason,
    ButtonExecutionResult,
    ClickExecutionResult,
    PointerStateSnapshot,
    NativeDispatchResult,
)
from abi_validator import (
    AbiGate,
    INPUT,
    MOUSEINPUT,
    INPUT_MOUSE,
    ORBIT_EXTRA_INFO_SIGNATURE,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
)
from cancellation import CancellationToken
from native_gateway import NativeDispatchGateway
from pointer_state_manager import PointerStateManager, query_windows_observable_button_pressed


class ButtonController:
    """
    Authoritative controller executing safe single-button transactions,
    press-and-release clicks, multi-packet dispatches, and emergency sanitizations.
    """

    def __init__(
        self,
        state_manager: Optional[PointerStateManager] = None,
        native_gateway: Optional[NativeDispatchGateway] = None,
        abi_gate: Optional[AbiGate] = None,
    ):
        self._abi_gate = abi_gate or (native_gateway.abi_gate if native_gateway else AbiGate())
        self._gateway = native_gateway or NativeDispatchGateway(abi_gate=self._abi_gate)
        self._state_mgr = state_manager or PointerStateManager()

    @property
    def state_manager(self) -> PointerStateManager:
        return self._state_mgr

    @property
    def gateway(self) -> NativeDispatchGateway:
        return self._gateway

    @property
    def abi_gate(self) -> AbiGate:
        return self._abi_gate

    # ------------------------------------------------------------------
    # 1. Single Button DOWN Operation
    # ------------------------------------------------------------------

    def execute_button_down(
        self,
        button: PointerButton = PointerButton.LEFT,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ButtonExecutionResult:
        """
        Executes a controlled single LEFTDOWN injection.

        Guarantees:
        1. Pre-dispatch cancellation check.
        2. Pre-dispatch fail-closed hard lockout check.
        3. Double-DOWN rejection if button is already PRESSED.
        4. ABI validation check.
        5. Single-packet (N=1) SendInput via NativeDispatchGateway.
        6. State machine transition to ORBIT_BUTTON_DOWN on success (M=1).
        7. Clean reversion to IDLE on zero dispatch (M=0).
        """
        start_ns = time.perf_counter_ns()

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        if button != PointerButton.LEFT:
            raise NotImplementedError(f"Button {button.value} is outside Phase 2C scope (LEFT only).")

        # Check 1: Cancellation
        if cancellation_token is not None and cancellation_token.is_cancelled:
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.CANCELLED_BEFORE_DISPATCH,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.CANCELLED,
                error_message=f"Action cancelled before DOWN dispatch: {cancellation_token.reason}",
            )

        # Check 2: Lockout
        if self._state_mgr.is_locked:
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.REJECTED_LOCKED,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.STATE_MACHINE_LOCKED,
                error_message=f"State machine is UNRESOLVED_LOCKED (Reason: {self._state_mgr.lockout_reason.value})",
            )

        # Check 3: Current state (Double-DOWN prevention)
        if self._state_mgr.left_button_state == SyntheticButtonState.PRESSED:
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.REJECTED_ALREADY_DOWN,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.ALREADY_IN_REQUESTED_STATE,
                error_message="Synthetic button is already in PRESSED state; duplicate DOWN rejected.",
            )

        # Check 4: ABI Gate
        if not self._abi_gate.is_injection_enabled():
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.ABI_INVALID,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.ABI_MISMATCH,
                error_message=f"Fail-closed ABI gate rejected dispatch: {self._abi_gate.result.error_message}",
            )

        # Transition to DOWN_DISPATCH_PENDING
        self._state_mgr.transition_to_down_pending()

        # Build SendInput packet
        packet = INPUT()
        packet.type = INPUT_MOUSE
        packet.union.mi.dx = 0
        packet.union.mi.dy = 0
        packet.union.mi.mouseData = 0
        packet.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        packet.union.mi.time = 0
        packet.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        dispatch_res: NativeDispatchResult = self._gateway.dispatch_single_packet(packet)
        m = dispatch_res.accepted_packets

        if m == 1:
            self._state_mgr.transition_to_button_down()
            self._abi_gate.action_counter.record_down(1)
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.SUCCESS,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                resulting_state=SyntheticButtonState.PRESSED,
                transaction_state=ButtonTransactionState.ORBIT_BUTTON_DOWN,
                accepted_packets=1,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.NONE,
                error_message=None,
            )
        else:
            self._state_mgr.transition_down_failed_to_idle()
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.DISPATCH_ZERO,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                resulting_state=SyntheticButtonState.RELEASED,
                transaction_state=ButtonTransactionState.IDLE,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.SENDINPUT_FAILED,
                error_message=f"SendInput returned 0 (Win32 LastError: {dispatch_res.win32_last_error})",
            )

    # ------------------------------------------------------------------
    # 2. Single Button UP Operation
    # ------------------------------------------------------------------

    def execute_button_up(
        self,
        button: PointerButton = PointerButton.LEFT,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ButtonExecutionResult:
        """
        Executes a controlled single LEFTUP injection.

        Guarantees:
        1. Pre-dispatch cancellation check.
        2. Pre-dispatch fail-closed hard lockout check.
        3. Redundant-UP rejection if button is already RELEASED.
        4. ABI validation check.
        5. Single-packet (N=1) SendInput via NativeDispatchGateway.
        6. State machine transition to IDLE on success (M=1).
        7. If UP fails (M=0), initiates emergency sanitization.
        8. If sanitization fails, transitions to UNRESOLVED_LOCKED.
        """
        start_ns = time.perf_counter_ns()

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        if button != PointerButton.LEFT:
            raise NotImplementedError(f"Button {button.value} is outside Phase 2C scope (LEFT only).")

        # Check 1: Cancellation
        if cancellation_token is not None and cancellation_token.is_cancelled:
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.CANCELLED_BEFORE_DISPATCH,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.CANCELLED,
                error_message=f"Action cancelled before UP dispatch: {cancellation_token.reason}",
            )

        # Check 2: Lockout
        if self._state_mgr.is_locked:
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.REJECTED_LOCKED,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.STATE_MACHINE_LOCKED,
                error_message=f"State machine is UNRESOLVED_LOCKED (Reason: {self._state_mgr.lockout_reason.value})",
            )

        # Check 3: Current state (Redundant-UP prevention)
        if self._state_mgr.left_button_state == SyntheticButtonState.RELEASED:
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.REJECTED_ALREADY_UP,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.ALREADY_IN_REQUESTED_STATE,
                error_message="Synthetic button is already in RELEASED state; redundant UP rejected.",
            )

        # Check 4: ABI Gate
        if not self._abi_gate.is_injection_enabled():
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.ABI_INVALID,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.ABI_MISMATCH,
                error_message=f"Fail-closed ABI gate rejected dispatch: {self._abi_gate.result.error_message}",
            )

        # Transition to UP_DISPATCH_PENDING
        self._state_mgr.transition_to_up_pending()

        # Build SendInput packet
        packet = INPUT()
        packet.type = INPUT_MOUSE
        packet.union.mi.dx = 0
        packet.union.mi.dy = 0
        packet.union.mi.mouseData = 0
        packet.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
        packet.union.mi.time = 0
        packet.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        dispatch_res: NativeDispatchResult = self._gateway.dispatch_single_packet(packet)
        m = dispatch_res.accepted_packets

        if m == 1:
            self._state_mgr.transition_to_idle_after_up()
            self._abi_gate.action_counter.record_up(1)
            return ButtonExecutionResult(
                status=ButtonExecutionStatus.SUCCESS,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                resulting_state=SyntheticButtonState.RELEASED,
                transaction_state=ButtonTransactionState.IDLE,
                accepted_packets=1,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.NONE,
                error_message=None,
            )
        else:
            # UP dispatch failed while button was down: trigger emergency sanitization
            self._state_mgr.transition_to_partial_or_failed()
            sanitized = self._execute_emergency_sanitization()
            if sanitized:
                return ButtonExecutionResult(
                    status=ButtonExecutionStatus.SANITIZED_AFTER_FAILURE,
                    button=button,
                    target_state=SyntheticButtonState.RELEASED,
                    resulting_state=SyntheticButtonState.RELEASED,
                    transaction_state=ButtonTransactionState.SANITIZED_RECOVERED,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    diagnostic_reason=ButtonDiagnosticReason.SENDINPUT_FAILED,
                    error_message=f"UP dispatch failed (LastError: {dispatch_res.win32_last_error}); emergency sanitization succeeded.",
                )
            else:
                return ButtonExecutionResult(
                    status=ButtonExecutionStatus.UNRESOLVED_LOCKOUT,
                    button=button,
                    target_state=SyntheticButtonState.RELEASED,
                    resulting_state=SyntheticButtonState.INDETERMINATE,
                    transaction_state=ButtonTransactionState.UNRESOLVED_LOCKED,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    diagnostic_reason=ButtonDiagnosticReason.SANITIZATION_FAILED,
                    error_message=f"UP dispatch failed and emergency sanitization failed; entered UNRESOLVED_LOCKED.",
                )

    # ------------------------------------------------------------------
    # 3. Emergency Sanitization Helper
    # ------------------------------------------------------------------

    def _execute_emergency_sanitization(self) -> bool:
        """
        Dispatches a single emergency synthetic LEFTUP packet.
        
        Returns:
            True if emergency UP was accepted (M=1), transitioning to SANITIZED_RECOVERED.
            False if emergency UP failed (M=0), transitioning to UNRESOLVED_LOCKED.
        """
        self._state_mgr.transition_to_sanitization_pending()

        packet = INPUT()
        packet.type = INPUT_MOUSE
        packet.union.mi.dx = 0
        packet.union.mi.dy = 0
        packet.union.mi.mouseData = 0
        packet.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
        packet.union.mi.time = 0
        packet.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        try:
            dispatch_res = self._gateway.dispatch_single_packet(packet)
            if dispatch_res.accepted_packets == 1:
                self._state_mgr.transition_to_sanitized_recovered()
                self._abi_gate.action_counter.record_up(1)
                return True
            else:
                self._state_mgr.enter_hard_lockout(LockoutReason.SANITIZATION_DISPATCH_FAILED)
                return False
        except Exception:
            self._state_mgr.enter_hard_lockout(LockoutReason.DISPATCH_EXCEPTION)
            return False

    def sanitize_synthetic_buttons(self) -> bool:
        """
        Public API for requesting immediate button sanitization.
        Emits synthetic UP if button is currently DOWN or INDETERMINATE.
        """
        if self._state_mgr.is_locked:
            return False
        if self._state_mgr.left_button_state == SyntheticButtonState.PRESSED:
            return self._execute_emergency_sanitization()
        return True

    # ------------------------------------------------------------------
    # 4. Press-and-Release CLICK Transaction
    # ------------------------------------------------------------------

    def execute_click(
        self,
        button: PointerButton = PointerButton.LEFT,
        dwell_ms: float = 0.0,
        use_composite_array: bool = False,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ClickExecutionResult:
        """
        Executes a controlled press-and-release click transaction.

        Supports two execution modes:
        Mode 1 (Sequential, default):
            DOWN -> dwell -> mid-cancellation checkpoint -> UP.
            Provides granular timing and cooperative preemption between phases.
        Mode 2 (Composite Array, use_composite_array=True):
            Dispatches [LEFTDOWN, LEFTUP] in a single SendInput(N=2) call.
            Handles partial dispatch (M=1) with immediate sanitization.
        """
        start_ns = time.perf_counter_ns()

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        if button != PointerButton.LEFT:
            raise NotImplementedError(f"Button {button.value} is outside Phase 2C scope (LEFT only).")

        # Check 1: Initial Cancellation
        if cancellation_token is not None and cancellation_token.is_cancelled:
            return ClickExecutionResult(
                status=ClickExecutionStatus.CANCELLED_BEFORE_DOWN,
                button=button,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                dwell_ms=dwell_ms,
                total_accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.CANCELLED,
                error_message=f"Click cancelled before DOWN: {cancellation_token.reason}",
            )

        # Check 2: Lockout
        if self._state_mgr.is_locked:
            return ClickExecutionResult(
                status=ClickExecutionStatus.REJECTED_LOCKED,
                button=button,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                dwell_ms=dwell_ms,
                total_accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.STATE_MACHINE_LOCKED,
                error_message=f"State machine is UNRESOLVED_LOCKED (Reason: {self._state_mgr.lockout_reason.value})",
            )

        # Check 3: ABI Gate
        if not self._abi_gate.is_injection_enabled():
            return ClickExecutionResult(
                status=ClickExecutionStatus.ABI_INVALID,
                button=button,
                resulting_state=self._state_mgr.left_button_state,
                transaction_state=self._state_mgr.transaction_state,
                dwell_ms=dwell_ms,
                total_accepted_packets=0,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.ABI_MISMATCH,
                error_message=f"ABI gate rejected click: {self._abi_gate.result.error_message}",
            )

        # --------------------------------------------------------------
        # MODE 2: Composite Array Dispatch (N = 2)
        # --------------------------------------------------------------
        if use_composite_array:
            self._state_mgr.transition_to_down_pending()

            p_down = INPUT()
            p_down.type = INPUT_MOUSE
            p_down.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
            p_down.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

            p_up = INPUT()
            p_up.type = INPUT_MOUSE
            p_up.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
            p_up.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

            dispatch_res = self._gateway.dispatch_packet_array([p_down, p_up])
            m = dispatch_res.accepted_packets

            if m == 2:
                # Both accepted atomically
                self._state_mgr.transition_to_button_down()
                self._state_mgr.transition_to_up_pending()
                self._state_mgr.transition_to_idle_after_up()
                self._abi_gate.action_counter.record_down(1)
                self._abi_gate.action_counter.record_up(1)
                return ClickExecutionResult(
                    status=ClickExecutionStatus.SUCCESS,
                    button=button,
                    resulting_state=SyntheticButtonState.RELEASED,
                    transaction_state=ButtonTransactionState.IDLE,
                    dwell_ms=dwell_ms,
                    total_accepted_packets=2,
                    duration_us=elapsed_us(),
                    diagnostic_reason=ButtonDiagnosticReason.NONE,
                    error_message=None,
                )
            elif m == 1:
                # Partial dispatch: DOWN accepted, UP failed!
                self._state_mgr.transition_to_button_down()
                self._abi_gate.action_counter.record_down(1)
                self._state_mgr.transition_to_partial_or_failed()

                sanitized = self._execute_emergency_sanitization()
                if sanitized:
                    return ClickExecutionResult(
                        status=ClickExecutionStatus.PARTIAL_DISPATCH_SANITIZED,
                        button=button,
                        resulting_state=SyntheticButtonState.RELEASED,
                        transaction_state=ButtonTransactionState.SANITIZED_RECOVERED,
                        dwell_ms=dwell_ms,
                        total_accepted_packets=1,
                        duration_us=elapsed_us(),
                        diagnostic_reason=ButtonDiagnosticReason.PARTIAL_DISPATCH,
                        error_message="Partial dispatch (M=1/N=2: DOWN accepted, UP failed); emergency sanitization recovered.",
                    )
                else:
                    return ClickExecutionResult(
                        status=ClickExecutionStatus.PARTIAL_DISPATCH_LOCKED,
                        button=button,
                        resulting_state=SyntheticButtonState.INDETERMINATE,
                        transaction_state=ButtonTransactionState.UNRESOLVED_LOCKED,
                        dwell_ms=dwell_ms,
                        total_accepted_packets=1,
                        duration_us=elapsed_us(),
                        diagnostic_reason=ButtonDiagnosticReason.SANITIZATION_FAILED,
                        error_message="Partial dispatch (M=1/N=2); emergency sanitization failed; entered UNRESOLVED_LOCKED.",
                    )
            else:
                # m == 0
                self._state_mgr.transition_down_failed_to_idle()
                return ClickExecutionResult(
                    status=ClickExecutionStatus.DOWN_FAILED,
                    button=button,
                    resulting_state=SyntheticButtonState.RELEASED,
                    transaction_state=ButtonTransactionState.IDLE,
                    dwell_ms=dwell_ms,
                    total_accepted_packets=0,
                    duration_us=elapsed_us(),
                    diagnostic_reason=ButtonDiagnosticReason.SENDINPUT_FAILED,
                    error_message=f"SendInput composite array returned M=0 (LastError: {dispatch_res.win32_last_error})",
                )

        # --------------------------------------------------------------
        # MODE 1: Sequential Controlled Click (DOWN -> dwell -> UP)
        # --------------------------------------------------------------
        # Step 1: Execute DOWN
        down_res = self.execute_button_down(button=button, cancellation_token=cancellation_token)
        if down_res.status != ButtonExecutionStatus.SUCCESS:
            return ClickExecutionResult(
                status=ClickExecutionStatus.DOWN_FAILED,
                button=button,
                resulting_state=down_res.resulting_state,
                transaction_state=down_res.transaction_state,
                dwell_ms=dwell_ms,
                total_accepted_packets=down_res.accepted_packets,
                duration_us=elapsed_us(),
                diagnostic_reason=down_res.diagnostic_reason,
                error_message=f"Click failed during DOWN phase: {down_res.error_message}",
            )

        # Step 2: Dwell
        if dwell_ms > 0:
            time.sleep(dwell_ms / 1000.0)

        # Step 3: Check cancellation between DOWN and UP
        if cancellation_token is not None and cancellation_token.is_cancelled:
            # Emergency sanitization required because button is currently DOWN
            sanitized = self._execute_emergency_sanitization()
            return ClickExecutionResult(
                status=ClickExecutionStatus.CANCELLED_BEFORE_UP,
                button=button,
                resulting_state=SyntheticButtonState.RELEASED if sanitized else SyntheticButtonState.INDETERMINATE,
                transaction_state=self._state_mgr.transaction_state,
                dwell_ms=dwell_ms,
                total_accepted_packets=1,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.CANCELLED,
                error_message=f"Click cancelled during dwell after DOWN; sanitization {'succeeded' if sanitized else 'FAILED'}.",
            )

        # Step 4: Execute UP
        up_res = self.execute_button_up(button=button, cancellation_token=cancellation_token)
        total_packets = down_res.accepted_packets + up_res.accepted_packets

        if up_res.status == ButtonExecutionStatus.SUCCESS:
            return ClickExecutionResult(
                status=ClickExecutionStatus.SUCCESS,
                button=button,
                resulting_state=SyntheticButtonState.RELEASED,
                transaction_state=ButtonTransactionState.IDLE,
                dwell_ms=dwell_ms,
                total_accepted_packets=total_packets,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.NONE,
                error_message=None,
            )
        elif up_res.status == ButtonExecutionStatus.SANITIZED_AFTER_FAILURE:
            return ClickExecutionResult(
                status=ClickExecutionStatus.UP_FAILED_SANITIZED,
                button=button,
                resulting_state=SyntheticButtonState.RELEASED,
                transaction_state=ButtonTransactionState.SANITIZED_RECOVERED,
                dwell_ms=dwell_ms,
                total_accepted_packets=down_res.accepted_packets,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.SENDINPUT_FAILED,
                error_message=f"UP dispatch failed during click; emergency sanitization recovered.",
            )
        else:
            return ClickExecutionResult(
                status=ClickExecutionStatus.UP_FAILED_LOCKED,
                button=button,
                resulting_state=SyntheticButtonState.INDETERMINATE,
                transaction_state=ButtonTransactionState.UNRESOLVED_LOCKED,
                dwell_ms=dwell_ms,
                total_accepted_packets=down_res.accepted_packets,
                duration_us=elapsed_us(),
                diagnostic_reason=ButtonDiagnosticReason.SANITIZATION_FAILED,
                error_message=f"UP dispatch and sanitization failed during click; entered UNRESOLVED_LOCKED.",
            )
