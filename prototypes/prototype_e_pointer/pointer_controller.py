"""
Pointer Movement Controller for ORBIT Prototype E.
(Phase 2B — Absolute Cursor Movement Only)

CRITICAL SAFETY & EXECUTION INVARIANTS:
1. PHASE 2B PERMITS ABSOLUTE CURSOR MOVEMENT ONLY.
   Zero mouse clicks, zero button-down, zero button-up, zero drag, zero wheel actions.
2. NO MAGIC NUMBERS:
   Movement flags are explicitly composed via named Win32 constants:
   MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK.
3. SINGLE AUTHORITATIVE DISPATCH GATEWAY:
   All SendInput calls are routed strictly through NativeDispatchGateway.
   No ad-hoc user32.SendInput calls exist elsewhere.
4. FAIL-CLOSED ABI GATE:
   AbiGate.require_abi_valid() is enforced before every potential dispatch.
5. STRUCTURAL TOPOLOGY IDENTITY:
   Display topology is validated using VirtualDesktopTopologyIdentity (origin, dimensions,
   monitor count). Timestamps are never compared for topology identity.
6. SINGLE-PACKET SENDINPUT HONESTY (N = 1):
   SendInput return value M is strictly M=0 (DISPATCH_ZERO) or M=1 (DISPATCH_ACCEPTED).
   Partial dispatch is designated DISPATCH_PARTIAL_NOT_APPLICABLE. Zero automatic retries.
7. NON-ATOMIC EXECUTION & READBACK TIMING:
   T1 (topology) -> T2 (normalize) -> T3 (pre-gate) -> T4 (SendInput) -> T5 (GetCursorPos).
   MOVEMENT_VERIFIED proves only that the destination was observed within tolerance
   at T5; it does NOT prove continuous exclusive trajectory control.
8. EPISTEMIC MODESTY:
   Readback mismatch is classified as CURSOR_READBACK_MISMATCH with
   EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE, never asserting human takeover without hook proof.
9. NO DESKTOP SWITCHING:
   Zero OpenInputDesktop or SetThreadDesktop calls.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Any, Callable, Dict, Optional, Tuple

from app_types import (
    MovementRequest,
    MovementExecutionResult,
    MovementExecutionStatus,
    MovementDiagnosticReason,
    NativeDispatchResult,
    VirtualDesktopMetrics,
    VirtualDesktopTopologyIdentity,
    VirtualDesktopTopologyObservation,
    NormalizedCoordinate,
    TargetValidationStatus,
    ValidationFailureReason,
)
from abi_validator import (
    AbiGate,
    INPUT,
    MOUSEINPUT,
    INPUT_MOUSE,
    ORBIT_EXTRA_INFO_SIGNATURE,
)
from coordinate_mapper import (
    get_virtual_desktop_metrics,
    get_topology_identity,
    normalize_to_sendinput,
)
from cancellation import CancellationToken
from dpi_awareness import initialize_dpi_awareness
from native_gateway import NativeDispatchGateway

# ----------------------------------------------------------------------
# 1. Named Win32 Mouse Event Flags (Correction C1)
# ----------------------------------------------------------------------

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

# Explicitly composed bitmask for virtual desktop absolute movement
FLAGS_ABSOLUTE_MOVE = (
    MOUSEEVENTF_MOVE
    | MOUSEEVENTF_ABSOLUTE
    | MOUSEEVENTF_VIRTUALDESK
)

user32 = ctypes.windll.user32

# Configure explicit ctypes signature for GetCursorPos
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL


# ----------------------------------------------------------------------
# 2. Live Cursor Position Readback Helper
# ----------------------------------------------------------------------

def get_live_cursor_position() -> Tuple[int, int]:
    """
    Queries live physical cursor coordinates via Win32 GetCursorPos.
    Returns (x, y) physical screen pixel tuple.
    """
    initialize_dpi_awareness()

    pt = wintypes.POINT()
    res = user32.GetCursorPos(ctypes.byref(pt))
    if not res:
        err = ctypes.GetLastError()
        raise RuntimeError(f"GetCursorPos failed with Win32 error code: {err}")
    return (pt.x, pt.y)


# ----------------------------------------------------------------------
# 3. Pointer Movement Controller Class
# ----------------------------------------------------------------------

class PointerController:
    """
    Safe, deterministic, interruptible pointer movement execution engine.
    Executes single-packet (N = 1) absolute cursor movements through NativeDispatchGateway.
    """

    def __init__(
        self,
        native_gateway: Optional[NativeDispatchGateway] = None,
        abi_gate: Optional[AbiGate] = None,
        cursorpos_override: Optional[Callable[[], Tuple[int, int]]] = None,
        topology_override: Optional[Callable[[], VirtualDesktopTopologyIdentity]] = None,
    ):
        """
        Initializes the PointerController.
        Optional override parameters are strictly for synthetic unit testing.
        """
        self._abi_gate = abi_gate or (native_gateway.abi_gate if native_gateway else AbiGate())
        self._gateway = native_gateway or NativeDispatchGateway(abi_gate=self._abi_gate)
        self._cursorpos_override = cursorpos_override
        self._topology_override = topology_override
        initialize_dpi_awareness()

    @property
    def gateway(self) -> NativeDispatchGateway:
        return self._gateway

    @property
    def abi_gate(self) -> AbiGate:
        return self._abi_gate

    def execute_movement(
        self,
        request: MovementRequest,
        telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> MovementExecutionResult:
        """
        Executes a complete 12-step Phase 2B movement transaction:

        T1  -> Capture initial display topology identity
        T2  -> Validate requested coordinates against virtual desktop bounds
        T3  -> Normalize physical coordinates to Win32 0..65535 domain
        T4  -> Cooperative cancellation checkpoint 1
        T5  -> Enforce fail-closed Win32 SendInput C ABI gate
        T6  -> Immediate pre-dispatch topology identity match re-check
        T7  -> Immediate pre-dispatch cancellation checkpoint 2
        T8  -> Build and dispatch single-packet (N=1) SendInput structure via NativeDispatchGateway
        T9  -> Record exact SendInput return value M (0 or 1) & LastError
        T10 -> Post-dispatch cancellation observation
        T11 -> Post-dispatch GetCursorPos readback
        T12 -> Classify observable outcome against configured tolerance
        """
        start_ns = time.perf_counter_ns()
        requested_pos = (request.target_x, request.target_y)
        token: Optional[CancellationToken] = request.cancellation_token

        telemetry_ctx: Dict[str, Any] = {
            "requested_pos": requested_pos,
            "tolerance_px": request.tolerance_px,
            "start_timestamp_ns": start_ns,
            "checkpoints_passed": [],
        }

        def elapsed_us() -> float:
            return (time.perf_counter_ns() - start_ns) / 1000.0

        def emit_telemetry(res: MovementExecutionResult) -> MovementExecutionResult:
            if telemetry_callback:
                telemetry_ctx["duration_us"] = res.duration_us
                telemetry_ctx["status"] = res.status.value
                telemetry_ctx["diagnostic_reason"] = res.diagnostic_reason.value
                telemetry_ctx["observed_pos"] = res.observed_pos
                telemetry_ctx["delta_px"] = res.delta_px
                telemetry_ctx["accepted_packets"] = res.accepted_packets
                telemetry_callback(telemetry_ctx)
            return res

        # --------------------------------------------------------------
        # CP1: Cancellation check before any work
        # --------------------------------------------------------------
        if token is not None and token.is_cancelled:
            telemetry_ctx["checkpoints_passed"].append("CP1_PRE_WORK_CANCELLED")
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.CANCELLED_BEFORE_DISPATCH,
                    diagnostic_reason=MovementDiagnosticReason.CANCELLED,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    error_message=f"Action cancelled before coordinate processing: {token.reason}",
                )
            )

        # --------------------------------------------------------------
        # T1: Capture initial topology identity
        # --------------------------------------------------------------
        if self._topology_override:
            initial_topology = self._topology_override()
        else:
            initial_topology = get_topology_identity()
        telemetry_ctx["initial_topology"] = initial_topology

        # --------------------------------------------------------------
        # T2 & T3: Validate and normalize coordinates
        # --------------------------------------------------------------
        metrics = get_virtual_desktop_metrics()
        norm_coord, val_result = normalize_to_sendinput(
            request.target_x, request.target_y, metrics
        )
        telemetry_ctx["normalized_coord"] = (norm_coord.norm_x, norm_coord.norm_y)

        if not val_result.is_valid or norm_coord.was_out_of_bounds:
            telemetry_ctx["validation_failure"] = val_result.failure_reason.value
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.REJECTED_OUT_OF_BOUNDS,
                    diagnostic_reason=MovementDiagnosticReason.OUT_OF_BOUNDS,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    error_message=val_result.diagnostic_message or "Coordinates outside virtual desktop bounds",
                )
            )

        telemetry_ctx["checkpoints_passed"].append("CP2_COORDINATES_NORMALIZED")

        # --------------------------------------------------------------
        # T4: Cancellation checkpoint 2
        # --------------------------------------------------------------
        if token is not None and token.is_cancelled:
            telemetry_ctx["checkpoints_passed"].append("CP2_POST_NORM_CANCELLED")
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.CANCELLED_BEFORE_DISPATCH,
                    diagnostic_reason=MovementDiagnosticReason.CANCELLED,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    error_message=f"Action cancelled after normalization: {token.reason}",
                )
            )

        # --------------------------------------------------------------
        # T5: Fail-closed Win32 C ABI gate check
        # --------------------------------------------------------------
        if not self._abi_gate.is_injection_enabled():
            telemetry_ctx["abi_gate_valid"] = False
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.ABI_INVALID,
                    diagnostic_reason=MovementDiagnosticReason.ABI_MISMATCH,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    error_message=f"Fail-closed ABI gate rejected dispatch: {self._abi_gate.result.error_message}",
                )
            )
        telemetry_ctx["abi_gate_valid"] = True
        telemetry_ctx["checkpoints_passed"].append("CP3_ABI_GATE_VERIFIED")

        # --------------------------------------------------------------
        # T6: Immediate pre-dispatch topology identity re-check (C2)
        # --------------------------------------------------------------
        if self._topology_override:
            current_topology = self._topology_override()
        else:
            current_topology = get_topology_identity()

        if not initial_topology.matches(current_topology):
            telemetry_ctx["topology_mutated"] = True
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.REJECTED_TOPOLOGY_MUTATED,
                    diagnostic_reason=MovementDiagnosticReason.TOPOLOGY_MUTATED,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    error_message=(
                        f"Display topology mutated before dispatch: "
                        f"Initial={initial_topology} vs Current={current_topology}"
                    ),
                )
            )
        telemetry_ctx["checkpoints_passed"].append("CP4_TOPOLOGY_CONFIRMED")

        # --------------------------------------------------------------
        # T7: Immediate pre-dispatch cancellation checkpoint (CP4)
        # --------------------------------------------------------------
        if token is not None and token.is_cancelled:
            telemetry_ctx["checkpoints_passed"].append("CP4_PRE_DISPATCH_CANCELLED")
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.CANCELLED_BEFORE_DISPATCH,
                    diagnostic_reason=MovementDiagnosticReason.CANCELLED,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    error_message=f"Action cancelled immediately before SendInput: {token.reason}",
                )
            )

        # --------------------------------------------------------------
        # T8: Build single-packet (N = 1) SendInput structure
        # --------------------------------------------------------------
        input_packet = INPUT()
        input_packet.type = INPUT_MOUSE
        input_packet.union.mi.dx = norm_coord.norm_x
        input_packet.union.mi.dy = norm_coord.norm_y
        input_packet.union.mi.mouseData = 0
        input_packet.union.mi.dwFlags = FLAGS_ABSOLUTE_MOVE
        input_packet.union.mi.time = 0
        input_packet.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        # Dispatch exclusively via NativeDispatchGateway
        dispatch_result: NativeDispatchResult = self._gateway.dispatch_single_packet(input_packet)
        accepted_packets = dispatch_result.accepted_packets

        telemetry_ctx["sendinput_return_m"] = accepted_packets
        telemetry_ctx["win32_last_error"] = dispatch_result.win32_last_error
        telemetry_ctx["checkpoints_passed"].append("CP5_SENDINPUT_DISPATCHED")

        # --------------------------------------------------------------
        # T9: Record SendInput return value M (C4: N=1)
        # --------------------------------------------------------------
        if accepted_packets == 0:
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.DISPATCH_ZERO,
                    diagnostic_reason=MovementDiagnosticReason.SENDINPUT_FAILED,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=0,
                    duration_us=elapsed_us(),
                    error_message=(
                        f"SendInput returned 0 (Win32 GetLastError="
                        f"{dispatch_result.win32_last_error}); zero packets accepted"
                    ),
                )
            )

        # --------------------------------------------------------------
        # T10: Post-dispatch cancellation check (C3)
        # --------------------------------------------------------------
        if token is not None and token.is_cancelled:
            telemetry_ctx["checkpoints_passed"].append("CP6_POST_DISPATCH_CANCELLED")
            return emit_telemetry(
                MovementExecutionResult(
                    status=MovementExecutionStatus.CANCELLED_AFTER_DISPATCH,
                    diagnostic_reason=MovementDiagnosticReason.CANCELLED,
                    requested_pos=requested_pos,
                    observed_pos=None,
                    delta_px=None,
                    accepted_packets=accepted_packets,
                    duration_us=elapsed_us(),
                    error_message="Cancellation observed after SendInput accepted the packet",
                )
            )

        # --------------------------------------------------------------
        # T11: Post-dispatch GetCursorPos readback (C5)
        # --------------------------------------------------------------
        if self._cursorpos_override:
            observed_pos = self._cursorpos_override()
        else:
            observed_pos = get_live_cursor_position()

        delta_x = abs(observed_pos[0] - requested_pos[0])
        delta_y = abs(observed_pos[1] - requested_pos[1])
        delta_px = (delta_x, delta_y)

        telemetry_ctx["observed_pos"] = observed_pos
        telemetry_ctx["delta_px"] = delta_px
        telemetry_ctx["checkpoints_passed"].append("CP7_READBACK_COMPLETED")

        # --------------------------------------------------------------
        # T12: Classify observable outcome against configured tolerance
        # --------------------------------------------------------------
        is_verified = (delta_x <= request.tolerance_px) and (delta_y <= request.tolerance_px)

        if is_verified:
            status = MovementExecutionStatus.MOVEMENT_VERIFIED
            diagnostic_reason = MovementDiagnosticReason.NONE
            error_message = None
        else:
            status = MovementExecutionStatus.CURSOR_READBACK_MISMATCH
            diagnostic_reason = MovementDiagnosticReason.EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE
            error_message = (
                f"Cursor readback ({observed_pos[0]}, {observed_pos[1]}) differed from "
                f"requested ({requested_pos[0]}, {requested_pos[1]}) by delta ({delta_x}, {delta_y})px "
                f"(tolerance: ±{request.tolerance_px}px)"
            )

        return emit_telemetry(
            MovementExecutionResult(
                status=status,
                diagnostic_reason=diagnostic_reason,
                requested_pos=requested_pos,
                observed_pos=observed_pos,
                delta_px=delta_px,
                accepted_packets=accepted_packets,
                duration_us=elapsed_us(),
                error_message=error_message,
            )
        )

    def move_to(
        self,
        target_x: int,
        target_y: int,
        tolerance_px: int = 1,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> MovementExecutionResult:
        """
        Convenience wrapper executing a MovementRequest.
        """
        req = MovementRequest(
            target_x=target_x,
            target_y=target_y,
            tolerance_px=tolerance_px,
            cancellation_token=cancellation_token,
        )
        return self.execute_movement(req)
