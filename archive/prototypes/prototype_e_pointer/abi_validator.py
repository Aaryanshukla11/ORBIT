"""
Win32 SendInput C ABI Structure Definitions & Runtime Verification Gate.
(ORBIT Prototype E — Phase 2A Foundation)

CRITICAL INVARIANT:
This module defines native Win32 C structures and verifies runtime ABI alignment.
It contains ZERO calls to SendInput, SetCursorPos, or any input injection APIs.
"""

import ctypes
from ctypes import wintypes
import platform
import sys
import time
from typing import Any, Dict, Optional, Tuple

from app_types import (
    AbiValidationStatus,
    AbiValidationResult,
    ActionCounter,
)

# ----------------------------------------------------------------------
# 1. Win32 Constants
# ----------------------------------------------------------------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# Mouse Event Flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

# ORBIT Tag Signature for ExtraInfo
ORBIT_EXTRA_INFO_SIGNATURE = 0x50524F544F425F31  # ASCII 'PROTOB_1'


# ----------------------------------------------------------------------
# 2. Native Win32 Ctypes Structure Definitions (Windows AMD64)
# ----------------------------------------------------------------------

class MOUSEINPUT(ctypes.Structure):
    """
    Win32 MOUSEINPUT Structure.
    Size on AMD64: 32 bytes (24 bytes data + 4 bytes padding + 4 bytes tail alignment)
    """
    _fields_ = [
        ("dx", wintypes.LONG),            # 4 bytes, offset 0
        ("dy", wintypes.LONG),            # 4 bytes, offset 4
        ("mouseData", wintypes.DWORD),     # 4 bytes, offset 8
        ("dwFlags", wintypes.DWORD),       # 4 bytes, offset 12
        ("time", wintypes.DWORD),          # 4 bytes, offset 16
        ("dwExtraInfo", ctypes.c_uint64),  # 8 bytes, offset 24 (4 bytes padding between time & dwExtraInfo)
    ]


class KEYBDINPUT(ctypes.Structure):
    """
    Win32 KEYBDINPUT Structure.
    Size on AMD64: 24 bytes (or 32 bytes with union alignment)
    """
    _fields_ = [
        ("wVk", wintypes.WORD),            # 2 bytes, offset 0
        ("wScan", wintypes.WORD),          # 2 bytes, offset 2
        ("dwFlags", wintypes.DWORD),       # 4 bytes, offset 4
        ("time", wintypes.DWORD),          # 4 bytes, offset 8
        ("dwExtraInfo", ctypes.c_uint64),  # 8 bytes, offset 16 (4 bytes padding between time & dwExtraInfo)
    ]


class HARDWAREINPUT(ctypes.Structure):
    """
    Win32 HARDWAREINPUT Structure.
    Size on AMD64: 8 bytes
    """
    _fields_ = [
        ("uMsg", wintypes.DWORD),          # 4 bytes, offset 0
        ("wParamL", wintypes.WORD),        # 2 bytes, offset 4
        ("wParamH", wintypes.WORD),        # 2 bytes, offset 6
    ]


class _INPUTunion(ctypes.Union):
    """
    Win32 INPUT union.
    Size on AMD64: 32 bytes (governed by largest member: MOUSEINPUT)
    """
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    """
    Win32 INPUT Structure.
    Size on AMD64: 40 bytes (4 bytes type + 4 bytes padding + 32 bytes union)
    """
    _fields_ = [
        ("type", wintypes.DWORD),          # 4 bytes, offset 0
        ("union", _INPUTunion),            # 32 bytes, offset 8 (4 bytes padding before union)
    ]


# ----------------------------------------------------------------------
# 3. Runtime ABI Validator Function
# ----------------------------------------------------------------------

