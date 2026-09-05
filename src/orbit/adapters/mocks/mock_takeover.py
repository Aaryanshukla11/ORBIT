"""Mock Human Takeover Adapter for Milestone M0 and M1A."""

from __future__ import annotations

from typing import Callable, Optional
from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityType,
    HumanTakeoverCapability,
)


class MockHumanTakeoverAdapter(BaseCapabilityAdapter, HumanTakeoverCapability):
    """Mock implementation of HumanTakeoverCapability with programmatic trigger support."""

    def __init__(self, health_status: CapabilityHealthStatus = CapabilityHealthStatus.HEALTHY) -> None:
        super().__init__(
            capability_name="MockHumanTakeover",
            capability_type=CapabilityType.HUMAN_TAKEOVER,
            adapter_mode=AdapterMode.MOCK,
        )
        self._health_status = health_status
        self._monitoring_active: bool = False
        self._takeover_active: bool = False
        self._callback: Optional[Callable[[], None]] = None
        self._details = {"is_monitoring": False, "is_takeover_active": False}

    @property
    def is_monitoring(self) -> bool:
        return self._monitoring_active

    async def start_monitoring(self, on_takeover_detected: Callable[[], None]) -> bool:
        self._callback = on_takeover_detected
        self._monitoring_active = True
        self._details["is_monitoring"] = True
        return True

    async def stop_monitoring(self) -> bool:
        self._monitoring_active = False
        self._callback = None
        self._details["is_monitoring"] = False
        return True

    async def is_takeover_active(self) -> bool:
        return self._takeover_active

    async def reset_takeover_state(self) -> bool:
        self._takeover_active = False
        self._details["is_takeover_active"] = False
        return True

    def trigger_takeover(self) -> None:
        """Simulate hardware-level human input detection."""
        self._takeover_active = True
        self._details["is_takeover_active"] = True
        if self._callback:
            self._callback()
