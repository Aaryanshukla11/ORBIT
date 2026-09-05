"""Production Pointer Adapter boundary for ORBIT."""

from __future__ import annotations

import logging
from typing import Optional

from orbit.adapters.base import BaseCapabilityAdapter, CapabilityUnavailableError, PointerError
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityType,
    PointerCapability,
)
from orbit.models.common import ScreenPoint

logger = logging.getLogger(__name__)


class ProductionPointerAdapter(BaseCapabilityAdapter, PointerCapability):
    """Production adapter boundary bridging ORBIT Runtime to Prototype E (Safe Pointer Engine)."""

    def __init__(self, enable_live_injection: bool = False) -> None:
        super().__init__(
            capability_name="ProductionPointer",
            capability_type=CapabilityType.POINTER,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self._enable_live_injection = enable_live_injection
        self._lockout_state = "NORMAL"
        self._details = {"integration_status": "BOUNDARY_ESTABLISHED", "live_injection_enabled": enable_live_injection}

    async def _on_initialize(self) -> None:
        if not self._enable_live_injection:
            # M1A honesty: Live pointer injection integration is scheduled for Milestone M2
            self._details["integration_status"] = "INTEGRATION_DEFERRED_TO_M2"
            raise PointerError(
                "Production pointer live injection is deferred to Milestone M2; live injection is not enabled",
                recoverable=False,
            )
        self._details["integration_status"] = "ACTIVE"

    async def move_to(self, x: int, y: int, duration_ms: float = 0.0) -> bool:
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )
        raise NotImplementedError("Live pointer movement not authorized in M1A")

    async def click(self, x: int, y: int, button: str = "left", count: int = 1) -> bool:
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )
        raise NotImplementedError("Live pointer clicking not authorized in M1A")

    async def press_down(self, button: str = "left") -> bool:
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )
        raise NotImplementedError("Live pointer press not authorized in M1A")

    async def release_up(self, button: str = "left") -> bool:
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )
        raise NotImplementedError("Live pointer release not authorized in M1A")

    async def get_cursor_position(self) -> ScreenPoint:
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )
        raise NotImplementedError("Live cursor readback not authorized in M1A")

    async def emergency_release_all(self) -> bool:
        # Emergency release is always safe to call
        logger.info("ProductionPointer emergency release called")
        return True

    async def get_lockout_state(self) -> str:
        return self._lockout_state
