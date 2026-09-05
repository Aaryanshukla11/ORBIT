"""Target Identity, Window Lifecycle, and Foreground Focus Validation for ORBIT Keyboard."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import logging
import os
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TargetContext:
    target_hwnd: int = 0
    process_id: int = 0
    process_name: str = ""
    window_title: str = ""
    is_valid: bool = False


class TargetFocusValidator:
    """Evaluates target application existence and foreground focus validity."""

    def __init__(self, max_focus_check_interval_ms: float = 25.0) -> None:
        self.max_focus_check_interval_ms = max_focus_check_interval_ms
        self._last_full_check_time_ns: int = 0

    @staticmethod
    def is_window_alive(hwnd: int) -> bool:
        """Validates whether the HWND is still a valid Win32 window via user32.IsWindow."""
        if hwnd == 0:
            return True
        if sys.platform != "win32":
            return True
        return bool(ctypes.windll.user32.IsWindow(hwnd))

    @staticmethod
    def is_foreground(expected_hwnd: int) -> bool:
        """Fast check verifying that the current foreground window matches expected HWND."""
        if expected_hwnd == 0:
            return True
        if sys.platform != "win32":
            return True
        current_fg = ctypes.windll.user32.GetForegroundWindow()
        return current_fg == expected_hwnd

    def capture_target_context(self, hwnd: Optional[int] = None) -> TargetContext:
        """Captures target context for the given HWND."""
        if hwnd is None or hwnd == 0:
            return TargetContext(target_hwnd=0, is_valid=True, process_name="unconstrained", window_title="Global Desktop")

        if sys.platform != "win32":
            return TargetContext(target_hwnd=hwnd, is_valid=True, process_name="non-win32", window_title="Non-Win32")

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

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
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
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
