"""
Process DPI-Awareness Configuration and Capability Detection for ORBIT Prototype E.
(Per-Monitor DPI Awareness V2 Initialization)

Ensures all Win32 User32 spatial APIs (GetSystemMetrics, GetCursorPos, WindowRects)
operate strictly in unscaled physical device pixels.
"""

import ctypes
from ctypes import wintypes
import time
from typing import Optional

from app_types import DpiAwarenessStatus

# Win32 Constants
# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ((DPI_AWARENESS_CONTEXT)-4)
DPI_AWARENESS_CONTEXT_UNAWARE = -1
DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED = -5

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Setup argtypes & restypes if available
if hasattr(user32, "SetProcessDpiAwarenessContext"):
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL

if hasattr(user32, "GetProcessDpiAwarenessContext"):
    user32.GetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    user32.GetProcessDpiAwarenessContext.restype = ctypes.c_void_p

if hasattr(user32, "AreDpiAwarenessContextsEqual"):
    user32.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.AreDpiAwarenessContextsEqual.restype = wintypes.BOOL


class DpiManager:
    """Singleton manager for process DPI awareness initialization and status querying."""
    _instance: Optional["DpiManager"] = None
    _status: Optional[DpiAwarenessStatus] = None

    def __new__(cls) -> "DpiManager":
        if cls._instance is None:
            cls._instance = super(DpiManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Attempts to configure the process as Per-Monitor V2 DPI aware."""
        if not hasattr(user32, "SetProcessDpiAwarenessContext"):
            self._status = DpiAwarenessStatus(
                is_per_monitor_v2=False,
                raw_context=None,
                init_succeeded=False,
                error_code=-1,
                error_message="SetProcessDpiAwarenessContext API not exported on this Windows version."
            )
            return

        target_context = ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        success = bool(user32.SetProcessDpiAwarenessContext(target_context))
        error_code = 0 if success else kernel32.GetLastError()

        # Query current process DPI context
        current_context = None
        is_pmv2 = False

        if hasattr(user32, "GetProcessDpiAwarenessContext"):
            current_process = kernel32.GetCurrentProcess()
            raw_ctx = user32.GetProcessDpiAwarenessContext(current_process)
            current_context = raw_ctx

            if hasattr(user32, "AreDpiAwarenessContextsEqual"):
                is_pmv2 = bool(user32.AreDpiAwarenessContextsEqual(raw_ctx, target_context))
            else:
                is_pmv2 = (raw_ctx == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        elif success:
            is_pmv2 = True

        # Error code 5 (ERROR_ACCESS_DENIED) often means DPI awareness was already set by process host
        error_msg = None
        if not success:
            if error_code == 5:
                # If already set and is PMv2, treat as success
                if is_pmv2:
                    error_msg = "Context already configured as Per-Monitor V2 by host process."
                else:
                    error_msg = f"DPI awareness context locked by host process (Error code: {error_code})."
            else:
                error_msg = f"SetProcessDpiAwarenessContext failed with Win32 error {error_code}."

        self._status = DpiAwarenessStatus(
            is_per_monitor_v2=is_pmv2,
            raw_context=current_context,
            init_succeeded=success or is_pmv2,
            error_code=error_code,
            error_message=error_msg
        )

    @property
    def status(self) -> DpiAwarenessStatus:
        if self._status is None:
            self._initialize()
        return self._status


def initialize_dpi_awareness() -> DpiAwarenessStatus:
    """Public functional interface for DPI awareness initialization."""
    return DpiManager().status
