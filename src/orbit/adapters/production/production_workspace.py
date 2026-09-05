"""Production Workspace Adapter boundary for ORBIT."""

from __future__ import annotations

import logging
from typing import Optional

from orbit.adapters.base import BaseCapabilityAdapter, CapabilityUnavailableError, WorkspaceError
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityType,
    WorkspaceCapability,
)
from orbit.models.common import BoundingBox

logger = logging.getLogger(__name__)


class ProductionWorkspaceAdapter(BaseCapabilityAdapter, WorkspaceCapability):
    """Production adapter boundary bridging ORBIT Runtime to Prototype A (AppBar & Workspace)."""

    def __init__(self, enable_live_appbar: bool = False) -> None:
        super().__init__(
            capability_name="ProductionWorkspace",
            capability_type=CapabilityType.WORKSPACE,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self._enable_live_appbar = enable_live_appbar
        self._details = {"integration_status": "BOUNDARY_ESTABLISHED", "live_appbar_enabled": enable_live_appbar}

    async def _on_initialize(self) -> None:
        if not self._enable_live_appbar:
            # M1A honesty: Live AppBar integration is scheduled for Milestone M5
            self._details["integration_status"] = "INTEGRATION_DEFERRED_TO_M5"
            raise WorkspaceError(
                "Production workspace live AppBar is deferred to Milestone M5; live AppBar is not enabled",
                recoverable=False,
            )
        self._details["integration_status"] = "ACTIVE"

    async def register_appbar(self, edge: str, size: int) -> bool:
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production workspace adapter is not ready",
            )
        raise NotImplementedError("Live AppBar registration not authorized in M1A")

    async def unregister_appbar(self) -> bool:
        return True

    async def get_work_area(self) -> BoundingBox:
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production workspace adapter is not ready",
            )
        raise NotImplementedError("Live work area query not authorized in M1A")
