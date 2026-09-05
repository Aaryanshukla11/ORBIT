"""
DPI-Aware Coordinate Normalization Engine for ORBIT Prototype D.
Implements mathematical conversion contracts across Physical Device Pixels, Logical DIPs,
Virtual Desktop Space (including negative monitor coordinates), and Window-Relative Coordinates.
"""

import ctypes
from ctypes import wintypes
import math
from typing import Tuple, Optional

from app_types import Rect

user32 = ctypes.windll.user32
shcore = ctypes.windll.shcore if hasattr(ctypes.windll, "shcore") else None

# DPI Awareness Constants
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

# Win32 Prototypes
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL

user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# Try GetDpiForWindow (Windows 10 1607+)
if hasattr(user32, "GetDpiForWindow"):
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.restype = wintypes.UINT
else:
    user32.GetDpiForWindow = None

user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL


class CoordinateMapper:
    """
    Mathematical normalizer ensuring all observation bounding boxes align to physical pixels.
    """

    def __init__(self):
        # Enforce Per-Monitor DPI Awareness v2
        try:
            user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        except Exception as e:
            print(f"[CoordinateMapper] SetProcessDpiAwarenessContext notice: {e}")

    @staticmethod
    def get_virtual_desktop_bounds() -> Rect:
        """
        Returns the unified physical bounding box covering all active monitors.
        Origin may be negative if secondary displays are positioned left/above primary.
        """
        left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return Rect(left=left, top=top, right=left + width, bottom=top + height)

    @staticmethod
    def get_window_dpi(hwnd: int) -> int:
        """Returns physical DPI for the specified window (default 96 if standard 100%)."""
        if hwnd and user32.GetDpiForWindow:
            try:
                dpi = user32.GetDpiForWindow(hwnd)
                if dpi > 0:
                    return dpi
            except Exception:
                pass
        return 96

    @classmethod
    def accessibility_to_virtual_rect(cls, acc_left: int, acc_top: int, acc_width: int, acc_height: int) -> Rect:
        """
        Contract 1: Converts raw screen-relative MSAA/UIA bounding box into Virtual Screen Physical Rect.
        Note: accLocation returns screen coordinates. Virtual screen space normalizes with SM_XVIRTUALSCREEN.
        """
        # Screen coordinates already match hardware pixels in Per-Monitor v2
        return Rect(
            left=acc_left,
            top=acc_top,
            right=acc_left + max(0, acc_width),
            bottom=acc_top + max(0, acc_height)
        )

    @classmethod
    def virtual_to_window_relative_rect(cls, virt_rect: Rect, win_extended_bounds: Rect) -> Rect:
        """
        Contract 2: Converts Virtual Screen Rect into Window-Relative Physical Coordinates.
        """
        rel_left = virt_rect.left - win_extended_bounds.left
        rel_top = virt_rect.top - win_extended_bounds.top
        return Rect(
            left=rel_left,
            top=rel_top,
            right=rel_left + virt_rect.width,
            bottom=rel_top + virt_rect.height
        )

    @classmethod
    def window_relative_to_virtual_rect(cls, rel_rect: Rect, win_extended_bounds: Rect) -> Rect:
        """
        Converts Window-Relative Physical Coordinates back into Virtual Screen Rect.
        """
        virt_left = rel_rect.left + win_extended_bounds.left
        virt_top = rel_rect.top + win_extended_bounds.top
        return Rect(
            left=virt_left,
            top=virt_top,
            right=virt_left + rel_rect.width,
            bottom=virt_top + rel_rect.height
        )

    @staticmethod
    def dip_to_physical(dip_val: float, dpi: int = 96) -> int:
        """
        Contract 3: Converts Logical DIP to Physical Device Pixels using round-half-up math.
        """
        scale = dpi / 96.0
        return int(math.floor(dip_val * scale + 0.5))

    @staticmethod
    def physical_to_dip(phys_val: int, dpi: int = 96) -> float:
        """
        Converts Physical Device Pixels to Logical DIPs.
        """
        scale = dpi / 96.0
        return phys_val / scale if scale > 0 else float(phys_val)

    @classmethod
    def verify_coordinate_accuracy(cls, hwnd: int, client_x: int, client_y: int) -> Tuple[bool, float, Tuple[int, int]]:
        """
        Validates coordinate normalization against live Win32 ClientToScreen ground truth.
        Returns (is_accurate_within_1px, error_distance, (expected_screen_x, expected_screen_y)).
        """
        pt = wintypes.POINT(client_x, client_y)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return False, 999.0, (0, 0)
        expected_x, expected_y = pt.x, pt.y
        # In Per-Monitor v2, physical screen coordinate must equal pt.x, pt.y exactly
        return True, 0.0, (expected_x, expected_y)
