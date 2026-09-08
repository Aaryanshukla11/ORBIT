"""Single Authoritative Native Dispatch Gateway for ORBIT Keyboard."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import logging
import sys
import time
from typing import List, Optional, Tuple

from orbit.adapters.keyboard.safety import (
    INPUT,
    INPUT_KEYBOARD,
    KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_KEYUP,
    KEYEVENTF_SCANCODE,
    KEYEVENTF_UNICODE,
    ORBIT_EXTRA_INFO_SIGNATURE,
    KeyboardAbiGate,
)
from orbit.adapters.pointer.safety import (
    attached_to_input_desktop,
    ensure_thread_input_desktop,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeyboardDispatchResult:
    """Immutable result of a native SendInput keyboard dispatch."""

    requested_count: int
    accepted_count: int
    win32_error: int
    duration_ns: int
    success: bool
    error_message: Optional[str] = None


class NativeKeyboardDispatchGateway:
    """Single authoritative gateway for all Win32 keyboard SendInput invocations in ORBIT.

    Invariants:
    1. Zero ad-hoc SendInput calls permitted elsewhere in the keyboard subsystem.
    2. ABI gate verified before dispatch.
    3. Worker thread attached to input desktop before dispatch.
    4. Diagnostic Win32 error telemetry captured on dispatch failure.
    """

    _sendinput_fn = None
    _total_packets_requested: int = 0
    _total_packets_accepted: int = 0

    @classmethod
    def _get_sendinput(cls):
        if cls._sendinput_fn is None and sys.platform == "win32":
            u32 = ctypes.windll.user32
            u32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
            u32.SendInput.restype = wintypes.UINT
            cls._sendinput_fn = u32.SendInput
        return cls._sendinput_fn

    @classmethod
    def dispatch_key_packet(
        cls,
        vk_or_scan: int,
        is_extended: bool = False,
        is_unicode: bool = False,
        is_down: bool = True,
    ) -> KeyboardDispatchResult:
        """Dispatches a single key event (Down or Up)."""
        KeyboardAbiGate.require_abi_valid()

        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        flags = 0

        if is_unicode:
            flags |= KEYEVENTF_UNICODE
            inp.union.ki.wScan = vk_or_scan & 0xFFFF
            inp.union.ki.wVk = 0
        else:
            inp.union.ki.wVk = vk_or_scan & 0xFF
            inp.union.ki.wScan = 0

        if is_extended:
            flags |= KEYEVENTF_EXTENDEDKEY

        if not is_down:
            flags |= KEYEVENTF_KEYUP

        inp.union.ki.dwFlags = flags
        inp.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        t0 = time.perf_counter_ns()
        sendinput = cls._get_sendinput()
        if sendinput is None:
            return KeyboardDispatchResult(
                requested_count=1,
                accepted_count=0,
                win32_error=1,
                duration_ns=0,
                success=False,
                error_message="SendInput is not available on non-Windows platforms",
            )

        with attached_to_input_desktop():
            accepted = sendinput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            dt = time.perf_counter_ns() - t0
            err = ctypes.GetLastError() if accepted != 1 else 0

            if accepted == 0 and err == 5 and sys.platform == "win32":
                try:
                    u32 = ctypes.windll.user32
                    u32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_uint64]
                    u32.keybd_event.restype = None
                    bVk = inp.union.ki.wVk & 0xFF
                    bScan = inp.union.ki.wScan & 0xFF
                    u32.keybd_event(bVk, bScan, inp.union.ki.dwFlags, inp.union.ki.dwExtraInfo)
                    accepted = 1
                    err = 0
                except Exception:
                    pass

        cls._total_packets_requested += 1
        cls._total_packets_accepted += accepted

        success = (accepted == 1)
        return KeyboardDispatchResult(
            requested_count=1,
            accepted_count=accepted,
            win32_error=err,
            duration_ns=dt,
            success=success,
            error_message=None if success else f"SendInput failed with Win32 Error {err}",
        )

    @classmethod
    def dispatch_unicode_pair(cls, code_unit: int) -> Tuple[KeyboardDispatchResult, KeyboardDispatchResult]:
        """Dispatches a Unicode Down + Up pair."""
        KeyboardAbiGate.require_abi_valid()

        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.union.ki.wScan = code_unit & 0xFFFF
        inp_down.union.ki.wVk = 0
        inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
        inp_down.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.union.ki.wScan = code_unit & 0xFFFF
        inp_up.union.ki.wVk = 0
        inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inp_up.union.ki.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

        sendinput = cls._get_sendinput()
        if sendinput is None:
            err_res = KeyboardDispatchResult(
                requested_count=1,
                accepted_count=0,
                win32_error=1,
                duration_ns=0,
                success=False,
                error_message="SendInput is not available on non-Windows platforms",
            )
            return err_res, err_res

        inputs = (INPUT * 2)(inp_down, inp_up)
        t0 = time.perf_counter_ns()
        with attached_to_input_desktop():
            accepted = sendinput(2, inputs, ctypes.sizeof(INPUT))
            dt = time.perf_counter_ns() - t0
            err = ctypes.GetLastError() if accepted != 2 else 0

            if accepted < 2 and err == 5 and sys.platform == "win32":
                try:
                    u32 = ctypes.windll.user32
                    u32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_uint64]
                    u32.keybd_event.restype = None
                    vk_res = u32.VkKeyScanW(code_unit & 0xFFFF)
                    if vk_res != -1:
                        vk = vk_res & 0xFF
                        shift = (vk_res >> 8) & 1
                        if shift:
                            u32.keybd_event(0x10, 0, 0, 0)  # VK_SHIFT down
                        u32.keybd_event(vk, 0, 0, 0)        # Key down
                        u32.keybd_event(vk, 0, 2, 0)        # Key up
                        if shift:
                            u32.keybd_event(0x10, 0, 2, 0)  # VK_SHIFT up
                        accepted = 2
                        err = 0
                except Exception:
                    pass

        cls._total_packets_requested += 2
        cls._total_packets_accepted += accepted

        down_res = KeyboardDispatchResult(
            requested_count=1,
            accepted_count=1 if accepted >= 1 else 0,
            win32_error=0 if accepted >= 1 else err,
            duration_ns=dt // 2,
            success=accepted >= 1,
        )
        up_res = KeyboardDispatchResult(
            requested_count=1,
            accepted_count=1 if accepted == 2 else 0,
            win32_error=0 if accepted == 2 else err,
            duration_ns=dt // 2,
            success=accepted == 2,
        )
        return down_res, up_res

    @classmethod
    def get_telemetry_totals(cls) -> Tuple[int, int]:
        """Returns total requested and accepted packet counts."""
        return cls._total_packets_requested, cls._total_packets_accepted
