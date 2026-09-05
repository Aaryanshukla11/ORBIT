"""
Low-Level Input Monitor for Prototype B.
Installs WH_MOUSE_LL and WH_KEYBOARD_LL hooks on a dedicated thread, captures
physical vs injected inputs with extraInfo signatures, and dispatches to high-speed queue.
"""

import ctypes
from ctypes import wintypes
import threading
import queue
import time
from typing import Callable, Optional, List

from app_types import InputEvent, InputSource

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Hook Constants
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

# Mouse Messages
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

# Keyboard Messages
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# Injected Flags
LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002
LLKHF_INJECTED = 0x00000010
LLKHF_LOWER_IL_INJECTED = 0x00000002

# ORBIT Tag Signature passed in dwExtraInfo
ORBIT_EXTRA_INFO_SIGNATURE = 0x08B17001

# Hook callback types
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


# Setup explicit 64-bit Win32 prototypes
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_longlong

user32.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

WM_QUIT = 0x0012


class InputMonitor:
    """
    Background hook monitor capturing all physical and synthetic OS input events.
    Dispatches non-blocking events to subscribers.
    """

    def __init__(self):
        self._mouse_hook = None
        self._keyboard_hook = None
        self._hook_thread = None
        self._thread_id = None
        self._is_running = False
        self._event_counter = 0
        self.event_queue: queue.Queue[InputEvent] = queue.Queue(maxsize=10000)
        self._callbacks: List[Callable[[InputEvent], None]] = []

        # Keep references to ctypes callbacks to avoid garbage collection
        self._mouse_proc = HOOKPROC(self._low_level_mouse_handler)
        self._keyboard_proc = HOOKPROC(self._low_level_keyboard_handler)

    def register_callback(self, callback: Callable[[InputEvent], None]):
        """Adds an event subscriber callback."""
        self._callbacks.append(callback)

    def start(self):
        """Starts the input monitor on a dedicated background message pump thread."""
        if self._is_running:
            return

        self._is_running = True
        ready_event = threading.Event()

        def hook_thread_proc():
            self._thread_id = kernel32.GetCurrentThreadId()
            h_inst = kernel32.GetModuleHandleW(None)

            self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, h_inst, 0)
            self._keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._keyboard_proc, h_inst, 0)

            if not self._mouse_hook or not self._keyboard_hook:
                print(f"[InputMonitor] Error: Failed to set hooks. Mouse={bool(self._mouse_hook)}, Kbd={bool(self._keyboard_hook)}")
                ready_event.set()
                return

            ready_event.set()

            # Win32 Message Loop required for low-level hooks
            msg = (wintypes.DWORD * 12)()
            while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                pass

            # Cleanup hooks on thread exit
            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
                self._mouse_hook = None
            if self._keyboard_hook:
                user32.UnhookWindowsHookEx(self._keyboard_hook)
                self._keyboard_hook = None

        self._hook_thread = threading.Thread(target=hook_thread_proc, name="OrbitInputMonitorThread", daemon=True)
        self._hook_thread.start()
        ready_event.wait(timeout=2.0)
        print("[InputMonitor] Low-level hooks active.")

    def stop(self):
        """Stops the input monitor and uninstalls hooks."""
        if not self._is_running:
            return
        self._is_running = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._hook_thread:
            self._hook_thread.join(timeout=1.0)
        print("[InputMonitor] Hooks uninstalled.")

    def _low_level_mouse_handler(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0:
            ts_ns = time.perf_counter_ns()
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents

            is_injected = bool(info.flags & LLMHF_INJECTED)
            extra_info = info.dwExtraInfo

            # Classify source
            if is_injected and extra_info == ORBIT_EXTRA_INFO_SIGNATURE:
                source = InputSource.ORBIT_EXPECTED
            elif not is_injected:
                source = InputSource.USER_PHYSICAL
            else:
                source = InputSource.INPUT_AMBIGUOUS

            event_type = "MOUSE_MOVE"
            if wParam == WM_LBUTTONDOWN:
                event_type = "LBUTTON_DOWN"
            elif wParam == WM_LBUTTONUP:
                event_type = "LBUTTON_UP"
            elif wParam == WM_RBUTTONDOWN:
                event_type = "RBUTTON_DOWN"
            elif wParam == WM_RBUTTONUP:
                event_type = "RBUTTON_UP"
            elif wParam == WM_MOUSEWHEEL:
                event_type = "MOUSE_WHEEL"

            self._event_counter += 1
            evt = InputEvent(
                event_id=self._event_counter,
                timestamp_ns=ts_ns,
                event_type=event_type,
                x=info.pt.x,
                y=info.pt.y,
                is_injected=is_injected,
                extra_info=extra_info,
                source_classification=source,
            )

            try:
                self.event_queue.put_nowait(evt)
            except queue.Full:
                pass

            for cb in self._callbacks:
                try:
                    cb(evt)
                except Exception:
                    pass

        return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

    def _low_level_keyboard_handler(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode >= 0:
            ts_ns = time.perf_counter_ns()
            info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents

            is_injected = bool(info.flags & LLKHF_INJECTED)
            extra_info = info.dwExtraInfo

            if is_injected and extra_info == ORBIT_EXTRA_INFO_SIGNATURE:
                source = InputSource.ORBIT_EXPECTED
            elif not is_injected:
                source = InputSource.USER_PHYSICAL
            else:
                source = InputSource.INPUT_AMBIGUOUS

            event_type = "KEY_DOWN" if (wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)) else "KEY_UP"

            self._event_counter += 1
            evt = InputEvent(
                event_id=self._event_counter,
                timestamp_ns=ts_ns,
                event_type=event_type,
                x=0,
                y=0,
                vk_code=info.vkCode,
                scan_code=info.scanCode,
                is_injected=is_injected,
                extra_info=extra_info,
                source_classification=source,
            )

            try:
                self.event_queue.put_nowait(evt)
            except queue.Full:
                pass

            for cb in self._callbacks:
                try:
                    cb(evt)
                except Exception:
                    pass

        return user32.CallNextHookEx(self._keyboard_hook, nCode, wParam, lParam)
