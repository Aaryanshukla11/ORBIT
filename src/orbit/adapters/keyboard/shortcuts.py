"""Shortcut Risk Policy and 4-Phase Transaction Executor for ORBIT Keyboard."""

from __future__ import annotations

from enum import Enum
import logging
import time
from typing import Callable, List, Optional, Set, Tuple

from orbit.adapters.keyboard.dispatch import NativeKeyboardDispatchGateway
from orbit.adapters.keyboard.safety import (
    MODIFIER_MAP,
    SPECIAL_KEY_MAP,
    VK_LWIN,
    VK_MENU,
    VK_RWIN,
)
from orbit.adapters.keyboard.state import KeyboardStateManager, KeyOwner
from orbit.runtime.cancellation import CancellationToken


logger = logging.getLogger(__name__)


class ShortcutRiskLevel(str, Enum):
    ALLOWED = "ALLOWED"                               # Standard safe editing shortcuts (Ctrl+C, Ctrl+V, etc.)
    RESTRICTED = "RESTRICTED"                         # Destructive/system shortcuts (Win+L, Alt+F4, etc.)
    MANUAL_CONTROLLED_ONLY = "MANUAL_CONTROLLED_ONLY" # Context-disruptive shortcuts (Alt+Tab, Win+Tab)


class ShortcutPolicy:
    """Evaluates keyboard shortcut risk against a conservative security policy."""

    def __init__(self) -> None:
        self._allowed_keys: Set[str] = {
            "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
            "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "left", "right", "up", "down", "home", "end", "pageup", "pagedown",
            "backspace", "delete", "enter", "tab", "space", "escape",
            "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
        }

        # Destructive system shortcuts (blocked by default)
        self._restricted_combinations = {
            ("win", "l"),        # Lock workstation
            ("alt", "f4"),       # Close active window
            ("win", "d"),        # Minimize all windows
            ("win", "m"),        # Minimize all
            ("win", "r"),        # Run dialog
            ("win", "e"),        # File Explorer
            ("ctrl", "alt", "delete"),
            ("ctrl", "shift", "escape"),  # Task Manager
        }

        # Context-disruptive shortcuts (manual controlled only)
        self._manual_only_combinations = {
            ("alt", "tab"),
            ("alt", "shift", "tab"),
            ("win", "tab"),
            ("win", "ctrl", "left"),
            ("win", "ctrl", "right"),
        }

    @staticmethod
    def parse_combination(combination: str) -> Tuple[List[str], str]:
        """Parses a shortcut string like 'ctrl+shift+s' or 'ctrl+c' into (modifiers, action_key)."""
        tokens = [t.strip().lower() for t in combination.split("+") if t.strip()]
        if not tokens:
            raise ValueError(f"Invalid empty shortcut combination: '{combination}'")
        if len(tokens) == 1:
            return [], tokens[0]
        return tokens[:-1], tokens[-1]

    def classify(self, modifiers: List[str], action_key: str) -> ShortcutRiskLevel:
        """Classifies a modifier + action key sequence."""
        norm_mods = tuple(sorted([m.lower().strip() for m in modifiers]))
        norm_act = action_key.lower().strip()
        full_tuple = tuple(sorted(list(norm_mods) + [norm_act]))

        keys_set = set(norm_mods) | {norm_act}

        for manual in self._manual_only_combinations:
            if set(manual) == keys_set:
                return ShortcutRiskLevel.MANUAL_CONTROLLED_ONLY

        for restricted in self._restricted_combinations:
            if set(restricted) == keys_set:
                return ShortcutRiskLevel.RESTRICTED

        # Disallow bare or arbitrary Win key sequences unless specifically vetted
        if "win" in norm_mods or norm_act in ("win", "lwin", "rwin"):
            return ShortcutRiskLevel.RESTRICTED

        if norm_act in self._allowed_keys:
            return ShortcutRiskLevel.ALLOWED

        return ShortcutRiskLevel.ALLOWED



