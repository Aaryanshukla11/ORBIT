"""
Synthetic Input Controller for Prototype B.
Executes controlled SendInput commands (mouse movement, clicks, drags, typing)
tagged with ORBIT_EXTRA_INFO_SIGNATURE. Supports instant cancellation.
"""

import ctypes
from ctypes import wintypes
import time
import threading
from typing import Optional, Callable

from input_monitor import ORBIT_EXTRA_INFO_SIGNATURE

user32 = ctypes.windll.user32

# SendInput Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

user32.GetCursorPos.argtypes = [ctypes.c_void_p]
user32.GetCursorPos.restype = wintypes.BOOL


class InputController:
    """
    High-precision synthetic input driver for ORBIT actions.
    Ensures all synthetic inputs are tagged with ORBIT session signatures.
    """

    def __init__(self):
        self._cancel_requested = threading.Event()
        self._screen_w = user32.GetSystemMetrics(0)
        self._screen_h = user32.GetSystemMetrics(1)
        self._vscreen_w = user32.GetSystemMetrics(78) or self._screen_w
        self._vscreen_h = user32.GetSystemMetrics(79) or self._screen_h

    def request_cancel(self):
        """Immediately halts any in-progress trajectory execution."""
        self._cancel_requested.set()

    def reset_cancel(self):
        self._cancel_requested.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_requested.is_set()

    def get_cursor_pos(self) -> tuple[int, int]:
        pt = (wintypes.LONG * 2)()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt[0], pt[1]

    def _normalize_coords(self, x: int, y: int) -> tuple[int, int]:
        norm_x = int((x * 65535) / (self._vscreen_w - 1))
        norm_y = int((y * 65535) / (self._vscreen_h - 1))
        return norm_x, norm_y

    def move_to(self, x: int, y: int):
        """Sends an absolute mouse movement tagged with ORBIT signature."""
        norm_x, norm_y = self._normalize_coords(x, y)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = norm_x
        inp.union.mi.dy = norm_y
        inp.union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        inp.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_down(self, button: str = "left"):
        inp = INPUT()
        inp.type = INPUT_MOUSE
        flag = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
        inp.union.mi.dwFlags = flag
        inp.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_up(self, button: str = "left"):
        inp = INPUT()
        inp.type = INPUT_MOUSE
        flag = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
        inp.union.mi.dwFlags = flag
        inp.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def click(self, x: int, y: int, button: str = "left"):
        self.move_to(x, y)
        time.sleep(0.02)
        self.mouse_down(button)
        time.sleep(0.02)
        self.mouse_up(button)

    def type_unicode_char(self, char: str):
        """Sends a Unicode character input tagged with ORBIT signature."""
        code = ord(char)
        # Key down
        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.union.ki.wScan = code
        inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
        inp_down.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        # Key up
        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.union.ki.wScan = code
        inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inp_up.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        inputs = (INPUT * 2)(inp_down, inp_up)
        user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
