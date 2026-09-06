"""Win32 C ABI definitions, data structures, and validation gates for Workspace & AppBar."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from typing import Any, Dict, Tuple

from orbit.models.common import BoundingBox

# ============================================================================
# PLATFORM DETECTION & BASE TYPES
# ============================================================================

IS_WINDOWS = sys.platform == "win32"

# 64-bit pointer size check
IS_64BIT = ctypes.sizeof(ctypes.c_void_p) == 8

# DPI Awareness Constants
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

# AppBar Messages (SHAppBarMessage)
ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABM_GETSTATE = 0x00000004
ABM_GETTASKBARPOS = 0x00000005
ABM_ACTIVATE = 0x00000006
ABM_GETAUTOHIDEBAR = 0x00000007
ABM_SETAUTOHIDEBAR = 0x00000008
ABM_WINDOWPOSCHANGED = 0x00000009
ABM_SETSTATE = 0x0000000A

# AppBar Edges
ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3

# AppBar Notifications (ABN_*)
ABN_STATECHANGE = 0x00000000
ABN_POSCHANGED = 0x00000001
ABN_FULLSCREENAPP = 0x00000002
ABN_WINDOWARRANGE = 0x00000003

# System Parameters Info
SPI_GETWORKAREA = 0x0030
SPI_SETWORKAREA = 0x002F
SPIF_SENDCHANGE = 0x0002
SPIF_UPDATEINIFILE = 0x0001

# Window Styles & Flags
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOZORDER = 0x0004
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)

WM_USER = 0x0400
WM_APPBAR_CALLBACK = WM_USER + 101

# Virtual Screen & Monitor System Metrics
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CMONITORS = 80

# Monitor Flags & Constants
MONITORINFOF_PRIMARY = 0x00000001
MONITOR_DEFAULTTONULL = 0x00000000
MONITOR_DEFAULTTOPRIMARY = 0x00000001
MONITOR_DEFAULTTONEAREST = 0x00000002

# Monitor DPI Types (GetDpiForMonitor)
MDT_EFFECTIVE_DPI = 0
MDT_ANGULAR_DPI = 1
MDT_RAW_DPI = 2
MDT_DEFAULT = MDT_EFFECTIVE_DPI


# ============================================================================
# CTYPES STRUCTURE DEFINITIONS (AMD64 64-BIT ALIGNED)
# ============================================================================

class RECT(wintypes.RECT):
    """Win32 RECT structure (16 bytes)."""

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def to_dict(self) -> Dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }

    def to_bounding_box(self) -> BoundingBox:
        return BoundingBox(
            left=self.left,
            top=self.top,
            width=max(1, self.width),
            height=max(1, self.height),
        )

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def __repr__(self) -> str:
        return f"RECT(left={self.left}, top={self.top}, right={self.right}, bottom={self.bottom}, width={self.width}, height={self.height})"


class APPBARDATA(ctypes.Structure):
    """Win32 APPBARDATA structure (48 bytes on AMD64)."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", RECT),
        ("lParam", wintypes.LPARAM),
    ]


class MONITORINFOEXW(ctypes.Structure):
    """Win32 MONITORINFOEXW structure (104 bytes on AMD64)."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


# ============================================================================
# ABI VALIDATION GATE
# ============================================================================

def validate_workspace_abi() -> Dict[str, Any]:
    """Inspect and validate Win32 AMD64 structure sizes, offsets, and pointer widths.

    Returns diagnostic report confirming ABI correctness.
    """
    rect_size = ctypes.sizeof(RECT)
    appbar_size = ctypes.sizeof(APPBARDATA)
    moninfo_size = ctypes.sizeof(MONITORINFOEXW)
    ptr_size = ctypes.sizeof(ctypes.c_void_p)

    # Offset checks
    appbar_offsets = {
        "cbSize": APPBARDATA.cbSize.offset,
        "hWnd": APPBARDATA.hWnd.offset,
        "uCallbackMessage": APPBARDATA.uCallbackMessage.offset,
        "uEdge": APPBARDATA.uEdge.offset,
        "rc": APPBARDATA.rc.offset,
        "lParam": APPBARDATA.lParam.offset,
    }

    moninfo_offsets = {
        "cbSize": MONITORINFOEXW.cbSize.offset,
        "rcMonitor": MONITORINFOEXW.rcMonitor.offset,
        "rcWork": MONITORINFOEXW.rcWork.offset,
        "dwFlags": MONITORINFOEXW.dwFlags.offset,
        "szDevice": MONITORINFOEXW.szDevice.offset,
    }

    # Invariants for 64-bit AMD64:
    # RECT: 16 bytes
    # APPBARDATA: 48 bytes (cbSize=0, hWnd=8, uCallbackMessage=16, uEdge=20, rc=24, lParam=40)
    # MONITORINFOEXW: 104 bytes (cbSize=0, rcMonitor=4, rcWork=20, dwFlags=36, szDevice=40)
    is_valid = (
        rect_size == 16
        and appbar_size == 48
        and moninfo_size == 104
        and ptr_size == 8
        and appbar_offsets["hWnd"] == 8
        and appbar_offsets["rc"] == 24
        and moninfo_offsets["rcMonitor"] == 4
        and moninfo_offsets["szDevice"] == 40
    )

    return {
        "is_valid": is_valid,
        "is_windows": IS_WINDOWS,
        "is_64bit": IS_64BIT,
        "pointer_size_bytes": ptr_size,
        "rect_size_bytes": rect_size,
        "appbardata_size_bytes": appbar_size,
        "monitorinfoexw_size_bytes": moninfo_size,
        "appbardata_offsets": appbar_offsets,
        "monitorinfoexw_offsets": moninfo_offsets,
    }
