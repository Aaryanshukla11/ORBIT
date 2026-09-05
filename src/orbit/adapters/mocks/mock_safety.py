"""Mock Emergency Safety Coordinator for Milestone M0 and M1A."""

from __future__ import annotations

from typing import List
from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityType,
    EmergencySafetyCoordinator,
)


class MockSafetyCoordinator(BaseCapabilityAdapter, EmergencySafetyCoordinator):
    """Mock safety coordinator that records emergency shutdown requests."""

    def __init__(self) -> None:
        super().__init__(
            capability_name="MockSafety",
            capability_type=CapabilityType.SAFETY,
            adapter_mode=AdapterMode.MOCK,
        )
        self._emergency_stops: List[str] = []
        self._is_safe: bool = True
        self._details = {"stop_count": 0}

    @property
    def stop_count(self) -> int:
        return len(self._emergency_stops)

    async def emergency_stop_all(self) -> bool:
        self._emergency_stops.append("EMERGENCY_STOP_TRIGGERED")
        self._is_safe = True
        self._details["stop_count"] = len(self._emergency_stops)
        return True

    async def is_safe_state(self) -> bool:
        return self._is_safe

    def set_unsafe_state(self) -> None:
        self._is_safe = False
