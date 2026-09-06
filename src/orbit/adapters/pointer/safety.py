"""Win32 SendInput C ABI definitions, fail-closed runtime verification gate, and topology safety."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
import platform
import sys
import time
from typing import Any, Dict, Optional, Tuple

# ----------------------------------------------------------------------
# 1. Win32 Constants & Mouse Flags
# ----------------------------------------------------------------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# Named Mouse Event Flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

# Virtual Key Codes for Asynchronous Observation Heuristics
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04

# Explicit bitmask for virtual desktop absolute movement
FLAGS_ABSOLUTE_MOVE = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

# ORBIT Diagnostic ExtraInfo signature
ORBIT_EXTRA_INFO_SIGNATURE = 0x50524F544F425F31  # ASCII 'PROTOB_1'


class MouseButton(str, Enum):
    """Supported pointer mouse buttons in ORBIT M1.2B."""

    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


def get_button_down_flag(button: MouseButton) -> int:
    """Map MouseButton enum to Win32 MOUSEEVENTF_*DOWN flag."""
    if button == MouseButton.LEFT:
        return MOUSEEVENTF_LEFTDOWN
    elif button == MouseButton.RIGHT:
        return MOUSEEVENTF_RIGHTDOWN
    elif button == MouseButton.MIDDLE:
        return MOUSEEVENTF_MIDDLEDOWN
    raise ValueError(f"Unsupported mouse button: {button}")


def get_button_up_flag(button: MouseButton) -> int:
    """Map MouseButton enum to Win32 MOUSEEVENTF_*UP flag."""
    if button == MouseButton.LEFT:
        return MOUSEEVENTF_LEFTUP
    elif button == MouseButton.RIGHT:
        return MOUSEEVENTF_RIGHTUP
    elif button == MouseButton.MIDDLE:
        return MOUSEEVENTF_MIDDLEUP
    raise ValueError(f"Unsupported mouse button: {button}")


def get_button_vkey(button: MouseButton) -> int:
    """Map MouseButton to Windows Virtual Key Code."""
    if button == MouseButton.LEFT:
        return VK_LBUTTON
    elif button == MouseButton.RIGHT:
        return VK_RBUTTON
    elif button == MouseButton.MIDDLE:
        return VK_MBUTTON
    raise ValueError(f"Unsupported mouse button: {button}")


def query_windows_observable_button_pressed(button: MouseButton = MouseButton.LEFT) -> bool:
    """Query point-in-time asynchronous button state via GetAsyncKeyState.

    EPISTEMIC LIMITATION NOTE:
    GetAsyncKeyState returns whether the key/button is physically or logically
    down at the instant of polling. It does NOT distinguish synthetic injection
    from human physical input. It is strictly a diagnostic observational signal.
    """
    if sys.platform != "win32":
        return False
    try:
        vkey = get_button_vkey(button)
        state = ctypes.windll.user32.GetAsyncKeyState(vkey)
        return bool(state & 0x8000)
    except Exception:
        return False



# ----------------------------------------------------------------------
# 2. Native Win32 Ctypes Structure Definitions (Windows AMD64)
# ----------------------------------------------------------------------

class MOUSEINPUT(ctypes.Structure):
    """Win32 MOUSEINPUT Structure (AMD64 32 bytes)."""

    _fields_ = [
        ("dx", wintypes.LONG),            # 4 bytes, offset 0
        ("dy", wintypes.LONG),            # 4 bytes, offset 4
        ("mouseData", wintypes.DWORD),     # 4 bytes, offset 8
        ("dwFlags", wintypes.DWORD),       # 4 bytes, offset 12
        ("time", wintypes.DWORD),          # 4 bytes, offset 16
        ("dwExtraInfo", ctypes.c_uint64),  # 8 bytes, offset 24 (4 bytes padding between time & dwExtraInfo)
    ]


class KEYBDINPUT(ctypes.Structure):
    """Win32 KEYBDINPUT Structure (AMD64 24 bytes, 32 bytes aligned)."""

    _fields_ = [
        ("wVk", wintypes.WORD),            # 2 bytes, offset 0
        ("wScan", wintypes.WORD),          # 2 bytes, offset 2
        ("dwFlags", wintypes.DWORD),       # 4 bytes, offset 4
        ("time", wintypes.DWORD),          # 4 bytes, offset 8
        ("dwExtraInfo", ctypes.c_uint64),  # 8 bytes, offset 16 (4 bytes padding between time & dwExtraInfo)
    ]


class HARDWAREINPUT(ctypes.Structure):
    """Win32 HARDWAREINPUT Structure (AMD64 8 bytes)."""

    _fields_ = [
        ("uMsg", wintypes.DWORD),          # 4 bytes, offset 0
        ("wParamL", wintypes.WORD),        # 2 bytes, offset 4
        ("wParamH", wintypes.WORD),        # 2 bytes, offset 6
    ]


class _INPUTunion(ctypes.Union):
    """Win32 INPUT union (AMD64 32 bytes)."""

    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    """Win32 INPUT Structure (AMD64 40 bytes)."""

    _fields_ = [
        ("type", wintypes.DWORD),          # 4 bytes, offset 0
        ("union", _INPUTunion),            # 32 bytes, offset 8 (4 bytes padding before union)
    ]


# ----------------------------------------------------------------------
# 3. ABI Validation Models & Logic
# ----------------------------------------------------------------------

class AbiValidationStatus(str, Enum):
    """Win32 SendInput C ABI validation status."""

    ABI_VALID = "ABI_VALID"
    ABI_MISMATCH = "ABI_MISMATCH"
    UNSUPPORTED_PROCESS_ARCHITECTURE = "UNSUPPORTED_PROCESS_ARCHITECTURE"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class AbiValidationResult:
    """Detailed runtime verification result for Win32 SendInput C ABI structures."""

    is_valid: bool
    status: AbiValidationStatus
    platform_system: str
    machine_arch: str
    pointer_width_bytes: int
    sizeof_mouseinput: int
    sizeof_input: int
    offset_dx: int
    offset_dwflags: int
    offset_dwextrainfo: int
    offset_input_union: int
    is_pointer_sized_extrainfo: bool
    error_message: Optional[str] = None
    validation_timestamp_ns: int = 0


def validate_runtime_abi(
    simulated_override: Optional[Dict[str, Any]] = None,
) -> AbiValidationResult:
    """Programmatically inspects and verifies the C ABI layout of ctypes structures."""
    now_ns = time.perf_counter_ns()
    platform_system = sys.platform
    machine_arch = platform.machine()
    pointer_width = ctypes.sizeof(ctypes.c_void_p)

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


class AbiGate:
    """Fail-closed gate ensuring SendInput cannot be invoked on an unvalidated ABI."""

    def __init__(self, validation_result: Optional[AbiValidationResult] = None) -> None:
        self._result = validation_result or validate_runtime_abi()

    @property
    def result(self) -> AbiValidationResult:
        return self._result

    @property
    def is_valid(self) -> bool:
        return self._result.is_valid and self._result.status == AbiValidationStatus.ABI_VALID

    def is_abi_valid(self) -> bool:
        return self.is_valid

    def require_abi_valid(self) -> AbiValidationResult:
        if not self.is_valid:
            raise RuntimeError(
                f"Win32 SendInput ABI validation failed closed: {self._result.status.value} "
                f"({self._result.error_message})"
            )
        return self._result


# ----------------------------------------------------------------------
# 4. Display Topology Models
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class VirtualDesktopMetrics:
    """Raw physical virtual desktop display metrics from Win32."""

    x_origin: int
    y_origin: int
    width: int
    height: int
    is_valid: bool
    timestamp_ns: int

    @property
    def right(self) -> int:
        return self.x_origin + self.width

    @property
    def bottom(self) -> int:
        return self.y_origin + self.height

    def contains_point(self, x: int, y: int) -> bool:
        return self.x_origin <= x < self.right and self.y_origin <= y < self.bottom


@dataclass(frozen=True)
class VirtualDesktopTopologyIdentity:
    """Stable structural display topology fingerprint."""

    origin_x: int
    origin_y: int
    width: int
    height: int
    monitor_count: int

    def matches(self, other: "VirtualDesktopTopologyIdentity") -> bool:
        return (
            self.origin_x == other.origin_x
            and self.origin_y == other.origin_y
            and self.width == other.width
            and self.height == other.height
            and self.monitor_count == other.monitor_count
        )


def query_virtual_desktop_metrics() -> VirtualDesktopMetrics:
    """Query live virtual desktop screen geometry via Win32 GetSystemMetrics."""
    if sys.platform != "win32":
        return VirtualDesktopMetrics(
            x_origin=0,
            y_origin=0,
            width=1920,
            height=1080,
            is_valid=True,
            timestamp_ns=time.perf_counter_ns(),
        )

    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    is_valid = (w > 0 and h > 0)
    return VirtualDesktopMetrics(
        x_origin=x,
        y_origin=y,
        width=w,
        height=h,
        is_valid=is_valid,
        timestamp_ns=time.perf_counter_ns(),
    )


def query_topology_identity() -> VirtualDesktopTopologyIdentity:
    """Query structural topology identity for mutation detection."""
    metrics = query_virtual_desktop_metrics()
    monitor_count = 1
    if sys.platform == "win32":
        SM_CMONITORS = 80
        cnt = ctypes.windll.user32.GetSystemMetrics(SM_CMONITORS)
        if cnt > 0:
            monitor_count = cnt

    return VirtualDesktopTopologyIdentity(
        origin_x=metrics.x_origin,
        origin_y=metrics.y_origin,
        width=metrics.width,
        height=metrics.height,
        monitor_count=monitor_count,
    )


# ----------------------------------------------------------------------
# 8. Desktop Session & Thread Attachment Safety
# ----------------------------------------------------------------------

DESKTOP_READOBJECTS = 0x0001
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_ACCESS_MASK = 0x01FF  # Full desktop rights for interactive workstation session


from contextlib import contextmanager
from typing import Generator


@contextmanager
def attached_to_input_desktop() -> Generator[bool, None, None]:
    """Temporarily attach calling thread to interactive input desktop and restore upon exit.

    Preserves the thread's original desktop so that modern UWP window enumeration
    continues to function cleanly across all thread pool worker invocations.
    """
    if sys.platform != "win32":
        yield False
        return

    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    h_orig = u32.GetThreadDesktop(k32.GetCurrentThreadId())
    h_input = u32.OpenInputDesktop(0, False, DESKTOP_ACCESS_MASK)
    attached = False
    if h_input:
        attached = bool(u32.SetThreadDesktop(h_input))

    try:
        yield attached
    finally:
        if attached and h_orig:
            try:
                u32.SetThreadDesktop(h_orig)
            except Exception:
                pass
        if h_input:
            try:
                u32.CloseDesktop(h_input)
            except Exception:
                pass


def ensure_thread_input_desktop() -> bool:
    """Verify that the interactive desktop is accessible to the worker thread."""
    if sys.platform != "win32":
        return False
    try:
        u32 = ctypes.windll.user32
        h_desktop = u32.OpenInputDesktop(0, False, DESKTOP_ACCESS_MASK)
        if h_desktop:
            u32.CloseDesktop(h_desktop)
            return True
    except Exception:
        pass
    return sys.platform == "win32"

