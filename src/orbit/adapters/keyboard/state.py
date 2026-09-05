"""Key Ownership Tracker, State Machine, and Selective Sanitization for ORBIT Keyboard."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger(__name__)


class KeyOwner(str, Enum):
    ORBIT_SYNTHETIC = "ORBIT_SYNTHETIC"  # Injected synthetically by ORBIT
    USER_PHYSICAL = "USER_PHYSICAL"      # Observed from user physical hardware (NEVER sanitize)
    UNKNOWN = "UNKNOWN"                  # Unproven or untracked state (NEVER sanitize)


@dataclass(frozen=True)
class PressedKey:
    """Immutable record of an active pressed key."""

    vk_code: int
    scan_code: int
    is_extended: bool
    is_unicode: bool
    owner: KeyOwner
    timestamp_ns: int
    session_id: str


class KeyboardStateManager:
    """Thread-safe state manager for depressed keys, ownership provenance, and fail-closed lockouts.

    Invariants:
    1. Only keys with owner ORBIT_SYNTHETIC may be released during sanitization.
    2. If a key release fails, the state machine immediately transitions to UNRESOLVED_LOCKED.
    3. UNRESOLVED_LOCKED can only be cleared via an explicit, valid administrative recovery token.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Map: (vk_code, scan_code, is_extended, is_unicode, owner, session_id) -> PressedKey
        self._pressed_keys: Dict[Tuple[int, int, bool, bool, KeyOwner, str], PressedKey] = {}
        self._is_locked: bool = False
        self._lockout_reason: Optional[str] = None
        self._active_recovery_token: Optional[str] = None

    @property
    def is_locked(self) -> bool:
        with self._lock:
            return self._is_locked

    @property
    def lockout_state(self) -> str:
        with self._lock:
            return "UNRESOLVED_LOCKED" if self._is_locked else "NORMAL"

    @property
    def lockout_reason(self) -> Optional[str]:
        with self._lock:
            return self._lockout_reason

    def lock_state(self, reason: str) -> str:
        """Transitions state machine into fail-closed UNRESOLVED_LOCKED and generates recovery token."""
        with self._lock:
            self._is_locked = True
            self._lockout_reason = reason
            token = f"REC-KBD-{uuid.uuid4().hex[:12].upper()}"
            self._active_recovery_token = token
            logger.critical("Keyboard state LOCKED: %s (Token: %s)", reason, token)
            return token

    def recover_locked_state(self, recovery_token: str) -> bool:
        """Recovers from UNRESOLVED_LOCKED if recovery token matches."""
        with self._lock:
            if not self._is_locked:
                return True
            if self._active_recovery_token and recovery_token.strip() == self._active_recovery_token:
                self._is_locked = False
                self._lockout_reason = None
                self._active_recovery_token = None
                self._pressed_keys.clear()
                logger.info("Keyboard state recovered from lockout via token %s", recovery_token)
                return True
            logger.warning("Keyboard recovery rejected: Invalid token %s", recovery_token)
            return False

    def register_key_down(
        self,
        vk_code: int,
        scan_code: int = 0,
        is_extended: bool = False,
        is_unicode: bool = False,
        owner: KeyOwner = KeyOwner.ORBIT_SYNTHETIC,
        session_id: str = "default",
    ) -> PressedKey:
        """Records a key down event."""
        with self._lock:
            if self._is_locked:
                raise RuntimeError(f"Cannot dispatch key down: Keyboard is UNRESOLVED_LOCKED ({self._lockout_reason})")

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
            self._pressed_keys[lookup] = key
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
        """Removes a key from the depressed state tracker upon key release."""
        with self._lock:
            for lookup, key in list(self._pressed_keys.items()):
                if (
                    key.vk_code == vk_code
                    and key.scan_code == scan_code
                    and key.is_extended == is_extended
                    and key.is_unicode == is_unicode
                ):
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
        """Returns all depressed keys explicitly confirmed as ORBIT_SYNTHETIC."""
        with self._lock:
            keys = [k for k in self._pressed_keys.values() if k.owner == KeyOwner.ORBIT_SYNTHETIC]
            if session_id:
                keys = [k for k in keys if k.session_id == session_id]
            return list(keys)

    def sanitize_orbit_keys(
        self,
        session_id: Optional[str] = None,
        release_callback: Optional[Callable[[PressedKey], bool]] = None,
    ) -> List[PressedKey]:
        """Sanitizes all active ORBIT-owned depressed keys in reverse order (action key, then modifiers).

        If any release fails, triggers fail-closed lockout.
        """
        with self._lock:
            orbit_keys = self.get_orbit_pressed_keys(session_id=session_id)
            sanitized: List[PressedKey] = []

            for k in reversed(orbit_keys):
                lookup = (k.vk_code, k.scan_code, k.is_extended, k.is_unicode, k.owner, k.session_id)
                self._pressed_keys.pop(lookup, None)
                if release_callback:
                    try:
                        ok = release_callback(k)
                        if not ok:
                            self.lock_state(f"Emergency key release failed for key vk=0x{k.vk_code:02X}, scan=0x{k.scan_code:04X}")
                            break
                    except Exception as e:
                        self.lock_state(f"Exception during emergency key release for key {k}: {e}")
                        break
                sanitized.append(k)

            return sanitized

    def clear_all_test_only(self) -> None:
        """Utility for test fixtures only."""
        with self._lock:
            self._pressed_keys.clear()
            self._is_locked = False
            self._lockout_reason = None
            self._active_recovery_token = None
