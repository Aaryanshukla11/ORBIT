"""Production Keyboard Adapter for ORBIT runtime."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityUnavailableError,
    KeyboardError,
)
from orbit.adapters.keyboard.dispatch import NativeKeyboardDispatchGateway
from orbit.adapters.keyboard.focus import TargetFocusValidator
from orbit.adapters.keyboard.safety import (
    MODIFIER_MAP,
    SPECIAL_KEY_MAP,
    KeyboardAbiGate,
)
from orbit.adapters.keyboard.shortcuts import ShortcutExecutor, ShortcutPolicy
from orbit.adapters.keyboard.state import KeyboardStateManager, KeyOwner
from orbit.adapters.keyboard.text import TextTypingExecutor
from orbit.adapters.pointer.safety import ensure_thread_input_desktop
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityType,
    KeyboardCapability,
)
from orbit.runtime.cancellation import CancellationToken


logger = logging.getLogger(__name__)


class ProductionKeyboardAdapter(BaseCapabilityAdapter, KeyboardCapability):
    """Production capability adapter for keyboard typing, shortcuts, and key state transactions."""

    def __init__(self, enable_live_injection: bool = True) -> None:
        super().__init__(
            capability_name="ProductionKeyboard",
            capability_type=CapabilityType.KEYBOARD,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self._enable_live_injection = enable_live_injection
        self._state_manager = KeyboardStateManager()
        self._focus_validator = TargetFocusValidator()
        self._shortcut_policy = ShortcutPolicy()
        self._shortcut_executor = ShortcutExecutor(self._state_manager, self._shortcut_policy)
        self._typing_executor = TextTypingExecutor(self._state_manager, self._focus_validator)

    @property
    def state_manager(self) -> KeyboardStateManager:
        return self._state_manager

    @property
    def shortcut_policy(self) -> ShortcutPolicy:
        return self._shortcut_policy

    async def _on_initialize(self) -> None:
        if not self._enable_live_injection:
            raise KeyboardError("Live keyboard injection is disabled by configuration", recoverable=False)

        if not KeyboardAbiGate.is_abi_valid():
            raise KeyboardError("Host environment failed KeyboardAbiGate verification", recoverable=False)

        ensure_thread_input_desktop()
        self._details["abi_valid"] = True
        self._details["live_injection_enabled"] = True
        logger.info("ProductionKeyboardAdapter initialized successfully")

    async def _on_shutdown(self) -> None:
        await self.emergency_release_all()
        logger.info("ProductionKeyboardAdapter shut down cleanly")

    async def type_text(
        self,
        text: str,
        delay_ms: float = 2.0,
        target_hwnd: Optional[int] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Type a sequence of Unicode characters character-by-character."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production keyboard adapter is not ready",
            )

        if self._state_manager.is_locked:
            raise KeyboardError(
                f"Keyboard is in fail-closed UNRESOLVED_LOCKED state ({self._state_manager.lockout_reason})",
                recoverable=True,
            )

        return await asyncio.to_thread(
            self._typing_executor.type_text,
            text,
            delay_ms,
            target_hwnd,
            "production_session",
            cancellation_token,
        )

    async def press_shortcut(
        self,
        combination: str,
        target_hwnd: Optional[int] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Execute a 4-phase modifier key shortcut (e.g. 'ctrl+c', 'alt+tab')."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production keyboard adapter is not ready",
            )

        if self._state_manager.is_locked:
            raise KeyboardError(
                f"Keyboard is in fail-closed UNRESOLVED_LOCKED state ({self._state_manager.lockout_reason})",
                recoverable=True,
            )

        return await asyncio.to_thread(
            self._shortcut_executor.execute_shortcut,
            combination,
            "production_session",
            cancellation_token,
        )

    def _parse_single_key(self, key_code: str) -> tuple[int, bool]:
        k = key_code.lower().strip()
        if k in MODIFIER_MAP:
            return MODIFIER_MAP[k], False
        if k in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[k]
        if k.startswith("f") and len(k) > 1 and k[1:].isdigit():
            f_num = int(k[1:])
            if 1 <= f_num <= 24:
                return 0x70 + (f_num - 1), False
        if len(k) == 1:
            return ord(k.upper()), False
        raise ValueError(f"Unknown key code: '{key_code}'")

    async def press_key(
        self,
        key_code: str,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Press down a specific virtual key."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production keyboard adapter is not ready",
            )

        if self._state_manager.is_locked:
            raise KeyboardError(
                f"Keyboard is in fail-closed UNRESOLVED_LOCKED state ({self._state_manager.lockout_reason})",
                recoverable=True,
            )

        if cancellation_token and cancellation_token.is_cancelled:
            return False

        vk, is_ext = self._parse_single_key(key_code)

        def _do_down() -> bool:
            res = NativeKeyboardDispatchGateway.dispatch_key_packet(
                vk_or_scan=vk,
                is_extended=is_ext,
                is_unicode=False,
                is_down=True,
            )
            if res.success:
                self._state_manager.register_key_down(
                    vk_code=vk,
                    is_extended=is_ext,
                    owner=KeyOwner.ORBIT_SYNTHETIC,
                    session_id="production_session",
                )
                return True
            self._state_manager.lock_state(f"Failed to dispatch key down for '{key_code}' (Error: {res.win32_error})")
            return False

        return await asyncio.to_thread(_do_down)

    async def release_key(
        self,
        key_code: str,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Release a specific virtual key."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production keyboard adapter is not ready",
            )

        vk, is_ext = self._parse_single_key(key_code)

        def _do_up() -> bool:
            res = NativeKeyboardDispatchGateway.dispatch_key_packet(
                vk_or_scan=vk,
                is_extended=is_ext,
                is_unicode=False,
                is_down=False,
            )
            if res.success:
                self._state_manager.register_key_up(
                    vk_code=vk,
                    is_extended=is_ext,
                    owner=KeyOwner.ORBIT_SYNTHETIC,
                    session_id="production_session",
                )
                return True
            self._state_manager.lock_state(f"Failed to dispatch key up for '{key_code}' (Error: {res.win32_error})")
            return False

        return await asyncio.to_thread(_do_up)

    async def emergency_release_all(self) -> bool:
        """Release all held keys fail-closed."""
        def _sanitize() -> bool:
            self._state_manager.sanitize_orbit_keys(
                release_callback=lambda k: NativeKeyboardDispatchGateway.dispatch_key_packet(
                    vk_or_scan=k.vk_code if not k.is_unicode else k.scan_code,
                    is_extended=k.is_extended,
                    is_unicode=k.is_unicode,
                    is_down=False,
                ).success,
            )
            return not self._state_manager.is_locked

        return await asyncio.to_thread(_sanitize)

    async def get_lockout_state(self) -> str:
        """Query keyboard lockout state."""
        return self._state_manager.lockout_state

    def recover_locked_state(self, recovery_token: str) -> bool:
        """Clear lockout with administrative recovery token."""
        return self._state_manager.recover_locked_state(recovery_token)

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        if self._state_manager.is_locked:
            return CapabilityHealth(
                capability_name=self.capability_name,
                capability_type=self.capability_type,
                adapter_mode=self.adapter_mode,
                lifecycle_state=self._lifecycle_state,
                status=CapabilityHealthStatus.DEGRADED,
                last_error=self._state_manager.lockout_reason,
                details={"lockout_state": self._state_manager.lockout_state, "reason": self._state_manager.lockout_reason},
            )
        base_health = await super().get_health()
        return base_health

