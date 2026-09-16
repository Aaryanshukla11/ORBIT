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


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND

    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND

    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL

    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL

    user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    user32.AllowSetForegroundWindow.restype = wintypes.BOOL

    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL

    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND

    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL

    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD


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
        return bool(user32.IsWindow(hwnd))

    @staticmethod
    def ensure_foreground(expected_hwnd: int) -> bool:
        """Forces the window to the foreground using Win32 AttachThreadInput and ShowWindow."""
        if expected_hwnd == 0:
            return True
        if sys.platform != "win32":
            return True
        try:
            if not user32.IsWindow(expected_hwnd):
                return False

            root_hwnd = user32.GetAncestor(expected_hwnd, 2)  # GA_ROOT = 2
            if not root_hwnd or not user32.IsWindow(root_hwnd):
                root_hwnd = expected_hwnd

            SW_RESTORE = 9
            SW_SHOW = 5
            if user32.IsIconic(root_hwnd):
                user32.ShowWindow(root_hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(root_hwnd, SW_SHOW)

            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd == root_hwnd or fg_hwnd == expected_hwnd or TargetFocusValidator.is_foreground(expected_hwnd):
                return True

            cur_thread = kernel32.GetCurrentThreadId()
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
            target_thread = user32.GetWindowThreadProcessId(root_hwnd, None)

            if cur_thread != target_thread and target_thread:
                user32.AttachThreadInput(cur_thread, target_thread, True)
            if cur_thread != fg_thread and fg_thread:
                user32.AttachThreadInput(cur_thread, fg_thread, True)

            # Grant foreground lock bypass
            try:
                user32.AllowSetForegroundWindow(0xFFFFFFFF)  # ASFW_ANY
            except Exception:
                pass

            # Bypass Windows SetForegroundWindow lock using Alt key simulation
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.SetForegroundWindow(root_hwnd)
            user32.BringWindowToTop(root_hwnd)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            if expected_hwnd != root_hwnd and user32.IsWindow(expected_hwnd):
                user32.SetFocus(expected_hwnd)
            else:
                user32.SetFocus(root_hwnd)

            if cur_thread != target_thread and target_thread:
                user32.AttachThreadInput(cur_thread, target_thread, False)
            if cur_thread != fg_thread and fg_thread:
                user32.AttachThreadInput(cur_thread, fg_thread, False)

            time.sleep(0.05)
            return TargetFocusValidator.is_foreground(expected_hwnd)
        except Exception as ex:
            logger.debug("ensure_foreground encountered error: %s", ex)
            return False

    @staticmethod
    def is_foreground(expected_hwnd: int) -> bool:
        """Fast check verifying that the current foreground window matches expected HWND or its hierarchy."""
        if expected_hwnd == 0:
            return True
        if sys.platform != "win32":
            return True
        if not user32.IsWindow(expected_hwnd):
            return False

        root_hwnd = user32.GetAncestor(expected_hwnd, 2)  # GA_ROOT = 2
        if not root_hwnd or not user32.IsWindow(root_hwnd):
            root_hwnd = expected_hwnd

        current_fg = user32.GetForegroundWindow()
        if not current_fg:
            return bool(user32.IsWindowVisible(root_hwnd))

        if current_fg == expected_hwnd or current_fg == root_hwnd:
            return True

        fg_root = user32.GetAncestor(current_fg, 2)
        if not fg_root or not user32.IsWindow(fg_root):
            fg_root = current_fg

        if fg_root == root_hwnd or fg_root == expected_hwnd:
            return True

        # Check process ID match between foreground and target hierarchy
        pid_fg = wintypes.DWORD(0)
        pid_exp = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(fg_root, ctypes.byref(pid_fg))
        user32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(pid_exp))
        if pid_fg.value > 0 and pid_fg.value == pid_exp.value:
            return True

        return False

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
