"""
Key Ownership Tracker and Selective Sanitization Engine for Prototype C.
Implements the 3-tier ownership model (ORBIT_INJECTED_TRACKED, USER_PHYSICAL_OBSERVED, UNKNOWN).
Ensures that ONLY confirmed ORBIT-owned depressed keys are sanitized upon abort.
"""

import threading
import time
from typing import Dict, List, Optional, Callable, Tuple
from app_types import PressedKey, KeyOwner


class KeyboardStateManager:
    """
    Thread-safe tracker for depressed keys categorized by provenance and session.
    Supports overlapping logical key states (e.g. Human and ORBIT holding Ctrl simultaneously)
    and strictly prevents blind global key release.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # Map (vk_code, scan_code, is_extended, is_unicode, owner, session_id) -> PressedKey
        self._pressed_keys: Dict[Tuple[int, int, bool, bool, KeyOwner, str], PressedKey] = {}
        self._history: List[PressedKey] = []

    def register_key_down(
        self,
        vk_code: int,
        scan_code: int = 0,
        is_extended: bool = False,
        is_unicode: bool = False,
        owner: KeyOwner = KeyOwner.ORBIT_INJECTED_TRACKED,
        session_id: str = "default",
    ) -> PressedKey:
        """
        Records that a key has entered the down state for the specified owner and session.
        """
        key = PressedKey(
            vk_code=vk_code,
            scan_code=scan_code,
            is_extended=is_extended,
            is_unicode=is_unicode,
            owner=owner,
            timestamp_ns=time.perf_counter_ns(),
            session_id=session_id,
        )
        lookup = (vk_code, scan_code, is_extended, is_unicode, owner, session_id)
        with self._lock:
            self._pressed_keys[lookup] = key
            self._history.append(key)
        return key

    def register_key_up(
        self,
        vk_code: int,
        scan_code: int = 0,
        is_extended: bool = False,
        is_unicode: bool = False,
        owner: Optional[KeyOwner] = None,
        session_id: Optional[str] = None,
    ) -> Optional[PressedKey]:
        """
        Removes a key from the depressed state tracker upon key release.
        """
        with self._lock:
            for lookup, key in list(self._pressed_keys.items()):
                if key.vk_code == vk_code and key.scan_code == scan_code and key.is_extended == is_extended and key.is_unicode == is_unicode:
                    if (owner is None or key.owner == owner) and (session_id is None or key.session_id == session_id):
                        return self._pressed_keys.pop(lookup, None)
            return None

    def is_key_down(self, vk_code: int, scan_code: int = 0) -> bool:
        """Returns True if the logical key is held down by ANY owner."""
        with self._lock:
            for k in self._pressed_keys.values():
                if k.vk_code == vk_code or (scan_code and k.scan_code == scan_code):
                    return True
            return False

    def get_orbit_pressed_keys(self, session_id: Optional[str] = None) -> List[PressedKey]:
        """
        Returns all currently depressed keys explicitly confirmed as ORBIT_INJECTED_TRACKED.
        """
        with self._lock:
            keys = [
                k for k in self._pressed_keys.values()
                if k.owner == KeyOwner.ORBIT_INJECTED_TRACKED
            ]
            if session_id:
                keys = [k for k in keys if k.session_id == session_id]
            return list(keys)

    def get_user_pressed_keys(self) -> List[PressedKey]:
        """
        Returns all currently depressed keys observed from physical user input.
        """
        with self._lock:
            return [
                k for k in self._pressed_keys.values()
                if k.owner == KeyOwner.USER_PHYSICAL_OBSERVED
            ]

    def sanitize_orbit_keys(
        self,
        session_id: Optional[str] = None,
        release_callback: Optional[Callable[[PressedKey], None]] = None,
    ) -> List[PressedKey]:
        """
        Sanitizes all active ORBIT-owned depressed keys by invoking release_callback
        and removing them from tracked state.
        
        CRITICAL SAFETY INVARIANT:
        Keys marked USER_PHYSICAL_OBSERVED or UNKNOWN are NEVER released.
        """
        with self._lock:
            orbit_keys = self.get_orbit_pressed_keys(session_id=session_id)
            sanitized: List[PressedKey] = []

            for k in reversed(orbit_keys):  # Release in reverse order (action key, then modifiers)
                lookup = (k.vk_code, k.scan_code, k.is_extended, k.is_unicode, k.owner, k.session_id)
                self._pressed_keys.pop(lookup, None)
                if release_callback:
                    try:
                        release_callback(k)
                    except Exception as e:
                        print(f"[KeyboardStateManager] Error in release callback for key {k}: {e}")
                sanitized.append(k)

            return sanitized

    def clear_all(self):
        """Clears in-memory tracker (test utility only)."""
        with self._lock:
            self._pressed_keys.clear()
            self._history.clear()
