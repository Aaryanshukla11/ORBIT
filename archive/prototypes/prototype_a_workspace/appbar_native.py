"""
Win32 AppBar Native API bindings for Prototype A (Workspace & Docking).
Handles AppBar registration, positioning, message dispatching, and DPI awareness
with explicit 64-bit Win32 argtypes/restype specifications.
"""

import ctypes
from ctypes import wintypes
import sys
from dataclasses import dataclass
from typing import Tuple, Optional

# Load DLLs
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

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


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def to_dict(self) -> dict:
        return {"left": self.left, "top": self.top, "right": self.right, "bottom": self.bottom, "width": self.width, "height": self.height}

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def __repr__(self) -> str:
        return f"RECT(left={self.left}, top={self.top}, right={self.right}, bottom={self.bottom}, width={self.width}, height={self.height})"


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", RECT),
        ("lParam", wintypes.LPARAM),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


def default_wnd_proc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


wnd_proc_callback = WNDPROC(default_wnd_proc)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


# Setup explicit 64-bit API signatures
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL

user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.SystemParametersInfoW.restype = wintypes.BOOL

shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
shell32.SHAppBarMessage.restype = ctypes.c_uint64

user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND

user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_longlong

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.UnregisterClassW.restype = wintypes.BOOL

user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL


@dataclass
class MonitorInfo:
    hMonitor: int
    rect: RECT
    work_rect: RECT
    is_primary: bool
    dpi: int


def set_dpi_awareness():
    """Configures Per-Monitor DPI Awareness v2 for the process."""
    try:
        user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except Exception as e:
        print(f"[AppBar] Warning: SetProcessDpiAwarenessContext failed: {e}")


def get_desktop_workarea() -> RECT:
    """Gets the primary monitor's current Windows Work Area."""
    rect = RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect


def get_screen_dimensions() -> Tuple[int, int]:
    """Gets screen width and height in pixels from current work area or metrics."""
    w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return w, h


def enum_monitors() -> list[MonitorInfo]:
    """Enumerates all active display monitors with DPI and work area."""
    monitors = []

    def monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))

        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        try:
            ctypes.windll.shcore.GetDpiForMonitor(hMonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
            dpi = dpi_x.value
        except Exception:
            dpi = 96

        monitors.append(
            MonitorInfo(
                hMonitor=hMonitor,
                rect=info.rcMonitor,
                work_rect=info.rcWork,
                is_primary=bool(info.dwFlags & 1),
                dpi=dpi,
            )
        )
        return True

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
    )
    user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(monitor_enum_proc), 0)
    return monitors


class Win32AppBar:
    """
    Manages Win32 Application Desktop Toolbar (AppBar) lifecycle.
    Implements registration, positioning, edge docking, and clean unregistration.
    """

    def __init__(self, hwnd: int, callback_msg: int = WM_APPBAR_CALLBACK):
        self.hwnd = hwnd
        self.callback_msg = callback_msg
        self.is_registered = False
        self.current_edge: Optional[int] = None
        self.current_rect = RECT()

    def register(self) -> bool:
        """Registers the window as an AppBar."""
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd
        abd.uCallbackMessage = self.callback_msg

        shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
        self.is_registered = True
        return True

    def unregister(self) -> bool:
        """Unregisters the window as an AppBar, restoring original work area."""
        if not self.is_registered:
            return True
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd

        shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        self.is_registered = False
        self.current_edge = None
        return True

    def set_dock_position(
        self,
        edge: int = ABE_RIGHT,
        target_width_ratio: float = 0.25,
        min_width: int = 380,
        max_width: int = 720,
    ) -> RECT:
        """
        Calculates dock bounds and requests shell positioning via ABM_QUERYPOS & ABM_SETPOS.
        Returns the finalized assigned RECT.
        """
        if not self.is_registered:
            self.register()

        screen_w, screen_h = get_screen_dimensions()
        desired_width = int(screen_w * target_width_ratio)
        clamped_width = max(min_width, min(max_width, desired_width))

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd
        abd.uEdge = edge

        # Initialize requested bounds
        if edge == ABE_RIGHT:
            abd.rc.left = screen_w - clamped_width
            abd.rc.right = screen_w
            abd.rc.top = 0
            abd.rc.bottom = screen_h
        elif edge == ABE_LEFT:
            abd.rc.left = 0
            abd.rc.right = clamped_width
            abd.rc.top = 0
            abd.rc.bottom = screen_h
        else:
            raise ValueError("Only ABE_LEFT and ABE_RIGHT are supported for ORBIT.")

        # Query Windows Shell for available space
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))

        # Re-apply requested width constraint to proposed rect
        if edge == ABE_RIGHT:
            abd.rc.left = abd.rc.right - clamped_width
        elif edge == ABE_LEFT:
            abd.rc.right = abd.rc.left + clamped_width

        # Commit final position to Windows Shell
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))

        self.current_edge = edge
        self.current_rect = abd.rc

        # Reposition the actual OS window to match agreed bounds
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            abd.rc.left,
            abd.rc.top,
            abd.rc.width,
            abd.rc.height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

        return abd.rc
