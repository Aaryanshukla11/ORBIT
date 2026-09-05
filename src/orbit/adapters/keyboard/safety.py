"""Safety invariants, Win32 C structures, ABI verification gate, and virtual key mappings for ORBIT Keyboard."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import platform
import struct
import sys
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 1. SendInput Keyboard Constants & Signatures
# ----------------------------------------------------------------------

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

ORBIT_EXTRA_INFO_SIGNATURE = 0x08B17001

# Virtual Key Constants
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C

VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_HOME = 0x24
VK_END = 0x23
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22   # Page Down

MODIFIER_MAP: Dict[str, int] = {
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "shift": VK_SHIFT,
    "alt": VK_MENU,
    "win": VK_LWIN,
    "windows": VK_LWIN,
}

SPECIAL_KEY_MAP: Dict[str, Tuple[int, bool]] = {
    "enter": (VK_RETURN, False),
    "return": (VK_RETURN, False),
    "tab": (VK_TAB, False),
    "escape": (VK_ESCAPE, False),
    "esc": (VK_ESCAPE, False),
    "space": (VK_SPACE, False),
    "backspace": (VK_BACK, False),
    "delete": (VK_DELETE, True),
    "del": (VK_DELETE, True),
    "left": (VK_LEFT, True),
    "up": (VK_UP, True),
    "right": (VK_RIGHT, True),
    "down": (VK_DOWN, True),
    "home": (VK_HOME, True),
    "end": (VK_END, True),
    "pageup": (VK_PRIOR, True),
    "pgup": (VK_PRIOR, True),
    "pagedown": (VK_NEXT, True),
    "pgdn": (VK_NEXT, True),
}


# ----------------------------------------------------------------------
# 2. Win32 AMD64 C Structures
# ----------------------------------------------------------------------

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("padding", ctypes.c_byte * 32),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


# ----------------------------------------------------------------------
# 3. Keyboard ABI Verification Gate
# ----------------------------------------------------------------------

class KeyboardAbiGate:
    """Strict runtime validation gate for Win32 SendInput AMD64 keyboard structures."""

    _cached_valid: Optional[bool] = None

    @classmethod
    def is_abi_valid(cls) -> bool:
        if cls._cached_valid is not None:
            return cls._cached_valid

        if sys.platform != "win32":
            cls._cached_valid = False
            return False

        if struct.calcsize("P") != 8:
            logger.error("Non-64-bit architecture rejected by KeyboardAbiGate")
            cls._cached_valid = False
            return False

        if platform.machine().upper() not in ("AMD64", "X86_64", "ARM64"):
            logger.error("Unsupported CPU architecture: %s", platform.machine())
            cls._cached_valid = False
            return False

        if ctypes.sizeof(KEYBDINPUT) != 24:
            logger.error("KEYBDINPUT size mismatch: %d != 24", ctypes.sizeof(KEYBDINPUT))
            cls._cached_valid = False
            return False

        if ctypes.sizeof(INPUT) != 40:
            logger.error("INPUT size mismatch: %d != 40", ctypes.sizeof(INPUT))
            cls._cached_valid = False
            return False

        if KEYBDINPUT.dwExtraInfo.offset != 16:
            logger.error("KEYBDINPUT.dwExtraInfo offset mismatch: %d != 16", KEYBDINPUT.dwExtraInfo.offset)
            cls._cached_valid = False
            return False

        cls._cached_valid = True
        return True

    @classmethod
    def require_abi_valid(cls) -> None:
        if not cls.is_abi_valid():
            raise RuntimeError("CRITICAL: KeyboardAbiGate failed — host Win32 ABI layout is invalid or non-AMD64")
