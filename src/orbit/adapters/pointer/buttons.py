"""Button transaction executor, atomic click pipeline, and emergency sanitization for ORBIT M1.2B."""

from __future__ import annotations

import ctypes
from datetime import datetime, timezone
from enum import Enum
import sys
import time
from typing import Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.adapters.pointer.health import ActionCounter
from orbit.adapters.pointer.movement import NativeDispatchGateway
from orbit.adapters.pointer.safety import (
    INPUT,
    INPUT_MOUSE,
    MOUSEINPUT,
    ORBIT_EXTRA_INFO_SIGNATURE,
    AbiGate,
    MouseButton,
    get_button_down_flag,
    get_button_up_flag,
    query_windows_observable_button_pressed,
)
from orbit.adapters.pointer.state import (
    LockoutReason,
    PointerStateManager,
    PointerStateSnapshot,
    PointerTransactionState,
    SyntheticButtonState,
)
from orbit.runtime.cancellation import CancellationToken


class ButtonExecutionStatus(str, Enum):
    """Classification of single button execution outcomes."""

    REQUEST_ACCEPTED = "REQUEST_ACCEPTED"
    BUTTON_DOWN_ACCEPTED = "BUTTON_DOWN_ACCEPTED"
    BUTTON_UP_ACCEPTED = "BUTTON_UP_ACCEPTED"
    DISPATCH_ZERO = "DISPATCH_ZERO"
    DISPATCH_ZERO_LOCKED = "DISPATCH_ZERO_LOCKED"
    REJECTED_ALREADY_HELD = "REJECTED_ALREADY_HELD"
    REJECTED_NOT_HELD = "REJECTED_NOT_HELD"
    REJECTED_UNRESOLVED_LOCKED = "REJECTED_UNRESOLVED_LOCKED"
    REJECTED_ABI_INVALID = "REJECTED_ABI_INVALID"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    CANCELLED_AFTER_DISPATCH = "CANCELLED_AFTER_DISPATCH"


class ClickExecutionStatus(str, Enum):
    """Classification of atomic click transaction outcomes."""

    CLICK_VERIFIED = "CLICK_VERIFIED"
    DOWN_DISPATCH_FAILED = "DOWN_DISPATCH_FAILED"
    UP_DISPATCH_FAILED_LOCKED = "UP_DISPATCH_FAILED_LOCKED"
    CANCELLED_BEFORE_DOWN = "CANCELLED_BEFORE_DOWN"
    CANCELLED_DURING_DWELL_SANITIZED = "CANCELLED_DURING_DWELL_SANITIZED"
    CANCELLED_DURING_DWELL_SANITIZATION_FAILED_LOCKED = "CANCELLED_DURING_DWELL_SANITIZATION_FAILED_LOCKED"
    REJECTED_UNRESOLVED_LOCKED = "REJECTED_UNRESOLVED_LOCKED"
    REJECTED_ABI_INVALID = "REJECTED_ABI_INVALID"


class ButtonTransactionResult(BaseModel):
    """Result payload for single button operations."""

    request_id: str = Field(default_factory=lambda: f"btn_{uuid4().hex[:12]}")
    status: ButtonExecutionStatus
    button: MouseButton
    target_state: SyntheticButtonState
    accepted_packets: int = 0
    win32_last_error: int = 0
    duration_us: float = 0.0
    is_observable_down: bool = False
    is_locked: bool = False
    lockout_reason: LockoutReason = LockoutReason.NONE
    recovery_token: Optional[str] = None
    state_snapshot: Optional[Dict] = None


class ClickTransactionResult(BaseModel):
    """Result payload for atomic click operations."""

    request_id: str = Field(default_factory=lambda: f"clk_{uuid4().hex[:12]}")
    status: ClickExecutionStatus
    button: MouseButton
    dwell_ms: float
    down_result: Optional[ButtonTransactionResult] = None
    up_result: Optional[ButtonTransactionResult] = None
    sanitization_result: Optional[Dict] = None
    total_duration_ms: float = 0.0
    is_locked: bool = False
    lockout_reason: LockoutReason = LockoutReason.NONE
    recovery_token: Optional[str] = None


