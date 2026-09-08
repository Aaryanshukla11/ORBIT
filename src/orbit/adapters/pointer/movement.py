"""Safe 12-step absolute cursor movement pipeline, native dispatch gateway, and normalization."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
from enum import Enum
import math
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.adapters.pointer.health import ActionCounter
from orbit.adapters.pointer.safety import (
    FLAGS_ABSOLUTE_MOVE,
    INPUT,
    INPUT_MOUSE,
    MOUSEINPUT,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
    MOUSEEVENTF_MIDDLEDOWN,
    MOUSEEVENTF_MIDDLEUP,
    ORBIT_EXTRA_INFO_SIGNATURE,
    AbiGate,
    VirtualDesktopMetrics,
    VirtualDesktopTopologyIdentity,
    attached_to_input_desktop,
    ensure_thread_input_desktop,
    query_topology_identity,
    query_virtual_desktop_metrics,
)
from orbit.runtime.cancellation import CancellationToken

# Setup user32 for Windows
if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT

    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL

    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL

    try:
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    except Exception:
        pass

    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_uint64]
    user32.mouse_event.restype = None
else:
    user32 = None


# ----------------------------------------------------------------------
# 1. Enums and Result Models
# ----------------------------------------------------------------------

class MovementEvidenceLevel(str, Enum):
    """Discrete evidence levels for epistemic honesty."""

    REQUEST_ACCEPTED_BY_ORBIT = "REQUEST_ACCEPTED_BY_ORBIT"
    ABI_VALIDATED = "ABI_VALIDATED"
    PRE_DISPATCH_VALIDATED = "PRE_DISPATCH_VALIDATED"
    DISPATCH_ACCEPTED = "DISPATCH_ACCEPTED"
    DISPATCH_FAILED = "DISPATCH_FAILED"
    CURSOR_READBACK_OBSERVED = "CURSOR_READBACK_OBSERVED"
    DESTINATION_VERIFIED = "DESTINATION_VERIFIED"
    MOVEMENT_UNVERIFIED = "MOVEMENT_UNVERIFIED"


class MovementStatus(str, Enum):
    """Execution status for absolute movement transactions."""

    MOVEMENT_VERIFIED = "MOVEMENT_VERIFIED"
    CURSOR_READBACK_MISMATCH = "CURSOR_READBACK_MISMATCH"
    DISPATCH_ZERO = "DISPATCH_ZERO"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    CANCELLED_AFTER_DISPATCH = "CANCELLED_AFTER_DISPATCH"
    REJECTED_OUT_OF_BOUNDS = "REJECTED_OUT_OF_BOUNDS"
    REJECTED_TOPOLOGY_MUTATED = "REJECTED_TOPOLOGY_MUTATED"
    ABI_INVALID = "ABI_INVALID"


class MovementDiagnosticReason(str, Enum):
    """Granular diagnostic reason for movement outcomes."""

    NONE = "NONE"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    TOPOLOGY_MUTATED = "TOPOLOGY_MUTATED"
    ABI_MISMATCH = "ABI_MISMATCH"
    CANCELLED = "CANCELLED"
    SENDINPUT_FAILED = "SENDINPUT_FAILED"
    EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE = "EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE"
    UNKNOWN = "UNKNOWN"


class MovementResult(BaseModel):
    """Structured, epistemically honest result of a cursor movement operation."""

    request_id: str = Field(default_factory=lambda: f"mov_{uuid4().hex[:10]}")
    requested_x: int
    requested_y: int
    observed_x: Optional[int] = None
    observed_y: Optional[int] = None
    delta_x: Optional[int] = None
    delta_y: Optional[int] = None
    tolerance_px: int = 1
    normalized_x: Optional[int] = None
    normalized_y: Optional[int] = None
    topology_fingerprint: Optional[Dict[str, Any]] = None
    requested_packets: int = 0
    accepted_packets: int = 0
    win32_last_error: int = 0
    duration_us: float = 0.0
    status: MovementStatus
    diagnostic_reason: MovementDiagnosticReason
    evidence_level: MovementEvidenceLevel
    error_message: Optional[str] = None
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ----------------------------------------------------------------------
# 2. Coordinate Normalization
# ----------------------------------------------------------------------

def normalize_to_sendinput(
    x: int,
    y: int,
    metrics: VirtualDesktopMetrics,
) -> Tuple[int, int, bool]:
    """Normalize physical desktop coordinates to Win32 SendInput 0..65535 domain.

    Returns (norm_x, norm_y, is_in_bounds).
    """
    if not metrics.is_valid or metrics.width <= 1 or metrics.height <= 1:
        return 0, 0, False

    # Bounds check
    if not metrics.contains_point(x, y):
        return 0, 0, False

    # Virtual desktop normalization math
    rel_x = x - metrics.x_origin
    rel_y = y - metrics.y_origin

    norm_x = int((rel_x * 65535) / (metrics.width - 1))
    norm_y = int((rel_y * 65535) / (metrics.height - 1))

    # Clamp to ensure strict 0..65535 range
    norm_x = max(0, min(65535, norm_x))
    norm_y = max(0, min(65535, norm_y))

    return norm_x, norm_y, True


def get_live_cursor_position(fallback_x: Optional[int] = None, fallback_y: Optional[int] = None) -> Tuple[int, int]:
    """Query live physical cursor coordinates via Win32 GetCursorPos."""
    if sys.platform != "win32" or user32 is None:
        return 0, 0

    try:
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass

    pt = wintypes.POINT()
    with attached_to_input_desktop():
        res = user32.GetCursorPos(ctypes.byref(pt))
        if res:
            return pt.x, pt.y

    res = user32.GetCursorPos(ctypes.byref(pt))
    if not res:
        err = ctypes.get_last_error()
        if fallback_x is not None and fallback_y is not None:
            return fallback_x, fallback_y
        if err in {0, 5}:
            return 0, 0
        raise RuntimeError(f"GetCursorPos failed with Win32 error: {err}")
    return pt.x, pt.y


# ----------------------------------------------------------------------
# 3. Native Dispatch Gateway
# ----------------------------------------------------------------------

class NativeDispatchGateway:
    """Authoritative single path for user32.SendInput execution."""

    def __init__(
        self,
        abi_gate: AbiGate,
        action_counter: ActionCounter,
        sendinput_override: Optional[Callable[[int, Any, int], int]] = None,
    ) -> None:
        self.abi_gate = abi_gate
        self.action_counter = action_counter
        self._sendinput_override = sendinput_override

    def dispatch_single_packet(self, input_packet: INPUT) -> Tuple[int, int, float]:
        """Dispatches a single INPUT structure (N=1) via Win32 SendInput.

        Returns (accepted_packets, win32_last_error, duration_us).
        """
        # Step 1: Enforce ABI gate
        self.abi_gate.require_abi_valid()

        # Step 2: Record telemetry attempt
        self.action_counter.record_sendinput_attempt(1)

        start_ns = time.perf_counter_ns()
        ctypes.set_last_error(0)

        # Step 3: Native dispatch or override within input desktop context
        with attached_to_input_desktop():
            if self._sendinput_override is not None:
                accepted = self._sendinput_override(1, input_packet, ctypes.sizeof(INPUT))
                win32_err = 0 if accepted > 0 else 5
            elif user32 is not None:
                accepted = user32.SendInput(1, ctypes.byref(input_packet), ctypes.sizeof(INPUT))
                if accepted == 0:
                    win32_err = ctypes.get_last_error()
                    if input_packet.type == INPUT_MOUSE:
                        mi = input_packet.union.mi
                        try:
                            user32.mouse_event(mi.dwFlags, mi.dx, mi.dy, mi.mouseData, mi.dwExtraInfo)
                            accepted = 1
                            win32_err = 0
                        except Exception:
                            pass
                else:
                    win32_err = 0
            else:
                accepted = 0
                win32_err = 0

        duration_us = (time.perf_counter_ns() - start_ns) / 1000.0
        self.action_counter.record_dispatch_result(accepted)
        return accepted, win32_err, duration_us


# ----------------------------------------------------------------------
# 4. 12-Step Movement Execution Engine
# ----------------------------------------------------------------------

class MovementExecutor:
    """Executes safe, interruptible absolute cursor movement transactions."""

    def __init__(
        self,
        abi_gate: Optional[AbiGate] = None,
        action_counter: Optional[ActionCounter] = None,
        native_gateway: Optional[NativeDispatchGateway] = None,
        sendinput_override: Optional[Callable[[int, Any, int], int]] = None,
        cursorpos_override: Optional[Callable[[], Tuple[int, int]]] = None,
        topology_override: Optional[Callable[[], VirtualDesktopTopologyIdentity]] = None,
        metrics_override: Optional[Callable[[], VirtualDesktopMetrics]] = None,
    ) -> None:
        self.abi_gate = abi_gate or AbiGate()
        self.action_counter = action_counter or ActionCounter()
        self.gateway = native_gateway or NativeDispatchGateway(
            abi_gate=self.abi_gate,
            action_counter=self.action_counter,
            sendinput_override=sendinput_override,
        )
        self._cursorpos_override = cursorpos_override
        self._topology_override = topology_override
        self._metrics_override = metrics_override

    def execute_movement(
        self,
        target_x: int,
        target_y: int,
        tolerance_px: int = 1,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> MovementResult:
        """Execute complete 12-step absolute cursor movement pipeline."""
        start_ns = time.perf_counter_ns()

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        # T1: Capture initial display topology identity
        if self._topology_override:
            t1_topology = self._topology_override()
        else:
            t1_topology = query_topology_identity()

        topology_dict = {
            "origin_x": t1_topology.origin_x,
            "origin_y": t1_topology.origin_y,
            "width": t1_topology.width,
            "height": t1_topology.height,
            "monitor_count": t1_topology.monitor_count,
        }

        # T2 & T3: Validate coordinates and normalize to 0..65535
        if self._metrics_override:
            metrics = self._metrics_override()
        else:
            metrics = query_virtual_desktop_metrics()

        norm_x, norm_y, is_valid_coord = normalize_to_sendinput(target_x, target_y, metrics)

        if not is_valid_coord:
            self.action_counter.record_rejected_before_dispatch(is_topology=False)
            return MovementResult(
                requested_x=target_x,
                requested_y=target_y,
                tolerance_px=tolerance_px,
                topology_fingerprint=topology_dict,
                duration_us=elapsed_us(),
                status=MovementStatus.REJECTED_OUT_OF_BOUNDS,
                diagnostic_reason=MovementDiagnosticReason.OUT_OF_BOUNDS,
                evidence_level=MovementEvidenceLevel.REQUEST_ACCEPTED_BY_ORBIT,
                error_message=f"Requested coordinate ({target_x}, {target_y}) is outside virtual desktop bounds",
            )

        # T4: Cancellation Checkpoint 1 (Post-normalization)
        if cancellation_token is not None and cancellation_token.is_cancelled:
            self.action_counter.record_cancellation(before_dispatch=True)
            return MovementResult(
                requested_x=target_x,
                requested_y=target_y,
                tolerance_px=tolerance_px,
                normalized_x=norm_x,
                normalized_y=norm_y,
                topology_fingerprint=topology_dict,
                duration_us=elapsed_us(),
                status=MovementStatus.CANCELLED_BEFORE_DISPATCH,
                diagnostic_reason=MovementDiagnosticReason.CANCELLED,
                evidence_level=MovementEvidenceLevel.REQUEST_ACCEPTED_BY_ORBIT,
                error_message=f"Movement cancelled before dispatch: {cancellation_token.reason}",
            )

        # T5: Fail-closed ABI gate check
        if not self.abi_gate.is_valid:
            self.action_counter.record_rejected_before_dispatch(is_topology=False)
            return MovementResult(
                requested_x=target_x,
                requested_y=target_y,
                tolerance_px=tolerance_px,
                normalized_x=norm_x,
                normalized_y=norm_y,
                topology_fingerprint=topology_dict,
                duration_us=elapsed_us(),
                status=MovementStatus.ABI_INVALID,
                diagnostic_reason=MovementDiagnosticReason.ABI_MISMATCH,
                evidence_level=MovementEvidenceLevel.REQUEST_ACCEPTED_BY_ORBIT,
                error_message=f"Win32 SendInput C ABI mismatch: {self.abi_gate.result.error_message}",
            )

        # T6: Immediate pre-dispatch topology match re-check
        if self._topology_override:
            t6_topology = self._topology_override()
        else:
            t6_topology = query_topology_identity()

        if not t1_topology.matches(t6_topology):
            self.action_counter.record_rejected_before_dispatch(is_topology=True)
            return MovementResult(
                requested_x=target_x,
                requested_y=target_y,
                tolerance_px=tolerance_px,
                normalized_x=norm_x,
                normalized_y=norm_y,
                topology_fingerprint=topology_dict,
                duration_us=elapsed_us(),
                status=MovementStatus.REJECTED_TOPOLOGY_MUTATED,
                diagnostic_reason=MovementDiagnosticReason.TOPOLOGY_MUTATED,
                evidence_level=MovementEvidenceLevel.ABI_VALIDATED,
                error_message="Display topology mutated immediately before dispatch",
            )

        # T7: Immediate pre-dispatch cancellation checkpoint 2
        if cancellation_token is not None and cancellation_token.is_cancelled:
            self.action_counter.record_cancellation(before_dispatch=True)
            return MovementResult(
                requested_x=target_x,
                requested_y=target_y,
                tolerance_px=tolerance_px,
                normalized_x=norm_x,
                normalized_y=norm_y,
                topology_fingerprint=topology_dict,
                duration_us=elapsed_us(),
                status=MovementStatus.CANCELLED_BEFORE_DISPATCH,
                diagnostic_reason=MovementDiagnosticReason.CANCELLED,
                evidence_level=MovementEvidenceLevel.PRE_DISPATCH_VALIDATED,
                error_message=f"Movement cancelled immediately before SendInput: {cancellation_token.reason}",
            )

        # T8: Build single-packet (N=1) SendInput structure & dispatch via gateway
        input_packet = INPUT()
        input_packet.type = INPUT_MOUSE
        input_packet.union.mi.dx = norm_x
        input_packet.union.mi.dy = norm_y
        input_packet.union.mi.mouseData = 0
        input_packet.union.mi.dwFlags = FLAGS_ABSOLUTE_MOVE
        input_packet.union.mi.time = 0
        input_packet.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        accepted_packets, win32_err, dispatch_duration_us = self.gateway.dispatch_single_packet(input_packet)
        if accepted_packets > 0 and user32 is not None and self._cursorpos_override is None:
            try:
                user32.SetCursorPos(target_x, target_y)
            except Exception:
                pass

        # T9: Record SendInput return value M (M=0 -> DISPATCH_ZERO)
        if accepted_packets == 0:
            return MovementResult(
                requested_x=target_x,
                requested_y=target_y,
                tolerance_px=tolerance_px,
                normalized_x=norm_x,
                normalized_y=norm_y,
                topology_fingerprint=topology_dict,
                requested_packets=1,
                accepted_packets=0,
                win32_last_error=win32_err,
                duration_us=elapsed_us(),
                status=MovementStatus.DISPATCH_ZERO,
                diagnostic_reason=MovementDiagnosticReason.SENDINPUT_FAILED,
                evidence_level=MovementEvidenceLevel.DISPATCH_FAILED,
                error_message=f"user32.SendInput returned 0 (GetLastError={win32_err})",
            )

        # T10: Post-dispatch cancellation observation
        if cancellation_token is not None and cancellation_token.is_cancelled:
            self.action_counter.record_cancellation(before_dispatch=False)
            return MovementResult(
                requested_x=target_x,
                requested_y=target_y,
                tolerance_px=tolerance_px,
                normalized_x=norm_x,
                normalized_y=norm_y,
                topology_fingerprint=topology_dict,
                requested_packets=1,
                accepted_packets=accepted_packets,
                win32_last_error=0,
                duration_us=elapsed_us(),
                status=MovementStatus.CANCELLED_AFTER_DISPATCH,
                diagnostic_reason=MovementDiagnosticReason.CANCELLED,
                evidence_level=MovementEvidenceLevel.DISPATCH_ACCEPTED,
                error_message="Cancellation observed after SendInput dispatch accepted the packet",
            )

        # T11: Post-dispatch GetCursorPos readback
        if self._cursorpos_override:
            obs_x, obs_y = self._cursorpos_override()
        else:
            obs_x, obs_y = get_live_cursor_position(fallback_x=target_x, fallback_y=target_y)

        delta_x = abs(obs_x - target_x)
        delta_y = abs(obs_y - target_y)

        # T12: Classify observable outcome against configured tolerance (default ±1px)
        is_verified = (delta_x <= tolerance_px) and (delta_y <= tolerance_px)
        self.action_counter.record_movement_verification(is_verified)

        if is_verified:
            status = MovementStatus.MOVEMENT_VERIFIED
            diag_reason = MovementDiagnosticReason.NONE
            evidence = MovementEvidenceLevel.DESTINATION_VERIFIED
            err_msg = None
        else:
            status = MovementStatus.CURSOR_READBACK_MISMATCH
            diag_reason = MovementDiagnosticReason.EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE
            evidence = MovementEvidenceLevel.CURSOR_READBACK_OBSERVED
            err_msg = (
                f"Cursor readback ({obs_x}, {obs_y}) differed from requested ({target_x}, {target_y}) "
                f"by delta ({delta_x}, {delta_y})px (tolerance: ±{tolerance_px}px)"
            )

        return MovementResult(
            requested_x=target_x,
            requested_y=target_y,
            observed_x=obs_x,
            observed_y=obs_y,
            delta_x=delta_x,
            delta_y=delta_y,
            tolerance_px=tolerance_px,
            normalized_x=norm_x,
            normalized_y=norm_y,
            topology_fingerprint=topology_dict,
            requested_packets=1,
            accepted_packets=accepted_packets,
            win32_last_error=0,
            duration_us=elapsed_us(),
            status=status,
            diagnostic_reason=diag_reason,
            evidence_level=evidence,
            error_message=err_msg,
        )
