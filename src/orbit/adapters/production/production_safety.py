"""Production Emergency Safety Coordinator for ORBIT fail-safe hardware sanitization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityType,
    EmergencySafetyCoordinator,
)

if TYPE_CHECKING:
    from orbit.adapters.registry import CapabilityRegistry

logger = logging.getLogger(__name__)


class ProductionSafetyCoordinator(BaseCapabilityAdapter, EmergencySafetyCoordinator):
    """Production emergency safety coordinator for global fail-safe shutdowns."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None) -> None:
        super().__init__(
            capability_name="ProductionSafety",
            capability_type=CapabilityType.SAFETY,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self._registry = registry
        self._is_safe = True
        self._details = {"integration_status": "BOUNDARY_ESTABLISHED"}

    def set_registry(self, registry: CapabilityRegistry) -> None:
        """Sets the capability registry for coordinating emergency release."""
        self._registry = registry

    async def _on_initialize(self) -> None:
        self._details["integration_status"] = "ACTIVE"
        logger.info("ProductionSafetyCoordinator active and ready for emergency coordination")

    async def emergency_stop_all(self) -> bool:
        """Coordinates fail-closed emergency release across pointer and keyboard capabilities."""
        logger.warning("Production emergency_stop_all triggered across registered capabilities")
        all_success = True

        if self._registry:
            # 1. Release synthetic pointer buttons
            ptr = self._registry.get_optional(CapabilityType.POINTER)
            if ptr and hasattr(ptr, "emergency_release_all"):
                try:
                    res = await ptr.emergency_release_all()
                    if not res:
                        all_success = False
                        logger.error("Pointer emergency_release_all returned False")
                except Exception as ex:
                    logger.error("Exception during pointer emergency_release_all: %s", ex)
                    all_success = False

            # 2. Release synthetic keyboard keys / modifiers
            kbd = self._registry.get_optional(CapabilityType.KEYBOARD)
            if kbd and hasattr(kbd, "emergency_release_all"):
                try:
                    res = await kbd.emergency_release_all()
                    if not res:
                        all_success = False
                        logger.error("Keyboard emergency_release_all returned False")
                except Exception as ex:
                    logger.error("Exception during keyboard emergency_release_all: %s", ex)
                    all_success = False

        self._is_safe = all_success
        return all_success

    async def is_safe_state(self) -> bool:
        return self._is_safe