class ShortcutExecutor:
    """Deterministic, 4-phase compound shortcut transaction engine."""

    def __init__(self, state_manager: KeyboardStateManager, policy: Optional[ShortcutPolicy] = None) -> None:
        self.state_manager = state_manager
        self.policy = policy or ShortcutPolicy()

    @staticmethod
    def parse_action_key(key_str: str) -> Tuple[int, bool]:
        """Parses an action key string to (vk_code, is_extended)."""
        k = key_str.lower().strip()
        if k in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[k]
        if k.startswith("f") and len(k) > 1 and k[1:].isdigit():
            f_num = int(k[1:])
            if 1 <= f_num <= 24:
                return 0x70 + (f_num - 1), False
        if len(k) == 1:
            return ord(k.upper()), False
        raise ValueError(f"Unknown shortcut action key: '{key_str}'")

    @staticmethod
    def parse_modifiers(modifiers: List[str]) -> List[int]:
        """Parses modifier strings to Virtual Key codes."""
        vks = []
        for m in modifiers:
            m_norm = m.lower().strip()
            if m_norm in MODIFIER_MAP:
                vks.append(MODIFIER_MAP[m_norm])
            else:
                raise ValueError(f"Unknown modifier key: '{m}'")
        return vks

    def execute_shortcut(
        self,
        combination: str,
        session_id: str = "default",
        cancellation_token: Optional[CancellationToken] = None,
        inter_phase_delay_s: float = 0.01,
    ) -> bool:
        """Executes a 4-phase compound shortcut:

        Phase 1: Modifiers Down
        Phase 2: Action Key Down
        Phase 3: Action Key Up
        Phase 4: Modifiers Up (in reverse order)

        Guarantees that cancellation or error at any phase triggers immediate sanitization.
        """
        modifiers, action_key = self.policy.parse_combination(combination)
        risk = self.policy.classify(modifiers, action_key)
        if risk == ShortcutRiskLevel.RESTRICTED:
            raise ValueError(f"Shortcut '{combination}' is RESTRICTED by safety policy")

        mod_vks = self.parse_modifiers(modifiers)
        act_vk, is_ext = self.parse_action_key(action_key)

        if cancellation_token and cancellation_token.is_cancelled:
            return False

        try:
            # --- PHASE 1: Modifiers Down ---
            for m_vk in mod_vks:
                if cancellation_token and cancellation_token.is_cancelled:
                    return False
                res = NativeKeyboardDispatchGateway.dispatch_key_packet(
                    vk_or_scan=m_vk,
                    is_extended=False,
                    is_unicode=False,
                    is_down=True,
                )
                if not res.success:
                    self.state_manager.lock_state(f"Failed to dispatch modifier DOWN vk=0x{m_vk:02X}")
                    return False
                self.state_manager.register_key_down(
                    vk_code=m_vk,
                    is_extended=False,
                    owner=KeyOwner.ORBIT_SYNTHETIC,
                    session_id=session_id,
                )
                if inter_phase_delay_s > 0:
                    time.sleep(inter_phase_delay_s)

            # --- PHASE 2: Action Key Down ---
            if cancellation_token and cancellation_token.is_cancelled:
                return False

            res = NativeKeyboardDispatchGateway.dispatch_key_packet(
                vk_or_scan=act_vk,
                is_extended=is_ext,
                is_unicode=False,
                is_down=True,
            )
            if not res.success:
                self.state_manager.lock_state(f"Failed to dispatch action key DOWN vk=0x{act_vk:02X}")
                return False
            self.state_manager.register_key_down(
                vk_code=act_vk,
                is_extended=is_ext,
                owner=KeyOwner.ORBIT_SYNTHETIC,
                session_id=session_id,
            )
            if inter_phase_delay_s > 0:
                time.sleep(inter_phase_delay_s)

            # --- PHASE 3: Action Key Up ---
            res_up = NativeKeyboardDispatchGateway.dispatch_key_packet(
                vk_or_scan=act_vk,
                is_extended=is_ext,
                is_unicode=False,
                is_down=False,
            )
            if not res_up.success:
                self.state_manager.lock_state(f"Failed to dispatch action key UP vk=0x{act_vk:02X}")
                return False
            self.state_manager.register_key_up(
                vk_code=act_vk,
                is_extended=is_ext,
                owner=KeyOwner.ORBIT_SYNTHETIC,
                session_id=session_id,
            )
            if inter_phase_delay_s > 0:
                time.sleep(inter_phase_delay_s)

            # --- PHASE 4: Modifiers Up (in reverse order) ---
            for m_vk in reversed(mod_vks):
                res_m_up = NativeKeyboardDispatchGateway.dispatch_key_packet(
                    vk_or_scan=m_vk,
                    is_extended=False,
                    is_unicode=False,
                    is_down=False,
                )
                if not res_m_up.success:
                    self.state_manager.lock_state(f"Failed to dispatch modifier UP vk=0x{m_vk:02X}")
                    return False
                self.state_manager.register_key_up(
                    vk_code=m_vk,
                    is_extended=False,
                    owner=KeyOwner.ORBIT_SYNTHETIC,
                    session_id=session_id,
                )
                if inter_phase_delay_s > 0:
                    time.sleep(inter_phase_delay_s)

            return True

        finally:
            # If any modifier remained due to abort or error, sanitize it
            self.state_manager.sanitize_orbit_keys(
                session_id=session_id,
                release_callback=lambda k: NativeKeyboardDispatchGateway.dispatch_key_packet(
                    vk_or_scan=k.vk_code if not k.is_unicode else k.scan_code,
                    is_extended=k.is_extended,
                    is_unicode=k.is_unicode,
                    is_down=False,
                ).success,
            )
