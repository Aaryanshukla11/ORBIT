"""Character-by-character Unicode Text Typing Engine for ORBIT Keyboard."""

from __future__ import annotations

import logging
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

        # Pre-dispatch target validation
        if expected_hwnd:
            if not self.focus_validator.is_window_alive(expected_hwnd):
                logger.warning("Target HWND %d is not a valid alive window before typing", expected_hwnd)
                return False
            if not self.focus_validator.is_foreground(expected_hwnd):
                logger.warning("Target HWND %d is not in foreground before typing", expected_hwnd)
                return False

        code_units = UnicodeEngine.text_to_utf16_code_units(text)

        try:
            for idx, unit in enumerate(code_units):
                # Cancellation check
                if cancellation_token and cancellation_token.is_cancelled:
                    logger.info("Typing cancelled at unit %d/%d", idx, len(code_units))
                    return False

                # Target existence & focus check during streaming
                if expected_hwnd:
                    if not self.focus_validator.is_window_alive(expected_hwnd):
                        logger.warning("Target HWND %d was destroyed during typing", expected_hwnd)
                        return False
                    if not self.focus_validator.is_foreground(expected_hwnd):
                        logger.warning("Target HWND %d lost foreground focus during typing", expected_hwnd)
                        return False

                # Dispatch Down + Up Unicode pair
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
