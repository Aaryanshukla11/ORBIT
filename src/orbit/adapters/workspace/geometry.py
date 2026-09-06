"""Authoritative Workspace Geometry Coordinator, Multi-Monitor Topology & DPI Engine."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
import logging
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from orbit.adapters.workspace.abi import (
    IS_64BIT,
    IS_WINDOWS,
    MDT_EFFECTIVE_DPI,
    MONITOR_DEFAULTTONEAREST,
    MONITORINFOF_PRIMARY,
    MONITORINFOEXW,
    RECT,
    SM_CMONITORS,
    SM_CXVIRTUALSCREEN,
    SM_CYVIRTUALSCREEN,
    SM_XVIRTUALSCREEN,
    SM_YVIRTUALSCREEN,
)
from orbit.adapters.workspace.state import WorkspaceStateManager
from orbit.adapters.workspace.telemetry import WorkspaceTelemetryRecorder
from orbit.adapters.workspace.types import (
    DisplayMonitorInfo,
    DockEdge,
    WorkspaceGeometry,
)
from orbit.models.common import BoundingBox

logger = logging.getLogger(__name__)

# Callback prototype for EnumDisplayMonitors
if IS_WINDOWS:
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )
else:
    MONITORENUMPROC = Any


# ============================================================================
# 1. Coordinate Validation Status & Result Models
# ============================================================================

class CoordinateValidationStatus(str, Enum):
    """Discrete outcome classifications for coordinate validation gates."""

    VALID = "VALID"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    STALE_COORDINATE_CONTEXT = "STALE_COORDINATE_CONTEXT"
    RESERVED_WORKSPACE_COLLISION = "RESERVED_WORKSPACE_COLLISION"
    GEOMETRY_UNAVAILABLE = "GEOMETRY_UNAVAILABLE"


@dataclass(frozen=True)
class CoordinateValidationResult:
    """Epistemically honest validation result for a target coordinate on the desktop."""

    is_valid: bool
    status: CoordinateValidationStatus
    x: int
    y: int
    active_generation_id: int
    tested_generation_id: Optional[int] = None
    in_usable_canvas: bool = False
    in_docked_area: bool = False
    target_monitor_index: Optional[int] = None
    target_monitor_device: Optional[str] = None
    error_message: Optional[str] = None


# ============================================================================
# 2. Native Win32 Topology Gateway
# ============================================================================

class Win32TopologyGateway:
    """Direct Win32 API wrapper for display topology and DPI queries."""

    def __init__(
        self,
        user32: Any = None,
        shcore: Any = None,
    ) -> None:
        if IS_WINDOWS:
            self._user32 = user32 or ctypes.WinDLL("user32", use_last_error=True)
            try:
                self._shcore = shcore or ctypes.WinDLL("shcore", use_last_error=True)
            except Exception:
                self._shcore = None
            self._setup_signatures()
        else:
            self._user32 = None
            self._shcore = None

    def _setup_signatures(self) -> None:
        if self._user32 is None:
            return

        # EnumDisplayMonitors
        self._user32.EnumDisplayMonitors.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(RECT),
            MONITORENUMPROC,
            wintypes.LPARAM,
        ]
        self._user32.EnumDisplayMonitors.restype = wintypes.BOOL

        # GetMonitorInfoW
        self._user32.GetMonitorInfoW.argtypes = [
            wintypes.HMONITOR,
            ctypes.POINTER(MONITORINFOEXW),
        ]
        self._user32.GetMonitorInfoW.restype = wintypes.BOOL

        # MonitorFromPoint
        self._user32.MonitorFromPoint.argtypes = [
            wintypes.POINT,
            wintypes.DWORD,
        ]
        self._user32.MonitorFromPoint.restype = wintypes.HMONITOR

        # MonitorFromRect
        self._user32.MonitorFromRect.argtypes = [
            ctypes.POINTER(RECT),
            wintypes.DWORD,
        ]
        self._user32.MonitorFromRect.restype = wintypes.HMONITOR

        # GetDpiForSystem
        if hasattr(self._user32, "GetDpiForSystem"):
            self._user32.GetDpiForSystem.argtypes = []
            self._user32.GetDpiForSystem.restype = wintypes.UINT

        # GetDpiForMonitor (shcore)
        if self._shcore is not None and hasattr(self._shcore, "GetDpiForMonitor"):
            self._shcore.GetDpiForMonitor.argtypes = [
                wintypes.HMONITOR,
                ctypes.c_int,
                ctypes.POINTER(wintypes.UINT),
                ctypes.POINTER(wintypes.UINT),
            ]
            self._shcore.GetDpiForMonitor.restype = ctypes.c_long

    def get_virtual_desktop_metrics(self) -> Dict[str, int]:
        """Query unified virtual desktop metrics from Win32."""
        if not IS_WINDOWS or self._user32 is None:
            return {"left": 0, "top": 0, "width": 1920, "height": 1080, "monitor_count": 1}

        left = self._user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = self._user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = self._user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = self._user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        count = self._user32.GetSystemMetrics(SM_CMONITORS)

        if width <= 0 or height <= 0:
            # Fallback to primary screen metrics if virtual screen returned 0
            width = self._user32.GetSystemMetrics(0)  # SM_CXSCREEN
            height = self._user32.GetSystemMetrics(1)  # SM_CYSCREEN
            left = 0
            top = 0

        return {
            "left": left,
            "top": top,
            "width": max(1, width),
            "height": max(1, height),
            "monitor_count": max(1, count),
        }

    def get_system_dpi(self) -> int:
        """Query system baseline DPI."""
        if IS_WINDOWS and self._user32 is not None and hasattr(self._user32, "GetDpiForSystem"):
            try:
                dpi = self._user32.GetDpiForSystem()
                if dpi > 0:
                    return int(dpi)
            except Exception:
                pass
        return 96

    def get_monitor_dpi(self, h_monitor: int) -> int:
        """Query per-monitor DPI via Shcore GetDpiForMonitor."""
        if IS_WINDOWS and self._shcore is not None and hasattr(self._shcore, "GetDpiForMonitor"):
            try:
                dpi_x = wintypes.UINT()
                dpi_y = wintypes.UINT()
                hr = self._shcore.GetDpiForMonitor(
                    wintypes.HMONITOR(h_monitor),
                    MDT_EFFECTIVE_DPI,
                    ctypes.byref(dpi_x),
                    ctypes.byref(dpi_y),
                )
                if hr == 0 and dpi_x.value > 0:
                    return int(dpi_x.value)
            except Exception as ex:
                logger.debug("GetDpiForMonitor query notice: %s", ex)
        return self.get_system_dpi()

    def enumerate_monitors(self) -> List[DisplayMonitorInfo]:
        """Enumerate all active physical and virtual display monitors."""
        if not IS_WINDOWS or self._user32 is None:
            # Synthetic default for non-Windows environments
            return [
                DisplayMonitorInfo(
                    h_monitor=1,
                    bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
                    work_area=BoundingBox(left=0, top=0, width=1920, height=1040),
                    is_primary=True,
                    dpi=96,
                    scale_factor=1.0,
                    device_name="\\\\.\\DISPLAY1",
                )
            ]

        monitors: List[DisplayMonitorInfo] = []

        def _enum_proc(h_mon: Any, hdc: Any, lprc: Any, lparam: Any) -> int:
            try:
                info = MONITORINFOEXW()
                info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                res = self._user32.GetMonitorInfoW(h_mon, ctypes.byref(info))
                if res:
                    is_primary = bool(info.dwFlags & MONITORINFOF_PRIMARY)
                    dpi = self.get_monitor_dpi(int(h_mon))
                    scale_factor = max(0.1, round(float(dpi) / 96.0, 4))
                    dev_name = str(info.szDevice)

                    mon_bounds = info.rcMonitor.to_bounding_box()
                    work_bounds = info.rcWork.to_bounding_box()

                    monitors.append(
                        DisplayMonitorInfo(
                            h_monitor=int(h_mon),
                            bounds=mon_bounds,
                            work_area=work_bounds,
                            is_primary=is_primary,
                            dpi=dpi,
                            scale_factor=scale_factor,
                            device_name=dev_name,
                        )
                    )
            except Exception as ex:
                logger.error("Error in MonitorEnumProc: %s", ex)
            return 1

        enum_callback = MONITORENUMPROC(_enum_proc)
        self._user32.EnumDisplayMonitors(None, None, enum_callback, 0)

        # Ensure at least one monitor is marked primary
        if monitors and not any(m.is_primary for m in monitors):
            monitors[0].is_primary = True

        return monitors

    def get_monitor_for_point(self, x: int, y: int) -> Optional[int]:
        """Resolve the HMONITOR containing the given physical desktop point."""
        if not IS_WINDOWS or self._user32 is None:
            return 1
        pt = wintypes.POINT(x=x, y=y)
        h_mon = self._user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        return int(h_mon) if h_mon else None


# ============================================================================
# 3. Workspace Geometry Coordinator
# ============================================================================

class WorkspaceGeometryCoordinator:
    """Authoritative coordinator for display geometry, multi-monitor topology, DPI, and generation safety."""

    def __init__(
        self,
        state_manager: Optional[WorkspaceStateManager] = None,
        telemetry: Optional[WorkspaceTelemetryRecorder] = None,
        gateway: Optional[Win32TopologyGateway] = None,
    ) -> None:
        self.state_manager = state_manager or WorkspaceStateManager()
        self.telemetry = telemetry
        self.gateway = gateway or Win32TopologyGateway()
        self._last_cached_geometry: Optional[WorkspaceGeometry] = None

    def get_active_desktop_generation(self) -> int:
        """Get the authoritative active desktop generation ID."""
        return self.state_manager.desktop_generation_id

    def get_active_topology_generation(self) -> int:
        """Get the authoritative active display topology generation ID."""
        return self.state_manager.topology_generation_id

    def query_current_geometry(
        self,
        dock_edge: DockEdge = DockEdge.NONE,
        docked_bounds: Optional[BoundingBox] = None,
        is_docked: bool = False,
    ) -> WorkspaceGeometry:
        """Query and compute the authoritative, current multi-monitor WorkspaceGeometry."""
        vmetrics = self.gateway.get_virtual_desktop_metrics()
        monitors = self.gateway.enumerate_monitors()

        virtual_box = BoundingBox(
            left=vmetrics["left"],
            top=vmetrics["top"],
            width=vmetrics["width"],
            height=vmetrics["height"],
        )

        # Determine primary monitor metrics
        primary_mon = next((m for m in monitors if m.is_primary), None)
        if primary_mon is None and monitors:
            primary_mon = monitors[0]

        primary_dpi = primary_mon.dpi if primary_mon else self.gateway.get_system_dpi()
        primary_scale = primary_mon.scale_factor if primary_mon else max(0.1, round(primary_dpi / 96.0, 4))

        # Determine usable work area
        if is_docked and docked_bounds is not None and dock_edge != DockEdge.NONE:
            usable_work_area = self._compute_docked_work_area(virtual_box, docked_bounds, dock_edge)
            res_w = docked_bounds.width
            res_h = docked_bounds.height
        else:
            # Baseline floating work area
            if primary_mon:
                usable_work_area = primary_mon.work_area
            else:
                usable_work_area = virtual_box
            res_w = 0
            res_h = 0

        geometry = WorkspaceGeometry(
            physical_display=virtual_box,
            work_area=usable_work_area,
            docked_bounds=docked_bounds if is_docked else None,
            dock_edge=dock_edge if is_docked else DockEdge.NONE,
            reservation_width_px=res_w,
            reservation_height_px=res_h,
            is_docked=is_docked,
            dpi=primary_dpi,
            scale_factor=primary_scale,
            topology_generation_id=self.state_manager.topology_generation_id,
            desktop_generation_id=self.state_manager.desktop_generation_id,
            monitors=monitors,
        )

        self._last_cached_geometry = geometry
        return geometry

    def validate_coordinate(
        self,
        x: int,
        y: int,
        expected_generation: Optional[int] = None,
        target_geometry: Optional[WorkspaceGeometry] = None,
    ) -> CoordinateValidationResult:
        """Validate a target coordinate against active geometry, boundaries, and generation parity."""
        geom = target_geometry or self._last_cached_geometry or self.query_current_geometry()
        active_gen = self.state_manager.desktop_generation_id

        # 1. Desktop Generation Parity Gate
        if expected_generation is not None and expected_generation != active_gen:
            return CoordinateValidationResult(
                is_valid=False,
                status=CoordinateValidationStatus.STALE_COORDINATE_CONTEXT,
                x=x,
                y=y,
                active_generation_id=active_gen,
                tested_generation_id=expected_generation,
                error_message=(
                    f"Coordinate generation mismatch: target was evaluated under generation "
                    f"{expected_generation}, but active desktop generation is {active_gen}"
                ),
            )

        # 2. Virtual Desktop Bounds Check
        vd = geom.physical_display
        if not (vd.left <= x < vd.left + vd.width and vd.top <= y < vd.top + vd.height):
            return CoordinateValidationResult(
                is_valid=False,
                status=CoordinateValidationStatus.OUT_OF_BOUNDS,
                x=x,
                y=y,
                active_generation_id=active_gen,
                tested_generation_id=expected_generation,
                error_message=f"Coordinate ({x}, {y}) is outside virtual desktop bounds ({vd.left}, {vd.top}, {vd.width}x{vd.height})",
            )

        # 3. Locate Target Monitor
        target_mon_idx: Optional[int] = None
        target_mon_dev: Optional[str] = None
        for idx, mon in enumerate(geom.monitors):
            b = mon.bounds
            if b.left <= x < b.left + b.width and b.top <= y < b.top + b.height:
                target_mon_idx = idx
                target_mon_dev = mon.device_name
                break

        # 4. Dock Collision Check
        in_dock = geom.is_point_in_docked_area(x, y)
        in_canvas = geom.is_point_in_usable_canvas(x, y)

        if in_dock:
            return CoordinateValidationResult(
                is_valid=False,
                status=CoordinateValidationStatus.RESERVED_WORKSPACE_COLLISION,
                x=x,
                y=y,
                active_generation_id=active_gen,
                tested_generation_id=expected_generation,
                in_usable_canvas=in_canvas,
                in_docked_area=True,
                target_monitor_index=target_mon_idx,
                target_monitor_device=target_mon_dev,
                error_message=f"Coordinate ({x}, {y}) falls within reserved ORBIT docked workspace bounds",
            )

        return CoordinateValidationResult(
            is_valid=True,
            status=CoordinateValidationStatus.VALID,
            x=x,
            y=y,
            active_generation_id=active_gen,
            tested_generation_id=expected_generation,
            in_usable_canvas=in_canvas,
            in_docked_area=False,
            target_monitor_index=target_mon_idx,
            target_monitor_device=target_mon_dev,
        )

    def _compute_docked_work_area(
        self,
        base_display: BoundingBox,
        docked_bounds: BoundingBox,
        dock_edge: DockEdge,
    ) -> BoundingBox:
        """Compute the remaining usable work area bounding box after subtracting docked reservation."""
        left = base_display.left
        top = base_display.top
        width = base_display.width
        height = base_display.height

        if dock_edge == DockEdge.RIGHT:
            width = max(1, width - docked_bounds.width)
        elif dock_edge == DockEdge.LEFT:
            left += docked_bounds.width
            width = max(1, width - docked_bounds.width)
        elif dock_edge == DockEdge.BOTTOM:
            height = max(1, height - docked_bounds.height)
        elif dock_edge == DockEdge.TOP:
            top += docked_bounds.height
            height = max(1, height - docked_bounds.height)

        return BoundingBox(
            left=left,
            top=top,
            width=width,
            height=height,
        )
