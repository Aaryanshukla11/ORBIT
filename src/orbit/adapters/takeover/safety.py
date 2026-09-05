"""64-bit AMD64 Win32 Low-Level Hook C ABI definitions, signatures, and structures for Human Takeover."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from typing import NamedTuple

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

# Window / Thread Messages
WM_QUIT = 0x0012

# Injected Event Flags
LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002
LLKHF_INJECTED = 0x00000010
LLKHF_LOWER_IL_INJECTED = 0x00000002

# Unified ORBIT ExtraInfo signature passed across Pointer and Keyboard dispatches
ORBIT_EXTRA_INFO_SIGNATURE = 0x08B17001

# Hook callback prototype: LRESULT CALLBACK LowLevelHookProc(int nCode, WPARAM wParam, LPARAM lParam)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    """64-bit Win32 MSLLHOOKSTRUCT structure."""
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """64-bit Win32 KBDLLHOOKSTRUCT structure."""
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_uint64),
    ]


if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

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
else:
    user32 = None
    kernel32 = None


class AbiValidationResult(NamedTuple):
    is_valid: bool
    pointer_size: int
    msllhook_size: int
    kbdllhook_size: int
    error_message: str = ""


class TakeoverAbiGate:
    """Fail-closed ABI validator verifying ctypes alignment against 64-bit AMD64 Windows specifications."""

    @classmethod
    def validate_abi(cls) -> AbiValidationResult:
        ptr_size = ctypes.sizeof(ctypes.c_void_p)
        msll_size = ctypes.sizeof(MSLLHOOKSTRUCT)
        kbdll_size = ctypes.sizeof(KBDLLHOOKSTRUCT)

        if sys.platform != "win32":
            return AbiValidationResult(
                is_valid=False,
                pointer_size=ptr_size,
                msllhook_size=msll_size,
                kbdllhook_size=kbdll_size,
                error_message=f"Non-Windows platform '{sys.platform}' unsupported for native takeover hooks",
            )

        if ptr_size != 8:
            return AbiValidationResult(
                is_valid=False,
                pointer_size=ptr_size,
                msllhook_size=msll_size,
                kbdllhook_size=kbdll_size,
                error_message=f"Invalid pointer size {ptr_size} (expected 8 bytes for 64-bit AMD64)",
            )

        if msll_size != 32:
            return AbiValidationResult(
                is_valid=False,
                pointer_size=ptr_size,
                msllhook_size=msll_size,
                kbdllhook_size=kbdll_size,
                error_message=f"MSLLHOOKSTRUCT size {msll_size} mismatch (expected 32 bytes)",
            )

        if kbdll_size != 24:
            return AbiValidationResult(
                is_valid=False,
                pointer_size=ptr_size,
                msllhook_size=msll_size,
                kbdllhook_size=kbdll_size,
                error_message=f"KBDLLHOOKSTRUCT size {kbdll_size} mismatch (expected 24 bytes)",
            )

        return AbiValidationResult(
            is_valid=True,
            pointer_size=ptr_size,
            msllhook_size=msll_size,
            kbdllhook_size=kbdll_size,
            error_message="",
        )
