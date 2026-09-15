"""
Read-Only Target Validation Engine for ORBIT Prototype E.
(Pre-Action & Immediate Pre-Dispatch Verification Gate)

CRITICAL ARCHITECTURAL REALITY:
========================================================================
VALIDATION DOES NOT MAKE DISPATCH ATOMIC.
Pre-dispatch validation verifies target state at time T_check.
A microsecond context switch race (~5-20 μs) between T_check and T_dispatch
is mathematically unavoidable in user-mode Windows User32.
Validation reduces the race window from hundreds of milliseconds to microseconds,
and post-action verification detects residual anomalies.
========================================================================

NO SendInput or pointer injection is performed in this module.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Optional, Tuple

from app_types import (
    Rect,
    ValidatedPointerTarget,
    PointerValidationResult,
    TargetValidationStatus,
    ValidationFailureReason,
)
from cancellation import CancellationToken
from coordinate_mapper import get_virtual_desktop_metrics

user32 = ctypes.windll.user32

# Setup Win32 signatures
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL


def _is_hwnd_or_ancestor(target_hwnd: int, query_hwnd: int) -> bool:
    """Checks if query_hwnd is target_hwnd or an ancestor/child in the window tree."""
    if target_hwnd == query_hwnd:
        return True
    if query_hwnd == 0:
        return False
    # Check if target_hwnd is ancestor of query_hwnd
    current = query_hwnd
    while current != 0:
        if current == target_hwnd:
            return True
        parent = user32.GetParent(current)
        if parent == 0 or parent == current:
            break
        current = parent
    return False


def validate_target(
    target: ValidatedPointerTarget,
    current_generation_id: int,
    cancellation_token: Optional[CancellationToken] = None,
    require_foreground: Optional[bool] = None,
    current_time_ns: Optional[int] = None,
) -> PointerValidationResult:
    """
    Executes a synchronous, multi-point read-only validation check against a target.

    Verification gates executed:
    1. Cancellation check (preempts immediately if cancelled)
    2. Snapshot TTL expiry check
    3. Desktop generation parity check
    4. HWND existence check (IsWindow)
    5. PID identity check (GetWindowThreadProcessId)
    6. Window minimized check (IsIconic)
    7. Foreground exclusivity check (GetForegroundWindow)
    8. Coordinate containment check
    9. Virtual desktop boundary containment check

    Returns:
        PointerValidationResult with explicit diagnostic failure reason.
    """
    start_ns = time.perf_counter_ns()
    now_ns = current_time_ns if current_time_ns is not None else start_ns

    # Gate 1: Cancellation Token Check
    if cancellation_token and cancellation_token.is_cancelled:
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.ACTION_CANCELLED,
            diagnostic_message=f"Action cancelled before execution: {cancellation_token.reason}",
            validation_duration_us=elapsed_us,
        )

    # Gate 2: Snapshot TTL Expiry Check
    age_ms = (now_ns - target.source_snapshot_timestamp_ns) / 1_000_000.0
    if age_ms > target.validity_ttl_ms:
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.SNAPSHOT_TTL_EXPIRED,
            diagnostic_message=f"Snapshot age {age_ms:.2f}ms exceeds maximum TTL {target.validity_ttl_ms:.2f}ms",
            validation_duration_us=elapsed_us,
        )

    # Gate 3: Desktop Generation Parity Check
    if current_generation_id != target.source_generation_id:
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.GENERATION_MISMATCH,
            diagnostic_message=(
                f"Desktop generation changed from {target.source_generation_id} "
                f"to {current_generation_id}."
            ),
            validation_duration_us=elapsed_us,
        )

    # Gate 4: HWND Existence Check (V1)
    if not user32.IsWindow(target.native_hwnd):
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.HWND_DESTROYED,
            diagnostic_message=f"Target window HWND {target.native_hwnd} is no longer a valid Win32 window.",
            validation_duration_us=elapsed_us,
        )

    # Gate 5: PID Identity Check (V2 - Guards against HWND recycling)
    live_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(target.native_hwnd, ctypes.byref(live_pid))
    if live_pid.value != target.process_id:
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.PID_MISMATCH,
            diagnostic_message=(
                f"Target HWND {target.native_hwnd} PID changed from "
                f"{target.process_id} to {live_pid.value} (recycled handle detected)."
            ),
            validation_duration_us=elapsed_us,
        )

    # Gate 6: Window Minimized Check (V4)
    if user32.IsIconic(target.native_hwnd):
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.WINDOW_IS_MINIMIZED,
            diagnostic_message=f"Target window HWND {target.native_hwnd} is currently minimized.",
            validation_duration_us=elapsed_us,
        )

    # Gate 7: Foreground Exclusivity Check (V3)
    must_be_foreground = (
        require_foreground
        if require_foreground is not None
        else target.require_foreground
    )
    if must_be_foreground:
        fg_hwnd = user32.GetForegroundWindow()
        if not _is_hwnd_or_ancestor(target.native_hwnd, fg_hwnd):
            elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
            return PointerValidationResult(
                is_valid=False,
                status=TargetValidationStatus.REJECTED,
                failure_reason=ValidationFailureReason.FOREGROUND_LOST,
                diagnostic_message=(
                    f"Target window HWND {target.native_hwnd} is not foreground. "
                    f"Current foreground window is HWND {fg_hwnd}."
                ),
                validation_duration_us=elapsed_us,
            )

    # Gate 8: Coordinate Containment Check (V7)
    click_x, click_y = target.click_point
    if not target.expected_bounds.contains_point(click_x, click_y):
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.COORDINATE_OUT_OF_BOUNDS,
            diagnostic_message=(
                f"Click point ({click_x}, {click_y}) is outside target expected bounds "
                f"{target.expected_bounds.as_tuple()}."
            ),
            validation_duration_us=elapsed_us,
        )

    # Gate 9: Virtual Desktop Bounding Box Check
    vmetrics = get_virtual_desktop_metrics()
    if not vmetrics.contains_point(click_x, click_y):
        elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
        return PointerValidationResult(
            is_valid=False,
            status=TargetValidationStatus.REJECTED,
            failure_reason=ValidationFailureReason.COORDINATE_OUT_OF_BOUNDS,
            diagnostic_message=(
                f"Click point ({click_x}, {click_y}) is outside live virtual desktop bounds "
                f"[{vmetrics.x_origin}..{vmetrics.right}), [{vmetrics.y_origin}..{vmetrics.bottom})."
            ),
            metrics_snapshot=vmetrics,
            validation_duration_us=elapsed_us,
        )

    # All validation gates passed
    elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0
    return PointerValidationResult(
        is_valid=True,
        status=TargetValidationStatus.VALID,
        failure_reason=ValidationFailureReason.NONE,
        diagnostic_message=None,
        metrics_snapshot=vmetrics,
        validation_duration_us=elapsed_us,
    )
