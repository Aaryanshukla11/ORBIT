"""
Win32 Window Metadata & Hierarchy Tracker for ORBIT Prototype D.
Captures HWND, Process ID, Process Image Name, Window Title, Extended DWM Frame Bounds,
Client Bounds, Z-Order Rank, and Minimized/Maximized states.
"""

import ctypes
from ctypes import wintypes
import os
import time
from typing import List, Optional, Tuple

from app_types import Rect, WindowObservation

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi if hasattr(ctypes.windll, "dwmapi") else None

# Constants
DWMWA_EXTENDED_FRAME_BOUNDS = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Set Win32 function signatures
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL

user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL

if dwmapi and hasattr(dwmapi, "DwmGetWindowAttribute"):
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
    ]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

# Callback for EnumWindows
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL


class WindowTracker:
    """
    Evaluates top-level and foreground window hierarchy and physical visible bounds.
    """

    @staticmethod
    def get_extended_frame_bounds(hwnd: int) -> Rect:
        """
        Queries physical visible window rectangle using DwmGetWindowAttribute (DWMWA_EXTENDED_FRAME_BOUNDS).
        Falls back to standard GetWindowRect if DWM is unavailable.
        """
        if dwmapi and hasattr(dwmapi, "DwmGetWindowAttribute"):
            r = wintypes.RECT()
            hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(wintypes.RECT))
            if hr == 0:
                return Rect(left=r.left, top=r.top, right=r.right, bottom=r.bottom)

        r2 = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r2))
        return Rect(left=r2.left, top=r2.top, right=r2.right, bottom=r2.bottom)

    @staticmethod
    def get_client_bounds(hwnd: int) -> Rect:
        """
        Returns screen-relative physical client area bounds.
        """
        r = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(r)):
            return Rect(left=0, top=0, right=0, bottom=0)
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        return Rect(left=pt.x, top=pt.y, right=pt.x + r.right, bottom=pt.y + r.bottom)

    @staticmethod
    def get_process_info(hwnd: int) -> Tuple[int, str]:
        """Returns (process_id, process_name)."""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_id = pid.value
        process_name = "unknown"

        if process_id > 0:
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
            if h_proc:
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                        process_name = os.path.basename(buf.value)
                finally:
                    kernel32.CloseHandle(h_proc)

        return process_id, process_name

    @classmethod
    def get_window_observation(cls, hwnd: int, z_order_rank: int = 0) -> WindowObservation:
        """Constructs an immutable WindowObservation for a specific HWND."""
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value

        pid, proc_name = cls.get_process_info(hwnd)
        ext_bounds = cls.get_extended_frame_bounds(hwnd)
        client_bounds = cls.get_client_bounds(hwnd)
        is_vis = bool(user32.IsWindowVisible(hwnd))
        is_min = bool(user32.IsIconic(hwnd))
        is_max = bool(user32.IsZoomed(hwnd))
        is_fg = (user32.GetForegroundWindow() == hwnd)

        dpi = 96
        if hasattr(user32, "GetDpiForWindow") and user32.GetDpiForWindow:
            try:
                d = user32.GetDpiForWindow(hwnd)
                if d > 0:
                    dpi = d
            except Exception:
                pass

        return WindowObservation(
            hwnd=hwnd,
            process_id=pid,
            process_name=proc_name,
            window_title=title,
            extended_bounds=ext_bounds,
            client_bounds=client_bounds,
            is_visible=is_vis,
            is_minimized=is_min,
            is_maximized=is_max,
            is_foreground=is_fg,
            z_order_rank=z_order_rank,
            dpi_scaling=round(dpi / 96.0, 2),
        )

    @classmethod
    def get_foreground_window_observation(cls) -> Optional[WindowObservation]:
        """Returns WindowObservation for the current foreground window."""
        hwnd = user32.GetForegroundWindow()
        if hwnd and user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd):
            return cls.get_window_observation(hwnd, z_order_rank=0)
        # Fallback to top-most visible window in Z-order if desktop has no explicit focus
        visible = cls.enumerate_visible_windows()
        return visible[0] if visible else None

    @classmethod
    def enumerate_visible_windows(cls) -> List[WindowObservation]:
        """
        Enumerates all visible top-level windows in Z-order.
        """
        windows: List[WindowObservation] = []
        rank = 0

        def enum_callback(hwnd, lparam):
            nonlocal rank
            if user32.IsWindowVisible(hwnd):
                # Ignore zero-size or off-screen hidden helper windows
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                if (r.right - r.left) > 0 and (r.bottom - r.top) > 0:
                    obs = cls.get_window_observation(hwnd, z_order_rank=rank)
                    windows.append(obs)
                    rank += 1
            return True

        cb = WNDENUMPROC(enum_callback)
        user32.EnumWindows(cb, 0)
        return windows

    get_all_windows = enumerate_visible_windows
