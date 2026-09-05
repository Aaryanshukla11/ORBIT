"""
Tiered Target Identity & Focus Verification for Prototype C.
Tracks HWND, Process ID, Process Image Name, Window Title, and validates foreground state
across pre-dispatch, streaming chunk, and post-dispatch phases.
"""

import ctypes
from ctypes import wintypes
import os
import time
from typing import Optional, Tuple
from app_types import TargetContext

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Setup 64-bit Win32 prototypes
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


class TargetTracker:
    """
    Evaluates destination application identity and foreground focus validity.
    """

    def __init__(self, max_focus_check_interval_ms: float = 25.0):
        self.max_focus_check_interval_ms = max_focus_check_interval_ms
        self._last_full_check_time_ns: int = 0

    def capture_target_context(self, hwnd: Optional[int] = None) -> TargetContext:
        """
        Captures target context for the given HWND. If hwnd is None or 0, returns unconstrained context.
        """
        if hwnd is None or hwnd == 0:
            return TargetContext(target_hwnd=0, is_valid=True, process_name="unconstrained", window_title="Global Desktop")

        if not user32.IsWindow(hwnd):
            return TargetContext(target_hwnd=hwnd, is_valid=False, process_name="invalid", window_title="Invalid Window")

        # Window Title
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value

        # Process ID
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_id = pid.value

        # Process Name
        process_name = "unknown"
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
        if h_proc:
            try:
                img_buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, img_buf, ctypes.byref(size)):
                    process_name = os.path.basename(img_buf.value)
            finally:
                kernel32.CloseHandle(h_proc)

        self._last_full_check_time_ns = time.perf_counter_ns()
        return TargetContext(
            target_hwnd=hwnd,
            process_id=process_id,
            process_name=process_name,
            window_title=title,
            is_valid=True,
        )

    def fast_check_foreground(self, expected_hwnd: int) -> bool:
        """
        Ultra-fast (<1 µs) check verifying that the current foreground window matches expected HWND.
        """
        if expected_hwnd == 0:
            return True  # No specific target constraint
        current_fg = user32.GetForegroundWindow()
        return current_fg == expected_hwnd

    def verify_target_identity(self, expected: TargetContext) -> bool:
        """
        Full target identity check validating HWND existence, PID, and foreground state.
        """
        if not expected.is_valid or expected.target_hwnd == 0:
            return True

        current_fg = user32.GetForegroundWindow()
        if current_fg != expected.target_hwnd:
            return False

        if not user32.IsWindow(expected.target_hwnd):
            return False

        # Verify PID has not been recycled
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(expected.target_hwnd, ctypes.byref(pid))
        if pid.value != expected.process_id:
            return False

        self._last_full_check_time_ns = time.perf_counter_ns()
        return True

    def should_perform_full_check(self) -> bool:
        """Returns True if the elapsed time exceeds max_focus_check_interval_ms."""
        elapsed_ms = (time.perf_counter_ns() - self._last_full_check_time_ns) / 1_000_000.0
        return elapsed_ms >= self.max_focus_check_interval_ms