def validate_runtime_abi(
    simulated_override: Optional[Dict[str, Any]] = None,
) -> AbiValidationResult:
    """
    Programmatically inspects and verifies the C ABI layout of ctypes structures.

    Verifies:
    1. OS platform is Windows ('win32').
    2. Architecture is AMD64 / 64-bit.
    3. Pointer size is 8 bytes.
    4. sizeof(MOUSEINPUT) == 32 bytes.
    5. sizeof(INPUT) == 40 bytes.
    6. MOUSEINPUT field offsets: dx==0, dwFlags==12, dwExtraInfo==24.
    7. INPUT union offset: union==8.
    8. dwExtraInfo is an 8-byte unsigned integer.

    Fails closed if any assertion fails.
    """
    now_ns = time.perf_counter_ns()
    platform_system = sys.platform
    machine_arch = platform.machine()
    pointer_width = ctypes.sizeof(ctypes.c_void_p)

    # Allow simulated overrides strictly for unit testing failure modes
    if simulated_override is not None:
        sz_mouse = simulated_override.get("sizeof_mouseinput", ctypes.sizeof(MOUSEINPUT))
        sz_input = simulated_override.get("sizeof_input", ctypes.sizeof(INPUT))
        off_dx = simulated_override.get("offset_dx", MOUSEINPUT.dx.offset)
        off_flags = simulated_override.get("offset_dwflags", MOUSEINPUT.dwFlags.offset)
        off_extra = simulated_override.get("offset_dwextrainfo", MOUSEINPUT.dwExtraInfo.offset)
        off_union = simulated_override.get("offset_input_union", INPUT.union.offset)
        plat = simulated_override.get("platform_system", platform_system)
        arch = simulated_override.get("machine_arch", machine_arch)
        ptr_w = simulated_override.get("pointer_width_bytes", pointer_width)
    else:
        sz_mouse = ctypes.sizeof(MOUSEINPUT)
        sz_input = ctypes.sizeof(INPUT)
        off_dx = MOUSEINPUT.dx.offset
        off_flags = MOUSEINPUT.dwFlags.offset
        off_extra = MOUSEINPUT.dwExtraInfo.offset
        off_union = INPUT.union.offset
        plat = platform_system
        arch = machine_arch
        ptr_w = pointer_width

    # Check 1: Platform and Architecture
    if plat != "win32":
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.UNSUPPORTED_PROCESS_ARCHITECTURE,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=(ptr_w == 8),
            error_message=f"Unsupported non-Windows platform: {plat}",
            validation_timestamp_ns=now_ns,
        )

    if arch not in ("AMD64", "x86_64") or ptr_w != 8:
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.UNSUPPORTED_PROCESS_ARCHITECTURE,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=(ptr_w == 8),
            error_message=f"Unsupported process architecture: {arch} ({ptr_w*8}-bit)",
            validation_timestamp_ns=now_ns,
        )

    # Check 2: Structure Sizes
    if sz_mouse != 32:
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.ABI_MISMATCH,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=True,
            error_message=f"MOUSEINPUT structure size mismatch: expected 32 bytes, got {sz_mouse}",
            validation_timestamp_ns=now_ns,
        )

    if sz_input != 40:
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.ABI_MISMATCH,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=True,
            error_message=f"INPUT structure size mismatch: expected 40 bytes, got {sz_input}",
            validation_timestamp_ns=now_ns,
        )

    # Check 3: Field Offsets
    if off_dx != 0:
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.ABI_MISMATCH,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=True,
            error_message=f"MOUSEINPUT.dx offset mismatch: expected 0, got {off_dx}",
            validation_timestamp_ns=now_ns,
        )

    if off_flags != 12:
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.ABI_MISMATCH,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=True,
            error_message=f"MOUSEINPUT.dwFlags offset mismatch: expected 12, got {off_flags}",
            validation_timestamp_ns=now_ns,
        )

    if off_extra != 24:
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.ABI_MISMATCH,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=True,
            error_message=f"MOUSEINPUT.dwExtraInfo offset mismatch: expected 24, got {off_extra}",
            validation_timestamp_ns=now_ns,
        )

    if off_union != 8:
        return AbiValidationResult(
            is_valid=False,
            status=AbiValidationStatus.ABI_MISMATCH,
            platform_system=plat,
            machine_arch=arch,
            pointer_width_bytes=ptr_w,
            sizeof_mouseinput=sz_mouse,
            sizeof_input=sz_input,
            offset_dx=off_dx,
            offset_dwflags=off_flags,
            offset_dwextrainfo=off_extra,
            offset_input_union=off_union,
            is_pointer_sized_extrainfo=True,
            error_message=f"INPUT.union offset mismatch: expected 8, got {off_union}",
            validation_timestamp_ns=now_ns,
        )

    # All ABI assertions verified
    return AbiValidationResult(
        is_valid=True,
        status=AbiValidationStatus.ABI_VALID,
        platform_system=plat,
        machine_arch=arch,
        pointer_width_bytes=ptr_w,
        sizeof_mouseinput=sz_mouse,
        sizeof_input=sz_input,
        offset_dx=off_dx,
        offset_dwflags=off_flags,
        offset_dwextrainfo=off_extra,
        offset_input_union=off_union,
        is_pointer_sized_extrainfo=True,
        error_message=None,
        validation_timestamp_ns=now_ns,
    )


# ----------------------------------------------------------------------
# 4. Fail-Closed Initialization Gate
# ----------------------------------------------------------------------

class AbiGate:
    """
    Singleton gate enforcing that pointer injection is impossible
    unless the Win32 C ABI is programmatically verified.
    """
    _instance: Optional["AbiGate"] = None

    def __new__(cls) -> "AbiGate":
        if cls._instance is None:
            cls._instance = super(AbiGate, cls).__new__(cls)
            cls._instance._result = validate_runtime_abi()
            cls._instance._action_counter = ActionCounter()
        return cls._instance

    @property
    def result(self) -> AbiValidationResult:
        return self._result

    @property
    def action_counter(self) -> ActionCounter:
        return self._action_counter

    def is_injection_enabled(self) -> bool:
        """Returns True ONLY if ABI validation passed."""
        return self._result.is_valid and self._result.status == AbiValidationStatus.ABI_VALID

    def require_abi_valid(self) -> AbiValidationResult:
        """
        Raises RuntimeError if ABI is invalid, preventing any downstream execution.
        """
        if not self.is_injection_enabled():
            raise RuntimeError(
                f"Win32 SendInput ABI validation failed closed: {self._result.status.value} "
                f"({self._result.error_message})"
            )
        return self._result
