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
        self._desktop_generation_id: int = 0
        self._work_area = BoundingBox(left=0, top=0, width=1920, height=1040)
        self._details = {"is_registered": False, "desktop_generation_id": 0}

    @property
    def is_registered(self) -> bool:
        return self._appbar_registered

    @property
    def desktop_generation_id(self) -> int:
        return self._desktop_generation_id

    def get_desktop_generation(self) -> int:
        return self._desktop_generation_id

    async def register_appbar(self, edge: str, size: int) -> bool:
        self._appbar_registered = True
        self._edge = edge
        self._size = size
        self._desktop_generation_id += 1
        if edge == "right":
            self._work_area = BoundingBox(left=0, top=0, width=1920 - size, height=1040)
        elif edge == "left":
            self._work_area = BoundingBox(left=size, top=0, width=1920 - size, height=1040)
        self._details["is_registered"] = True
        self._details["desktop_generation_id"] = self._desktop_generation_id
        return True

    async def unregister_appbar(self) -> bool:
        self._appbar_registered = False
        self._edge = None
        self._size = 0
        self._desktop_generation_id += 1
        self._work_area = BoundingBox(left=0, top=0, width=1920, height=1040)
        self._details["is_registered"] = False
        self._details["desktop_generation_id"] = self._desktop_generation_id
        return True

    async def get_work_area(self) -> BoundingBox:
        return self._work_area

    def validate_coordinate(
        self,
        x: int,
        y: int,
        expected_generation: Optional[int] = None,
    ):
        from orbit.adapters.workspace.geometry import (
            CoordinateValidationResult,
            CoordinateValidationStatus,
        )
        active_gen = self._desktop_generation_id

        # 1. Generation parity
        if expected_generation is not None and expected_generation != active_gen:
            return CoordinateValidationResult(
                is_valid=False,
                status=CoordinateValidationStatus.STALE_COORDINATE_CONTEXT,
                x=x,
                y=y,
                active_generation_id=active_gen,
                tested_generation_id=expected_generation,
                error_message=(
                    f"Coordinate generation mismatch: target evaluated under generation "
                    f"{expected_generation}, active desktop generation is {active_gen}"
                ),
            )

        # 2. Virtual desktop bounds
        if not (0 <= x < 1920 and 0 <= y < 1080):
            return CoordinateValidationResult(
                is_valid=False,
                status=CoordinateValidationStatus.OUT_OF_BOUNDS,
                x=x,
                y=y,
                active_generation_id=active_gen,
                tested_generation_id=expected_generation,
                error_message=f"Coordinate ({x}, {y}) is outside virtual desktop bounds (0, 0, 1920x1080)",
            )

        # 3. Dock collision
        in_dock = False
        if self._appbar_registered:
            if self._edge == "right" and x >= (1920 - self._size):
                in_dock = True
            elif self._edge == "left" and x < self._size:
                in_dock = True

        if in_dock:
            return CoordinateValidationResult(
                is_valid=False,
                status=CoordinateValidationStatus.RESERVED_WORKSPACE_COLLISION,
                x=x,
                y=y,
                active_generation_id=active_gen,
                tested_generation_id=expected_generation,
                in_usable_canvas=False,
                in_docked_area=True,
                error_message=f"Coordinate ({x}, {y}) falls within reserved ORBIT docked workspace bounds",
            )

        return CoordinateValidationResult(
            is_valid=True,
            status=CoordinateValidationStatus.VALID,
            x=x,
            y=y,
            active_generation_id=active_gen,
            tested_generation_id=expected_generation,
            in_usable_canvas=True,
            in_docked_area=False,
        )

