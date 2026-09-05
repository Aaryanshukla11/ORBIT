"""Mock Workspace Adapter for Milestone M0 and M1A."""

from __future__ import annotations

from typing import Optional
from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityType,
    WorkspaceCapability,
)
from orbit.models.common import BoundingBox


class MockWorkspaceAdapter(BaseCapabilityAdapter, WorkspaceCapability):
    """Mock implementation of WorkspaceCapability managing virtual desktop work area."""

    def __init__(self, health_status: CapabilityHealthStatus = CapabilityHealthStatus.HEALTHY) -> None:
        super().__init__(
            capability_name="MockWorkspace",
            capability_type=CapabilityType.WORKSPACE,
            adapter_mode=AdapterMode.MOCK,
        )
        self._health_status = health_status
        self._appbar_registered: bool = False
        self._edge: Optional[str] = None
        self._size: int = 0
        self._work_area = BoundingBox(left=0, top=0, width=1920, height=1040)
        self._details = {"is_registered": False}

    @property
    def is_registered(self) -> bool:
        return self._appbar_registered

    async def register_appbar(self, edge: str, size: int) -> bool:
        self._appbar_registered = True
        self._edge = edge
        self._size = size
        if edge == "right":
            self._work_area = BoundingBox(left=0, top=0, width=1920 - size, height=1040)
        elif edge == "left":
            self._work_area = BoundingBox(left=size, top=0, width=1920 - size, height=1040)
        self._details["is_registered"] = True
        return True

    async def unregister_appbar(self) -> bool:
        self._appbar_registered = False
        self._edge = None
        self._size = 0
        self._work_area = BoundingBox(left=0, top=0, width=1920, height=1040)
        self._details["is_registered"] = False
        return True

    async def get_work_area(self) -> BoundingBox:
        return self._work_area
