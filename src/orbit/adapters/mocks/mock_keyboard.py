"""Mock Keyboard Adapter for Milestone M0 and M1A."""

from __future__ import annotations

from typing import Dict, List, Optional
from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityType,
    KeyboardCapability,
)


class MockKeyboardAdapter(BaseCapabilityAdapter, KeyboardCapability):
    """Mock implementation of KeyboardCapability recording typed text and keystrokes."""

    def __init__(self, health_status: CapabilityHealthStatus = CapabilityHealthStatus.HEALTHY) -> None:
        super().__init__(
            capability_name="MockKeyboard",
            capability_type=CapabilityType.KEYBOARD,
            adapter_mode=AdapterMode.MOCK,
        )
        self._health_status = health_status
        self._typed_history: List[str] = []
        self._shortcut_history: List[str] = []
        self._key_states: Dict[str, bool] = {}
        self._lockout_state: str = "NORMAL"

    @property
    def typed_history(self) -> List[str]:
        return list(self._typed_history)

    @property
    def shortcut_history(self) -> List[str]:
        return list(self._shortcut_history)

    async def type_text(self, text: str, delay_ms: float = 2.0, target_hwnd: Optional[int] = None) -> bool:
        self._typed_history.append(text)
        self._details["typed_count"] = len(self._typed_history)
        return True

    async def press_shortcut(self, combination: str, target_hwnd: Optional[int] = None) -> bool:
        self._shortcut_history.append(combination)
        return True

    async def press_key(self, key_code: str) -> bool:
        self._key_states[key_code] = True
        return True

    async def release_key(self, key_code: str) -> bool:
        self._key_states[key_code] = False
        return True

    async def emergency_release_all(self) -> bool:
        self._key_states.clear()
        return True

    async def get_lockout_state(self) -> str:
        return self._lockout_state

    def set_lockout_state(self, state: str) -> None:
        self._lockout_state = state
        self._details["lockout_state"] = state

    def recover_locked_state(self, token: str) -> bool:
        if token:
            self._lockout_state = "NORMAL"
            self._details["lockout_state"] = "NORMAL"
            return True
        return False
