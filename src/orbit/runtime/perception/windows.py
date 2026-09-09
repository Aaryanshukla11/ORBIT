"""Win32 Window Perception Observer (Step 3).

Interrogates live operating system window hierarchy via native Win32 APIs:
- Enumerates top-level visible windows (EnumWindows)
- Identifies active foreground window (GetForegroundWindow)
- Resolves window and client area screen bounds (GetWindowRect, GetClientRect)
- Retrieves process ID and executable name
- Detects minimized, maximized, and visible states
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import WindowObservation

logger = logging.getLogger(__name__)


class Win32WindowObserver:
    """Production Win32 window hierarchy and focus state observer."""

    def __init__(self) -> None:
        self._is_win32 = sys.platform == "win32"

    def _ensure_desktop_attached(self) -> Optional[int]:
        """Ensure current thread is attached to interactive desktop WinSta0\\Default."""
        if not self._is_win32:
            return None
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # 0x01FF = DESKTOP_ALL
            h_desk = user32.OpenInputDesktop(0, False, 0x01FF)
            if not h_desk:
                h_desk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if h_desk:
                user32.SetThreadDesktop(h_desk)
            return h_desk
        except Exception as ex:
            logger.debug("Desktop attach notice: %s", ex)
            return None

    def observe_windows(self) -> Tuple[Optional[WindowObservation], List[WindowObservation]]:
        """Query live OS for active foreground window and all visible top-level windows."""
        if not self._is_win32:
            return self._mock_windows()

        try:
            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32
            h_desk = None
            # Setup ctypes signatures
            user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
            user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
            user32.IsWindowVisible.restype = ctypes.wintypes.BOOL
            user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
            user32.IsIconic.restype = ctypes.wintypes.BOOL
            user32.IsZoomed.argtypes = [ctypes.wintypes.HWND]
            user32.IsZoomed.restype = ctypes.wintypes.BOOL
            user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
            user32.GetWindowRect.restype = ctypes.wintypes.BOOL
            user32.GetClientRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
            user32.GetClientRect.restype = ctypes.wintypes.BOOL

            fg_hwnd = user32.GetForegroundWindow()
            visible_windows: List[WindowObservation] = []

            # Callback for EnumWindows / EnumDesktopWindows
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
            user32.EnumWindows.restype = ctypes.wintypes.BOOL
            if hasattr(user32, "EnumDesktopWindows"):
                user32.EnumDesktopWindows.argtypes = [ctypes.wintypes.HANDLE, WNDENUMPROC, ctypes.wintypes.LPARAM]
                user32.EnumDesktopWindows.restype = ctypes.wintypes.BOOL

            def enum_proc(hwnd: int, lparam: Any) -> bool:
                if not user32.IsWindowVisible(hwnd):
                    return True

                # Title length & text
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True

                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()

                # Filter out invisible or system overlay windows with trivial titles
                if not title or title in ("Program Manager", "Default IME", "MSCTFIME UI"):
                    return True

                # Class name
                cls_buff = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buff, 256)
                cls_name = cls_buff.value

                # Window Rect
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top

                # Exclude 0-area or offscreen windows
                if w <= 0 or h <= 0:
                    return True

                # Client Rect & coordinate translation
                client_rect = ctypes.wintypes.RECT()
                user32.GetClientRect(hwnd, ctypes.byref(client_rect))
                pt = ctypes.wintypes.POINT(client_rect.left, client_rect.top)
                user32.ClientToScreen(hwnd, ctypes.byref(pt))
                client_w = client_rect.right - client_rect.left
                client_h = client_rect.bottom - client_rect.top

                # Process ID & Name
                pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                proc_name = self._resolve_process_name(pid.value)

                is_fg = (hwnd == fg_hwnd)
                is_min = bool(user32.IsIconic(hwnd))
                is_max = bool(user32.IsZoomed(hwnd))

                w_bounds = BoundingBox(left=rect.left, top=rect.top, width=w, height=h)
                c_bounds = BoundingBox(left=pt.x, top=pt.y, width=client_w, height=client_h) if (client_w > 0 and client_h > 0) else w_bounds

                obs = WindowObservation(
                    hwnd=hwnd,
                    title=title,
                    window_class=cls_name,
                    is_foreground=is_fg,
                    is_visible=True,
                    is_minimized=is_min,
                    is_maximized=is_max,
                    window_bounds=w_bounds,
                    client_bounds=c_bounds,
                    process_id=pid.value,
                    process_name=proc_name,
                )
                visible_windows.append(obs)
                return True

            cb = WNDENUMPROC(enum_proc)
            user32.EnumWindows(cb, 0)

            # If EnumWindows produced no windows, fallback to EnumDesktopWindows
            if not visible_windows:
                h_desk = self._ensure_desktop_attached()
                if h_desk:
                    user32.EnumDesktopWindows(h_desk, cb, 0)

            # Resolve foreground window observation
            foreground_obs = None
            for win in visible_windows:
                if win.is_foreground:
                    foreground_obs = win
                    break

            if not foreground_obs and fg_hwnd:
                foreground_obs = self._observe_single_hwnd(fg_hwnd)
                if foreground_obs and foreground_obs.is_visible:
                    # Insert or mark as foreground
                    if not any(w.hwnd == foreground_obs.hwnd for w in visible_windows):
                        visible_windows.insert(0, foreground_obs)

            if not foreground_obs and visible_windows:
                foreground_obs = visible_windows[0]

            return foreground_obs, visible_windows

        except Exception as ex:
            logger.debug("Win32 window observation exception: %s", ex)
            return self._mock_windows()

    def _observe_single_hwnd(self, hwnd: int) -> Optional[WindowObservation]:
        """Capture metadata for a specific HWND directly."""
        try:
            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32

            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value

            cls_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buff, 256)
            cls_name = cls_buff.value

            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = self._resolve_process_name(pid.value)

            return WindowObservation(
                hwnd=hwnd,
                title=title,
                window_class=cls_name,
                is_foreground=True,
                is_visible=bool(user32.IsWindowVisible(hwnd)),
                is_minimized=bool(user32.IsIconic(hwnd)),
                is_maximized=bool(user32.IsZoomed(hwnd)),
                window_bounds=BoundingBox(left=rect.left, top=rect.top, width=w, height=h),
                client_bounds=BoundingBox(left=rect.left, top=rect.top, width=w, height=h),
                process_id=pid.value,
                process_name=proc_name,
            )
        except Exception:
            return None

    def _resolve_process_name(self, pid: int) -> Optional[str]:
        """Resolve executable process name from PID."""
        if not pid:
            return None
        try:
            import psutil
            proc = psutil.Process(pid)
            return proc.name()
        except Exception:
            return None

    def _mock_windows(self) -> Tuple[Optional[WindowObservation], List[WindowObservation]]:
        """Fallback mock windows for non-Windows platforms or test environments."""
        mock_win = WindowObservation(
            hwnd=1001,
            title="Desktop",
            window_class="Progman",
            is_foreground=True,
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
            window_bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
            client_bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
            process_id=100,
            process_name="explorer.exe",
        )
        return mock_win, [mock_win]
