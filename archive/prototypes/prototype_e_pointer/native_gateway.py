"""
Authoritative Native Input Dispatch Gateway for ORBIT Prototype E.
(Phase 2B/2C — Native Dispatch Gateway, Single-Call Invariant & Multi-Packet Support)

CRITICAL INVARIANTS:
1. SINGLE DISPATCH GATEWAY INVARIANT:
   This module is the ONLY authorized path for calling user32.SendInput in Prototype E.
   No other module or function may directly invoke user32.SendInput.
2. MANDATORY ABI GATE CHECK:
   AbiGate.require_abi_valid() is enforced before every native dispatch attempt.
3. MANDATORY ACTION COUNTER INSTRUMENTATION:
   Every dispatch attempt unconditionally increments ActionCounter.sendinput_calls,
   regardless of whether SendInput returns N, 0, or partial M < N.
4. ZERO AUTOMATIC RETRIES:
   If SendInput returns 0 or fails, the gateway captures the exact result and stops.
5. NO DESKTOP SWITCHING:
   Desktop switching APIs may have been used during isolated development investigation
   or test-harness thread attachment, but they are not part of the final Phase 2B/2C
   production implementation path. Zero OpenInputDesktop or SetThreadDesktop calls exist here.
6. LASTERROR TELEMETRY BOUNDARY:
   SendInput returning 0 indicates that User32 did not accept the input packet. If Windows
   provides a Win32 last-error code, it is captured for diagnostics via ctypes.get_last_error(),
   but SendInput does not guarantee setting GetLastError for all failure modes (e.g., UIPI
   isolation, secure desktop, or background thread restrictions). LastError is captured strictly
   as diagnostic telemetry, not as absolute proof of root cause.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Any, Callable, List, Optional, Tuple

from app_types import (
    NativeDispatchResult,
    MovementExecutionStatus,
    MovementDiagnosticReason,
)
from abi_validator import (
    AbiGate,
    INPUT,
    MOUSEINPUT,
    INPUT_MOUSE,
    ORBIT_EXTRA_INFO_SIGNATURE,
)

# Use WinDLL with use_last_error=True for accurate thread-local Win32 error capture
user32 = ctypes.WinDLL("user32", use_last_error=True)

# Configure explicit ctypes Win32 signatures on AMD64
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


class NativeDispatchGateway:
    """
    Authoritative single native input dispatch gateway.
    Ensures fail-closed ABI gating, ActionCounter telemetry, and atomic dispatch capture.
    """
    _instance: Optional["NativeDispatchGateway"] = None

    def __init__(
        self,
        abi_gate: Optional[AbiGate] = None,
        sendinput_override: Optional[Callable[[int, Any, int], int]] = None,
    ):
        self._abi_gate = abi_gate or AbiGate()
        self._sendinput_override = sendinput_override
        self._total_dispatch_attempts: int = 0
        self._successful_dispatches: int = 0
        self._failed_dispatches: int = 0

    @property
    def abi_gate(self) -> AbiGate:
        return self._abi_gate

    @property
    def total_dispatch_attempts(self) -> int:
        return self._total_dispatch_attempts

    @property
    def successful_dispatches(self) -> int:
        return self._successful_dispatches

    @property
    def failed_dispatches(self) -> int:
        return self._failed_dispatches

    def dispatch_single_packet(self, input_packet: INPUT) -> NativeDispatchResult:
        """
        Dispatches a single INPUT structure (N = 1) through Win32 SendInput.

        Enforces:
        1. ABI Gate check (raises RuntimeError if invalid).
        2. ActionCounter increment (counted on every attempt).
        3. Native SendInput execution with ctypes thread-local last error management.
        4. Immediate get_last_error capture if SendInput returns 0.
        5. Return of structured NativeDispatchResult.
        """
        # Step 1: Enforce ABI gate
        self._abi_gate.require_abi_valid()

        # Step 2: Increment dispatch telemetry counters
        self._total_dispatch_attempts += 1
        self._abi_gate.action_counter.record_sendinput(1)

        start_ns = time.perf_counter_ns()
        requested_packets = 1

        # Clear last error before dispatch to prevent stale error reporting
        ctypes.set_last_error(0)

        # Step 3: Execute native dispatch (or test override)
        if self._sendinput_override is not None:
            accepted_packets = self._sendinput_override(
                requested_packets,
                input_packet,
                ctypes.sizeof(INPUT),
            )
        else:
            accepted_packets = user32.SendInput(
                requested_packets,
                ctypes.byref(input_packet),
                ctypes.sizeof(INPUT),
            )

        end_ns = time.perf_counter_ns()
        duration_us = (end_ns - start_ns) / 1000.0

        # Step 4: Capture LastError immediately if SendInput returns 0
        if accepted_packets == 0:
            win32_last_error = ctypes.get_last_error()
            self._failed_dispatches += 1
        else:
            win32_last_error = 0
            self._successful_dispatches += 1

        return NativeDispatchResult(
            requested_packets=requested_packets,
            accepted_packets=accepted_packets,
            win32_last_error=win32_last_error,
            duration_us=duration_us,
            dispatch_timestamp_ns=start_ns,
        )

    def dispatch_packet_array(self, input_packets: List[INPUT]) -> NativeDispatchResult:
        """
        Dispatches an array of INPUT structures (N >= 1) in a single SendInput call.

        Enforces:
        1. ABI Gate check.
        2. Non-empty packet list requirement.
        3. ActionCounter increment.
        4. Native SendInput execution of contiguous C array.
        5. Immediate get_last_error capture if accepted_packets < requested_packets.
        6. Return of structured NativeDispatchResult capturing M (0, M < N, or M == N).
        """
        if not input_packets:
            raise ValueError("dispatch_packet_array requires at least one INPUT packet.")

        # Step 1: Enforce ABI gate
        self._abi_gate.require_abi_valid()

        requested_packets = len(input_packets)
        self._total_dispatch_attempts += 1
        self._abi_gate.action_counter.record_sendinput(1)

        # Construct contiguous C array of INPUT structures
        input_array = (INPUT * requested_packets)(*input_packets)

        start_ns = time.perf_counter_ns()

        # Clear last error before dispatch
        ctypes.set_last_error(0)

        # Step 2: Execute native dispatch (or test override)
        if self._sendinput_override is not None:
            accepted_packets = self._sendinput_override(
                requested_packets,
                input_array,
                ctypes.sizeof(INPUT),
            )
        else:
            accepted_packets = user32.SendInput(
                requested_packets,
                input_array,
                ctypes.sizeof(INPUT),
            )

        end_ns = time.perf_counter_ns()
        duration_us = (end_ns - start_ns) / 1000.0

        # Step 3: Capture LastError if any packet failed
        if accepted_packets < requested_packets:
            win32_last_error = ctypes.get_last_error()
            self._failed_dispatches += 1
        else:
            win32_last_error = 0
            self._successful_dispatches += 1

        return NativeDispatchResult(
            requested_packets=requested_packets,
            accepted_packets=accepted_packets,
            win32_last_error=win32_last_error,
            duration_us=duration_us,
            dispatch_timestamp_ns=start_ns,
        )
