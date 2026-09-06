"""Mock Pointer Adapter for Milestone M0 and M1A."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityType,
    PointerCapability,
)
from orbit.models.common import ScreenPoint


class MockPointerAdapter(BaseCapabilityAdapter, PointerCapability):
    """Mock implementation of PointerCapability tracking cursor state in memory."""

    def __init__(
        self,
        initial_position: Optional[ScreenPoint] = None,
        health_status: CapabilityHealthStatus = CapabilityHealthStatus.HEALTHY,
    ) -> None:
        super().__init__(
            capability_name="MockPointer",
            capability_type=CapabilityType.POINTER,
            adapter_mode=AdapterMode.MOCK,
        )
        self._position = initial_position or ScreenPoint(x=500, y=500)
        self._health_status = health_status
        self._button_states: Dict[str, bool] = {"left": False, "right": False, "middle": False}
        self._lockout_state: str = "NORMAL"
        self._move_history: List[ScreenPoint] = [self._position]
        self._click_history: List[Dict[str, Any]] = []
        self._details = {"lockout_state": self._lockout_state, "position": self._position.model_dump()}

    @property
    def move_history(self) -> List[ScreenPoint]:
        return list(self._move_history)

    @property
    def click_history(self) -> List[Dict[str, Any]]:
        return list(self._click_history)

    @property
    def button_states(self) -> Dict[str, bool]:
        return dict(self._button_states)

    async def move_to(
        self,
        x: int,
        y: int,
        duration_ms: float = 0.0,
        cancellation_token: Optional[Any] = None,
    ) -> bool:
        if cancellation_token is not None and getattr(cancellation_token, "is_cancelled", False):
            return False
        self._position = ScreenPoint(x=x, y=y)
        self._move_history.append(self._position)
        self._details["position"] = self._position.model_dump()
        return True

    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        count: int = 1,
        dwell_ms: float = 50.0,
        cancellation_token: Optional[Any] = None,
    ) -> bool:
        if cancellation_token is not None and getattr(cancellation_token, "is_cancelled", False):
            return False
        if x is not None and y is not None:
            await self.move_to(x, y, cancellation_token=cancellation_token)
        target_x = x if x is not None else self._position.x
        target_y = y if y is not None else self._position.y
        self._click_history.append({"x": target_x, "y": target_y, "button": button, "count": count})
        return True




    async def press_down(self, button: str = "left") -> bool:
        self._button_states[button] = True
        return True

    async def release_up(self, button: str = "left") -> bool:
        self._button_states[button] = False
        return True

    async def get_cursor_position(self) -> ScreenPoint:
        return self._position

    async def emergency_release_all(self) -> bool:
        for btn in self._button_states:
            self._button_states[btn] = False
        return True

    async def get_lockout_state(self) -> str:
        return self._lockout_state

    def set_lockout_state(self, state: str) -> None:
        self._lockout_state = state
        self._details["lockout_state"] = state
