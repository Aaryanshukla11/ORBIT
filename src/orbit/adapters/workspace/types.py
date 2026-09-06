"""Domain models, typed enums, and geometry contracts for Workspace & AppBar."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from orbit.models.common import BoundingBox


class DockEdge(str, Enum):
    """Supported display docking edges for ORBIT Workspace."""

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    NONE = "NONE"

    @classmethod
    def from_string(cls, value: str) -> DockEdge:
        """Parse string to DockEdge enum safely with case insensitivity."""
        if not value:
            return cls.NONE
        val_upper = value.strip().upper()
        for member in cls:
            if member.value == val_upper:
                return member
        raise ValueError(f"Invalid DockEdge: '{value}'. Supported values: {[e.value for e in cls]}")


class WorkspaceState(str, Enum):
    """Discrete lifecycle states for ORBIT Workspace capability."""

    UNINITIALIZED = "UNINITIALIZED"
    READY_FLOATING = "READY_FLOATING"
    REGISTERING = "REGISTERING"
    DOCKED = "DOCKED"
    RELEASING = "RELEASING"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class DisplayMonitorInfo(BaseModel):
    """Physical and logical properties of an individual display monitor."""

    h_monitor: int = Field(default=0, description="Native Win32 HMONITOR handle value")
    bounds: BoundingBox = Field(..., description="Monitor full bounding box in virtual desktop coordinates")
    work_area: BoundingBox = Field(..., description="Monitor standard work area bounding box")
    is_primary: bool = Field(default=True, description="True if primary display monitor")
    dpi: int = Field(default=96, ge=1, description="Monitor DPI (dots per inch)")
    scale_factor: float = Field(default=1.0, gt=0.0, description="DPI scale factor relative to 96 DPI baseline")
    device_name: str = Field(default="", description="Win32 display device name (e.g. \\\\.\\DISPLAY1)")

    @model_validator(mode="before")
    @classmethod
    def populate_scale_factor(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if ("scale_factor" not in data or data["scale_factor"] is None) and "dpi" in data:
                dpi_val = data["dpi"]
                if isinstance(dpi_val, (int, float)) and dpi_val > 0:
                    data["scale_factor"] = max(0.1, round(float(dpi_val) / 96.0, 4))
        return data


class WorkspaceGeometry(BaseModel):
    """Multi-layer coordinate and layout model for desktop workspace and docked reservations."""

    physical_display: BoundingBox = Field(..., description="Full physical/virtual desktop screen bounds")
    work_area: BoundingBox = Field(..., description="Available application workspace canvas bounds")
    docked_bounds: Optional[BoundingBox] = None
    dock_edge: DockEdge = Field(default=DockEdge.NONE, description="Docked screen edge")
    reservation_width_px: int = Field(default=0, ge=0, description="Width in physical pixels allocated for dock")
    reservation_height_px: int = Field(default=0, ge=0, description="Height in physical pixels allocated for dock")
    is_docked: bool = Field(default=False, description="True if AppBar is actively registered and docked")
    dpi: int = Field(default=96, ge=1, description="Primary display DPI")
    scale_factor: float = Field(default=1.0, gt=0.0, description="Primary display DPI scale factor")
    topology_generation_id: int = Field(default=1, ge=1, description="Incremented on display topology/resolution change")
    desktop_generation_id: int = Field(default=1, ge=1, description="Incremented on workspace layout/docking change")
    monitors: List[DisplayMonitorInfo] = Field(default_factory=list, description="Attached display monitors")

    @model_validator(mode="before")
    @classmethod
    def populate_scale_factor(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if ("scale_factor" not in data or data["scale_factor"] is None) and "dpi" in data:
                dpi_val = data["dpi"]
                if isinstance(dpi_val, (int, float)) and dpi_val > 0:
                    data["scale_factor"] = max(0.1, round(float(dpi_val) / 96.0, 4))
        return data

    def is_point_in_docked_area(self, x: int, y: int) -> bool:
        """Check whether physical coordinates fall within the reserved ORBIT docked area."""
        if not self.is_docked or self.docked_bounds is None:
            return False
        b = self.docked_bounds
        return (b.left <= x < b.left + b.width) and (b.top <= y < b.top + b.height)

    def is_point_in_usable_canvas(self, x: int, y: int) -> bool:
        """Check whether physical coordinates fall within the usable workspace canvas."""
        w = self.work_area
        return (w.left <= x < w.left + w.width) and (w.top <= y < w.top + w.height)


class WorkspaceHealthDetails(BaseModel):
    """Structured diagnostic details payload for Workspace capability health reports."""

    state: WorkspaceState = Field(default=WorkspaceState.UNINITIALIZED)
    dock_edge: DockEdge = Field(default=DockEdge.NONE)
    is_docked: bool = Field(default=False)
    desktop_generation_id: int = Field(default=1)
    topology_generation_id: int = Field(default=1)
    monitor_count: int = Field(default=1)
    primary_dpi: int = Field(default=96)
    watchdog_active: bool = Field(default=False)
    last_error: Optional[str] = None
    extra_details: Dict[str, Any] = Field(default_factory=dict)