class SanitizationResult(BaseModel):
    """Result payload for emergency sanitization."""

    success: bool
    released_buttons: List[MouseButton] = Field(default_factory=list)
    failed_buttons: List[MouseButton] = Field(default_factory=list)
    is_locked: bool = False
    lockout_reason: LockoutReason = LockoutReason.NONE
    recovery_token: Optional[str] = None
    duration_us: float = 0.0


class ButtonTransactionExecutor:
    """Authoritative executor for mouse button operations and atomic clicks."""

    def __init__(
        self,
        native_gateway: NativeDispatchGateway,
        state_manager: PointerStateManager,
        abi_gate: AbiGate,
        action_counter: ActionCounter,
    ) -> None:
        self.gateway = native_gateway
        self.state_mgr = state_manager
        self.abi_gate = abi_gate
        self.action_counter = action_counter

    def execute_button_down(
        self,
        button: MouseButton = MouseButton.LEFT,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ButtonTransactionResult:
        """Execute a controlled single BUTTON_DOWN operation."""
        start_ns = time.perf_counter_ns()

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        # Check 1: ABI validation
        if not self.abi_gate.is_abi_valid():
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.REJECTED_ABI_INVALID,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                duration_us=elapsed_us(),
                is_locked=self.state_mgr.is_locked,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        # Check 2: Hard lockout
        if self.state_mgr.is_locked:
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.REJECTED_UNRESOLVED_LOCKED,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                duration_us=elapsed_us(),
                is_locked=True,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        # Check 3: Cooperative cancellation before dispatch
        if cancellation_token is not None and cancellation_token.is_cancelled:
            self.action_counter.record_cancellation(before_dispatch=True)
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.CANCELLED_BEFORE_DISPATCH,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                duration_us=elapsed_us(),
                is_locked=False,
            )

        # Check 4: State machine initiation
        try:
            self.state_mgr.start_button_down(button)
        except RuntimeError as ex:
            if "already synthetically HELD" in str(ex):
                return ButtonTransactionResult(
                    status=ButtonExecutionStatus.REJECTED_ALREADY_HELD,
                    button=button,
                    target_state=SyntheticButtonState.PRESSED,
                    duration_us=elapsed_us(),
                )
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.REJECTED_UNRESOLVED_LOCKED if self.state_mgr.is_locked else ButtonExecutionStatus.DISPATCH_ZERO,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                duration_us=elapsed_us(),
                is_locked=self.state_mgr.is_locked,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        # Build native INPUT packet
        flag = get_button_down_flag(button)
        mi = MOUSEINPUT(
            dx=0,
            dy=0,
            mouseData=0,
            dwFlags=flag,
            time=0,
            dwExtraInfo=ORBIT_EXTRA_INFO_SIGNATURE,
        )
        packet = INPUT(type=INPUT_MOUSE, mi=mi)

        # Checkpoint: Immediate pre-dispatch cancellation
        if cancellation_token is not None and cancellation_token.is_cancelled:
            self.state_mgr.abort_button_down(button)
            self.action_counter.record_cancellation(before_dispatch=True)
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.CANCELLED_BEFORE_DISPATCH,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                duration_us=elapsed_us(),
            )

        # Native dispatch via authoritative gateway
        accepted, win32_err, disp_dur_us = self.gateway.dispatch_single_packet(packet)

        if accepted == 1:
            self.state_mgr.confirm_button_down(button)
            is_obs = query_windows_observable_button_pressed(button)
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.BUTTON_DOWN_ACCEPTED,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                accepted_packets=1,
                win32_last_error=0,
                duration_us=elapsed_us(),
                is_observable_down=is_obs,
                is_locked=False,
            )
        else:
            self.state_mgr.abort_button_down(button)
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.DISPATCH_ZERO,
                button=button,
                target_state=SyntheticButtonState.PRESSED,
                accepted_packets=0,
                win32_last_error=win32_err,
                duration_us=elapsed_us(),
                is_locked=False,
            )

    def execute_button_up(
        self,
        button: MouseButton = MouseButton.LEFT,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ButtonTransactionResult:
        """Execute a controlled single BUTTON_UP operation."""
        start_ns = time.perf_counter_ns()

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        if not self.abi_gate.is_abi_valid():
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.REJECTED_ABI_INVALID,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                duration_us=elapsed_us(),
                is_locked=self.state_mgr.is_locked,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        if self.state_mgr.is_locked:
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.REJECTED_UNRESOLVED_LOCKED,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                duration_us=elapsed_us(),
                is_locked=True,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        try:
            self.state_mgr.start_button_up(button)
        except RuntimeError as ex:
            if "not in held synthetic button set" in str(ex):
                return ButtonTransactionResult(
                    status=ButtonExecutionStatus.REJECTED_NOT_HELD,
                    button=button,
                    target_state=SyntheticButtonState.RELEASED,
                    duration_us=elapsed_us(),
                )
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.REJECTED_UNRESOLVED_LOCKED if self.state_mgr.is_locked else ButtonExecutionStatus.DISPATCH_ZERO,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                duration_us=elapsed_us(),
                is_locked=self.state_mgr.is_locked,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        # Build native INPUT packet
        flag = get_button_up_flag(button)
        mi = MOUSEINPUT(
            dx=0,
            dy=0,
            mouseData=0,
            dwFlags=flag,
            time=0,
            dwExtraInfo=ORBIT_EXTRA_INFO_SIGNATURE,
        )
        packet = INPUT(type=INPUT_MOUSE, mi=mi)

        accepted, win32_err, disp_dur_us = self.gateway.dispatch_single_packet(packet)

        if accepted == 1:
            self.state_mgr.confirm_button_up(button)
            is_obs = query_windows_observable_button_pressed(button)
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.BUTTON_UP_ACCEPTED,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                accepted_packets=1,
                win32_last_error=0,
                duration_us=elapsed_us(),
                is_observable_down=is_obs,
                is_locked=False,
            )
        else:
            token = self.state_mgr.fail_button_up_and_lock(button, LockoutReason.BUTTON_UP_DISPATCH_FAILED)
            return ButtonTransactionResult(
                status=ButtonExecutionStatus.DISPATCH_ZERO_LOCKED,
                button=button,
                target_state=SyntheticButtonState.RELEASED,
                accepted_packets=0,
                win32_last_error=win32_err,
                duration_us=elapsed_us(),
                is_locked=True,
                lockout_reason=LockoutReason.BUTTON_UP_DISPATCH_FAILED,
                recovery_token=token,
            )

    def execute_click(
        self,
        button: MouseButton = MouseButton.LEFT,
        dwell_ms: float = 50.0,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ClickTransactionResult:
        """Execute an atomic controlled click transaction (DOWN -> dwell -> UP)."""
        t0 = time.perf_counter()

        def elapsed_ms() -> float:
            return (time.perf_counter() - t0) * 1000.0

        # Step 1: Pre-dispatch checks
        if not self.abi_gate.is_abi_valid():
            return ClickTransactionResult(
                status=ClickExecutionStatus.REJECTED_ABI_INVALID,
                button=button,
                dwell_ms=dwell_ms,
                total_duration_ms=elapsed_ms(),
                is_locked=self.state_mgr.is_locked,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        if self.state_mgr.is_locked:
            return ClickTransactionResult(
                status=ClickExecutionStatus.REJECTED_UNRESOLVED_LOCKED,
                button=button,
                dwell_ms=dwell_ms,
                total_duration_ms=elapsed_ms(),
                is_locked=True,
                lockout_reason=self.state_mgr.lockout_reason,
            )

        if cancellation_token is not None and cancellation_token.is_cancelled:
            return ClickTransactionResult(
                status=ClickExecutionStatus.CANCELLED_BEFORE_DOWN,
                button=button,
                dwell_ms=dwell_ms,
                total_duration_ms=elapsed_ms(),
            )

        # Step 2: Execute DOWN
        down_res = self.execute_button_down(button, cancellation_token)
        if down_res.status != ButtonExecutionStatus.BUTTON_DOWN_ACCEPTED:
            return ClickTransactionResult(
                status=ClickExecutionStatus.DOWN_DISPATCH_FAILED,
                button=button,
                dwell_ms=dwell_ms,
                down_result=down_res,
                total_duration_ms=elapsed_ms(),
                is_locked=down_res.is_locked,
                lockout_reason=down_res.lockout_reason,
            )

        # Step 3: Controlled dwell with cooperative cancellation watch
        dwell_s = max(0.001, dwell_ms / 1000.0)
        dwell_start = time.perf_counter()
        cancelled_during_dwell = False

        while (time.perf_counter() - dwell_start) < dwell_s:
            if cancellation_token is not None and cancellation_token.is_cancelled:
                cancelled_during_dwell = True
                break
            time.sleep(0.001)

        # Step 4: Handle cancellation during dwell with emergency sanitization
        if cancelled_during_dwell:
            san_res = self.emergency_sanitize(cancellation_token=None)
            if san_res.success:
                return ClickTransactionResult(
                    status=ClickExecutionStatus.CANCELLED_DURING_DWELL_SANITIZED,
                    button=button,
                    dwell_ms=dwell_ms,
                    down_result=down_res,
                    sanitization_result=san_res.model_dump(),
                    total_duration_ms=elapsed_ms(),
                    is_locked=False,
                )
            else:
                return ClickTransactionResult(
                    status=ClickExecutionStatus.CANCELLED_DURING_DWELL_SANITIZATION_FAILED_LOCKED,
                    button=button,
                    dwell_ms=dwell_ms,
                    down_result=down_res,
                    sanitization_result=san_res.model_dump(),
                    total_duration_ms=elapsed_ms(),
                    is_locked=True,
                    lockout_reason=san_res.lockout_reason,
                    recovery_token=san_res.recovery_token,
                )

        # Step 5: Execute UP
        up_res = self.execute_button_up(button, cancellation_token=None)
        if up_res.status != ButtonExecutionStatus.BUTTON_UP_ACCEPTED:
            return ClickTransactionResult(
                status=ClickExecutionStatus.UP_DISPATCH_FAILED_LOCKED,
                button=button,
                dwell_ms=dwell_ms,
                down_result=down_res,
                up_result=up_res,
                total_duration_ms=elapsed_ms(),
                is_locked=True,
                lockout_reason=up_res.lockout_reason,
                recovery_token=up_res.recovery_token,
            )

        return ClickTransactionResult(
            status=ClickExecutionStatus.CLICK_VERIFIED,
            button=button,
            dwell_ms=dwell_ms,
            down_result=down_res,
            up_result=up_res,
            total_duration_ms=elapsed_ms(),
            is_locked=False,
        )

    def emergency_sanitize(
        self,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> SanitizationResult:
        """Release all held synthetic buttons fail-closed."""
        start_ns = time.perf_counter_ns()

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        held = list(self.state_mgr.held_buttons)
        if len(held) == 0:
            return SanitizationResult(
                success=True,
                released_buttons=[],
                duration_us=elapsed_us(),
            )

        try:
            self.state_mgr.start_emergency_sanitization()
        except RuntimeError:
            if self.state_mgr.is_locked:
                return SanitizationResult(
                    success=False,
                    is_locked=True,
                    lockout_reason=self.state_mgr.lockout_reason,
                    duration_us=elapsed_us(),
                )

        released = []
        failed = []

        for btn in held:
            flag = get_button_up_flag(btn)
            mi = MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=flag,
                time=0,
                dwExtraInfo=ORBIT_EXTRA_INFO_SIGNATURE,
            )
            packet = INPUT(type=INPUT_MOUSE, mi=mi)
            accepted, _, _ = self.gateway.dispatch_single_packet(packet)
            if accepted == 1:
                released.append(btn)
            else:
                failed.append(btn)

        if len(failed) == 0:
            self.state_mgr.confirm_emergency_sanitization()
            return SanitizationResult(
                success=True,
                released_buttons=released,
                duration_us=elapsed_us(),
            )
        else:
            token = self.state_mgr.fail_emergency_sanitization_and_lock(LockoutReason.SANITIZATION_DISPATCH_FAILED)
            return SanitizationResult(
                success=False,
                released_buttons=released,
                failed_buttons=failed,
                is_locked=True,
                lockout_reason=LockoutReason.SANITIZATION_DISPATCH_FAILED,
                recovery_token=token,
                duration_us=elapsed_us(),
            )
