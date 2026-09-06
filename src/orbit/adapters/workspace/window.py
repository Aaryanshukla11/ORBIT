"""Native Win32 Window lifecycle management and window procedure routing for AppBar container."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from orbit.adapters.workspace.abi import (
    HWND_NOTOPMOST,
    HWND_TOPMOST,
    IS_WINDOWS,
    RECT,
    SWP_NOACTIVATE,
    SWP_NOZORDER,
    SWP_SHOWWINDOW,
    WM_APPBAR_CALLBACK,
    WS_EX_TOPMOST,
    WS_POPUP,
    WS_VISIBLE,
)
from orbit.models.common import BoundingBox

logger = logging.getLogger(__name__)

# Window Procedure callback type
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    """Win32 WNDCLASSEXW structure."""

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


class Win32WindowGateway:
    """Platform gateway dispatching native User32/Kernel32 windowing APIs with explicit AMD64 ABI."""

    def __init__(self) -> None:
        if IS_WINDOWS:
            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32

            # Configure explicit signatures
            self._user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
            self._user32.RegisterClassExW.restype = wintypes.ATOM

            self._user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
            self._user32.UnregisterClassW.restype = wintypes.BOOL

            self._user32.CreateWindowExW.argtypes = [
                wintypes.DWORD,
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                wintypes.DWORD,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.HWND,
                wintypes.HMENU,
                wintypes.HINSTANCE,
                wintypes.LPVOID,
            ]
            self._user32.CreateWindowExW.restype = wintypes.HWND

            self._user32.DestroyWindow.argtypes = [wintypes.HWND]
            self._user32.DestroyWindow.restype = wintypes.BOOL

            self._user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            self._user32.SetWindowPos.restype = wintypes.BOOL

            self._user32.GetWindowRect.argtypes = [wintypes.HWND, wintypes.LPRECT]
            self._user32.GetWindowRect.restype = wintypes.BOOL

            self._user32.IsWindow.argtypes = [wintypes.HWND]
            self._user32.IsWindow.restype = wintypes.BOOL

            self._user32.DefWindowProcW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            self._user32.DefWindowProcW.restype = ctypes.c_longlong

            self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            self._kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

            self._kernel32.GetLastError.argtypes = []
            self._kernel32.GetLastError.restype = wintypes.DWORD
        else:
            self._user32 = None
            self._kernel32 = None

    def get_module_handle(self) -> int:
        if not IS_WINDOWS or self._kernel32 is None:
            return 0
        return self._kernel32.GetModuleHandleW(None) or 0

    def register_class(self, wc: WNDCLASSEXW) -> int:
        if not IS_WINDOWS or self._user32 is None:
            return 0
        return self._user32.RegisterClassExW(ctypes.byref(wc)) or 0

    def unregister_class(self, class_name: str, h_instance: int) -> bool:
        if not IS_WINDOWS or self._user32 is None:
            return False
        return bool(self._user32.UnregisterClassW(class_name, h_instance))

    def create_window(
        self,
        ex_style: int,
        class_name: str,
        window_name: str,
        style: int,
        x: int,
        y: int,
        w: int,
        h: int,
        h_instance: int,
    ) -> int:
        if not IS_WINDOWS or self._user32 is None:
            return 0
        return int(
            self._user32.CreateWindowExW(
                ex_style,
                class_name,
                window_name,
                style,
                x,
                y,
                w,
                h,
                None,
                None,
                h_instance,
                None,
            )
            or 0
        )

    def destroy_window(self, hwnd: int) -> bool:
        if not IS_WINDOWS or self._user32 is None:
            return False
        return bool(self._user32.DestroyWindow(hwnd))

    def set_window_pos(
        self,
        hwnd: int,
        hwnd_insert_after: int,
        x: int,
        y: int,
        w: int,
        h: int,
        flags: int,
    ) -> bool:
        if not IS_WINDOWS or self._user32 is None:
            return False
        return bool(self._user32.SetWindowPos(hwnd, hwnd_insert_after, x, y, w, h, flags))

    def get_window_rect(self, hwnd: int) -> Optional[RECT]:
        if not IS_WINDOWS or self._user32 is None:
            return None
        rc = RECT()
        if self._user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return rc
        return None

    def is_window(self, hwnd: int) -> bool:
        if not IS_WINDOWS or self._user32 is None:
            return False
        return bool(self._user32.IsWindow(hwnd))

    def def_window_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if not IS_WINDOWS or self._user32 is None:
            return 0
        return int(self._user32.DefWindowProcW(hwnd, msg, wparam, lparam))

    def get_last_error(self) -> int:
        if not IS_WINDOWS or self._kernel32 is None:
            return 0
        return int(self._kernel32.GetLastError())


class NativeWorkspaceWindow:
    """Manages the lifecycle, positioning, and callback routing of a native Win32 AppBar window."""

    def __init__(
        self,
        window_title: str = "ORBIT Workspace Window",
        callback_message: int = WM_APPBAR_CALLBACK,
        gateway: Optional[Win32WindowGateway] = None,
    ) -> None:
        self._window_title = window_title
        self._callback_message = callback_message
        self._gateway = gateway or Win32WindowGateway()

        self._hwnd: int = 0
        self._class_atom: int = 0
        self._class_name: str = f"OrbitWorkspaceWindow_{uuid4().hex[:8]}"
        self._h_instance: int = 0
        self._is_created: bool = False
        self._current_rect: RECT = RECT()

        # Hold a strong reference to the WNDPROC callback to prevent Python garbage collection
        self._wnd_proc_callback = WNDPROC(self._window_proc_handler)
        self._notification_listeners: List[Callable[[int, int], None]] = []
        self._recorded_notifications: List[Dict[str, Any]] = []

    @property
    def hwnd(self) -> int:
        return self._hwnd

    @property
    def class_name(self) -> str:
        return self._class_name

    @property
    def is_created(self) -> bool:
        return self._is_created and (self._gateway.is_window(self._hwnd) if self._hwnd else False)

    @property
    def callback_message(self) -> int:
        return self._callback_message

    def _window_proc_handler(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """Native Window Procedure handling WM_APPBAR_CALLBACK and delegating to DefWindowProc."""
        if msg == self._callback_message:
            notification_code = int(wparam)
            self._recorded_notifications.append({
                "notification_code": notification_code,
                "lparam": int(lparam),
            })
            for listener in list(self._notification_listeners):
                try:
                    listener(notification_code, int(lparam))
                except Exception as ex:
                    logger.error("Error in AppBar notification listener: %s", ex)
            return 0

        return self._gateway.def_window_proc(hwnd, msg, wparam, lparam)

    def create(
        self,
        bounds: Optional[BoundingBox] = None,
        topmost: bool = True,
        visible: bool = True,
    ) -> int:
        """Register the window class and create the native top-level window."""
        if self._hwnd and self.is_created:
            return self._hwnd

        self._h_instance = self._gateway.get_module_handle()

        # 1. Register Window Class
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wnd_proc_callback
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = self._h_instance
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = self._class_name
        wc.hIconSm = None

        atom = self._gateway.register_class(wc)
        if not atom:
            err = self._gateway.get_last_error()
            raise RuntimeError(f"Failed to register Win32 window class '{self._class_name}' (LastError: {err})")
        self._class_atom = atom

        # 2. Window Position & Styles
        ex_style = WS_EX_TOPMOST if topmost else 0
        style = WS_POPUP
        if visible:
            style |= WS_VISIBLE

        x = bounds.left if bounds else 0
        y = bounds.top if bounds else 0
        w = bounds.width if bounds else 400
        h = bounds.height if bounds else 600

        hwnd = self._gateway.create_window(
            ex_style=ex_style,
            class_name=self._class_name,
            window_name=self._window_title,
            style=style,
            x=x,
            y=y,
            w=w,
            h=h,
            h_instance=self._h_instance,
        )

        if not hwnd:
            err = self._gateway.get_last_error()
            # Clean up registered class on creation failure
            self._gateway.unregister_class(self._class_name, self._h_instance)
            self._class_atom = 0
            raise RuntimeError(f"Failed to create native Win32 window (LastError: {err})")

        self._hwnd = hwnd
        self._is_created = True
        self._current_rect = RECT(x, y, x + w, y + h)
        logger.info("Created native workspace window (HWND=%d, class=%s)", self._hwnd, self._class_name)
        return self._hwnd

    def set_position(
        self,
        rect: RECT,
        topmost: bool = True,
        activate: bool = False,
    ) -> bool:
        """Position and resize the native window matching negotiated bounds."""
        if not self._hwnd or not self._is_created:
            raise RuntimeError("Cannot position window: HWND is not created")

        insert_after = HWND_TOPMOST if topmost else HWND_NOTOPMOST
        flags = SWP_SHOWWINDOW
        if not activate:
            flags |= SWP_NOACTIVATE
        if not topmost:
            flags |= SWP_NOZORDER

        ok = self._gateway.set_window_pos(
            hwnd=self._hwnd,
            hwnd_insert_after=insert_after,
            x=rect.left,
            y=rect.top,
            w=rect.width,
            h=rect.height,
            flags=flags,
        )

        if ok:
            self._current_rect = rect
            logger.debug("Repositioned workspace window to %s", rect)
        else:
            err = self._gateway.get_last_error()
            logger.error("SetWindowPos failed on HWND=%d (LastError=%d)", self._hwnd, err)

        return ok

    def get_bounds(self) -> Optional[RECT]:
        """Query live physical bounds of window."""
        if not self._hwnd or not self._is_created:
            return None
        return self._gateway.get_window_rect(self._hwnd)

    def destroy(self) -> bool:
        """Destroy the native window and unregister its class."""
        if not self._hwnd and not self._class_atom:
            return True

        destroyed_ok = True
        if self._hwnd:
            destroyed_ok = self._gateway.destroy_window(self._hwnd)
            self._hwnd = 0

        unregistered_ok = True
        if self._class_atom and self._class_name and self._h_instance:
            unregistered_ok = self._gateway.unregister_class(self._class_name, self._h_instance)
            self._class_atom = 0

        self._is_created = False
        logger.info("Destroyed native workspace window (class=%s)", self._class_name)
        return destroyed_ok and unregistered_ok

    def add_notification_listener(self, callback: Callable[[int, int], None]) -> None:
        if callback not in self._notification_listeners:
            self._notification_listeners.append(callback)

    def remove_notification_listener(self, callback: Callable[[int, int], None]) -> None:
        if callback in self._notification_listeners:
            self._notification_listeners.remove(callback)

    def get_recorded_notifications(self) -> List[Dict[str, Any]]:
        return list(self._recorded_notifications)
