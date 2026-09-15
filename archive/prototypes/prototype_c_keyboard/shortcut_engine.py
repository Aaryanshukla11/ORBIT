"""
Phased Modifier Sequence Engine for Prototype C.
Executes 4-phase compound shortcuts (Ctrl, Shift, Alt, Win) with atomic per-phase cancellation
and guaranteed modifier sanitization.
"""

import time
from typing import List, Dict, Optional, Tuple, Callable
from app_types import PressedKey, KeyOwner, ShortcutSequence
from cancellation_contract import CancellationCoordinator
from keyboard_state import KeyboardStateManager

# Win32 Virtual Key Constants
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


class ShortcutEngine:
    """
    Manages deterministic, phased shortcut key execution and cancellation cleanup.
    """

    def __init__(self, state_manager: KeyboardStateManager):
        self.state_manager = state_manager

    @staticmethod
    def parse_action_key(key_str: str) -> Tuple[int, bool]:
        """
        Parses an action key string to (vk_code, is_extended).
        """
        k = key_str.lower().strip()
        if k in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[k]
        if len(k) == 1:
            code = ord(k.upper())
            return code, False
        raise ValueError(f"Unknown shortcut action key: '{key_str}'")

    @staticmethod
    def parse_modifiers(modifiers: List[str]) -> List[int]:
        """
        Parses a list of modifier strings to Virtual Key codes.
        """
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
        sequence: ShortcutSequence,
        send_key_fn: Callable[[int, bool, bool, bool], bool],
        session_id: str,
        coordinator: Optional[CancellationCoordinator] = None,
        inter_phase_delay_s: float = 0.01,
    ) -> bool:
        """
        Executes a 4-phase compound shortcut:
          Phase 1: Modifiers Down
          Phase 2: Action Key Down
          Phase 3: Action Key Up
          Phase 4: Modifiers Up (in reverse order)
        
        Guarantees that cancellation or error at any phase triggers immediate sanitization.
        """
        mod_vks = self.parse_modifiers(sequence.modifiers)
        act_vk, is_ext = self.parse_action_key(sequence.action_key)

        try:
            for rep in range(sequence.repeat_count):
                if coordinator and coordinator.is_cancelled:
                    return False

                # --- PHASE 1: Modifiers Down ---
                for m_vk in mod_vks:
                    if coordinator and coordinator.is_cancelled:
                        return False
                    send_key_fn(m_vk, False, False, True)  # vk, is_extended, is_unicode, is_down
                    self.state_manager.register_key_down(
                        vk_code=m_vk,
                        is_extended=False,
                        owner=KeyOwner.ORBIT_INJECTED_TRACKED,
                        session_id=session_id,
                    )
                    time.sleep(inter_phase_delay_s)

                # --- PHASE 2: Action Key Down ---
                if coordinator and coordinator.is_cancelled:
                    return False
                send_key_fn(act_vk, is_ext, False, True)
                self.state_manager.register_key_down(
                    vk_code=act_vk,
                    is_extended=is_ext,
                    owner=KeyOwner.ORBIT_INJECTED_TRACKED,
                    session_id=session_id,
                )
                time.sleep(inter_phase_delay_s)

                # --- PHASE 3: Action Key Up ---
                send_key_fn(act_vk, is_ext, False, False)
                self.state_manager.register_key_up(
                    vk_code=act_vk,
                    is_extended=is_ext,
                    owner=KeyOwner.ORBIT_INJECTED_TRACKED,
                    session_id=session_id,
                )
                time.sleep(inter_phase_delay_s)

                # --- PHASE 4: Modifiers Up (in reverse order) ---
                for m_vk in reversed(mod_vks):
                    send_key_fn(m_vk, False, False, False)
                    self.state_manager.register_key_up(
                        vk_code=m_vk,
                        is_extended=False,
                        owner=KeyOwner.ORBIT_INJECTED_TRACKED,
                        session_id=session_id,
                    )
                    time.sleep(inter_phase_delay_s)

            return True

        finally:
            # If any modifier or action key remained in state due to abort/exception, sanitize!
            self.state_manager.sanitize_orbit_keys(
                session_id=session_id,
                release_callback=lambda k: send_key_fn(k.vk_code, k.is_extended, k.is_unicode, False),
            )
