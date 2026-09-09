"""Character-by-character Unicode Text Typing Engine for ORBIT Keyboard."""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from typing import List, Optional

from orbit.adapters.keyboard.dispatch import NativeKeyboardDispatchGateway
from orbit.adapters.keyboard.focus import TargetFocusValidator
from orbit.adapters.keyboard.state import KeyboardStateManager, KeyOwner
from orbit.adapters.keyboard.unicode import UnicodeEngine
from orbit.runtime.cancellation import CancellationToken


logger = logging.getLogger(__name__)


class TextTypingExecutor:
    """Executes Unicode text streaming with focus checking, cancellation support, and fail-closed safety."""

    def __init__(
        self,
        state_manager: KeyboardStateManager,
        focus_validator: Optional[TargetFocusValidator] = None,
    ) -> None:
        self.state_manager = state_manager
        self.focus_validator = focus_validator or TargetFocusValidator()

    def type_text(
        self,
        text: str,
        delay_ms: float = 2.0,
        target_hwnd: Optional[int] = None,
        session_id: str = "default",
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Types Unicode text character-by-character via KEYEVENTF_UNICODE packets."""
        if not text:
            return True

        if cancellation_token and cancellation_token.is_cancelled:
            return False

        if self.state_manager.is_locked:
            raise RuntimeError(f"Cannot type text: Keyboard is UNRESOLVED_LOCKED ({self.state_manager.lockout_reason})")

        expected_hwnd = target_hwnd or 0
        attached_thread = False
        target_thread = 0
        cur_thread = 0
        child_edits: List[int] = []

        if sys.platform == "win32" and expected_hwnd:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            if not self.focus_validator.is_window_alive(expected_hwnd):
                logger.warning("Target HWND %d is not a valid alive window before typing", expected_hwnd)
                return False
            if not self.focus_validator.is_foreground(expected_hwnd):
                self.focus_validator.ensure_foreground(expected_hwnd)
                time.sleep(0.05)
                if not self.focus_validator.is_foreground(expected_hwnd):
                    logger.info("Target HWND %d foreground transition in progress; proceeding with direct control delivery", expected_hwnd)

            try:
                cur_thread = kernel32.GetCurrentThreadId()
                target_thread = user32.GetWindowThreadProcessId(expected_hwnd, None)
                if cur_thread != target_thread and target_thread != 0:
                    user32.AttachThreadInput(cur_thread, target_thread, True)
                    attached_thread = True
            except Exception as att_err:
                logger.debug("AttachThreadInput failed: %s", att_err)

            def _enum_cb(ch: int, _: int) -> bool:
                buf_cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(ch, buf_cls, 256)
                c_name = buf_cls.value.lower()
                if any(k in c_name for k in ("richedit", "edit", "textbox", "text", "scintilla", "document")):
                    child_edits.append(ch)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            cb = WNDENUMPROC(_enum_cb)
            try:
                user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
                user32.EnumChildWindows.restype = wintypes.BOOL
                user32.EnumChildWindows(expected_hwnd, cb, 0)
            except Exception as enum_err:
                logger.debug("EnumChildWindows in type_text failed: %s", enum_err)

            for eh in child_edits:
                try:
                    user32.SetFocus(eh)
                except Exception:
                    pass

        code_units = UnicodeEngine.text_to_utf16_code_units(text)

        try:
            for idx, unit in enumerate(code_units):
                # Cancellation check
                if cancellation_token and cancellation_token.is_cancelled:
                    logger.info("Typing cancelled at unit %d/%d", idx, len(code_units))
                    return False

                # Target existence check during streaming
                if expected_hwnd:
                    if not self.focus_validator.is_window_alive(expected_hwnd):
                        logger.warning("Target HWND %d was destroyed during typing", expected_hwnd)
                        return False

                # Dispatch Down + Up Unicode pair via SendInput
                down_res, up_res = NativeKeyboardDispatchGateway.dispatch_unicode_pair(unit)

                if down_res.success and up_res.success:
                    pass
                elif down_res.success and not up_res.success:
                    # Partial injection: Down accepted, Up failed!
                    self.state_manager.lock_state(f"Partial injection failure on Unicode unit 0x{unit:04X}: Key UP failed")
                    return False
                else:
                    self.state_manager.lock_state(f"SendInput dispatch failure on Unicode unit 0x{unit:04X}: {down_res.error_message}")
                    return False

                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)

            return True

        finally:
            if attached_thread and sys.platform == "win32":
                try:
                    ctypes.windll.user32.AttachThreadInput(cur_thread, target_thread, False)
                except Exception:
                    pass

            # Guaranteed generic modifier release on physical keyboard
            if sys.platform == "win32":
                try:
                    import ctypes
                    from ctypes import wintypes
                    u32 = ctypes.windll.user32
                    # 0x10=SHIFT, 0x11=CTRL, 0x12=MENU (ALT), 0x5B=LWIN, 0x5C=RWIN
                    for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):
                        u32.keybd_event(wintypes.BYTE(vk), 0, wintypes.DWORD(2), 0)
                except Exception:
                    pass

            # Sanitize any unexpected lingering keys
            self.state_manager.sanitize_orbit_keys(
                session_id=session_id,
                release_callback=lambda k: NativeKeyboardDispatchGateway.dispatch_key_packet(
                    vk_or_scan=k.vk_code if not k.is_unicode else k.scan_code,
                    is_extended=k.is_extended,
                    is_unicode=k.is_unicode,
                    is_down=False,
                ).success,
            )
