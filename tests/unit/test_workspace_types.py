"""Unit tests for Workspace domain types, enums, and geometry contracts."""

import pytest
from pydantic import ValidationError

from orbit.adapters.workspace.types import (
    DisplayMonitorInfo,
    DockEdge,
    WorkspaceGeometry,
    WorkspaceHealthDetails,
    WorkspaceState,
)
from orbit.models.common import BoundingBox


def test_dock_edge_enum_values():
    assert DockEdge.LEFT.value == "LEFT"
    assert DockEdge.RIGHT.value == "RIGHT"
    assert DockEdge.TOP.value == "TOP"
    assert DockEdge.BOTTOM.value == "BOTTOM"
    assert DockEdge.NONE.value == "NONE"


def test_dock_edge_from_string():
    assert DockEdge.from_string("right") == DockEdge.RIGHT
    assert DockEdge.from_string("LEFT") == DockEdge.LEFT
    assert DockEdge.from_string(" Top ") == DockEdge.TOP
    assert DockEdge.from_string("bottom") == DockEdge.BOTTOM
    assert DockEdge.from_string("none") == DockEdge.NONE
    assert DockEdge.from_string("") == DockEdge.NONE


def test_dock_edge_invalid_string_raises():
    with pytest.raises(ValueError, match="Invalid DockEdge"):
        DockEdge.from_string("diagonal")


def test_workspace_state_enum_values():
    expected_states = {
        "UNINITIALIZED",
        "READY_FLOATING",
        "REGISTERING",
        "DOCKED",
        "RELEASING",
        "DEGRADED",
        "FAILED",
        "STOPPED",
    }
    actual_states = {s.value for s in WorkspaceState}
    assert actual_states == expected_states


def test_display_monitor_info_creation_and_scale_factor():
    mon = DisplayMonitorInfo(
        h_monitor=12345,
        bounds=BoundingBox(left=0, top=0, width=2880, height=1800),
        work_area=BoundingBox(left=0, top=0, width=2880, height=1800),
        is_primary=True,
        dpi=192,
        device_name="\\\\.\\DISPLAY1",
    )
    assert mon.h_monitor == 12345
    assert mon.dpi == 192
    assert mon.scale_factor == 2.0
    assert mon.is_primary is True


def test_workspace_geometry_valid_dimensions():
    geom = WorkspaceGeometry(
        physical_display=BoundingBox(left=0, top=0, width=2880, height=1800),
        work_area=BoundingBox(left=0, top=0, width=2160, height=1800),
        docked_bounds=BoundingBox(left=2160, top=0, width=720, height=1800),
        dock_edge=DockEdge.RIGHT,
        reservation_width_px=720,
        is_docked=True,
        dpi=192,
        desktop_generation_id=2,
    )
    assert geom.is_docked is True
    assert geom.dock_edge == DockEdge.RIGHT
    assert geom.reservation_width_px == 720
    assert geom.scale_factor == 2.0
    assert geom.desktop_generation_id == 2


def test_workspace_geometry_invalid_zero_dimension_raises():
    with pytest.raises(ValidationError):
        BoundingBox(left=0, top=0, width=0, height=1800)


def test_workspace_geometry_point_in_docked_area():
    geom = WorkspaceGeometry(
        physical_display=BoundingBox(left=0, top=0, width=2880, height=1800),
        work_area=BoundingBox(left=0, top=0, width=2160, height=1800),
        docked_bounds=BoundingBox(left=2160, top=0, width=720, height=1800),
        dock_edge=DockEdge.RIGHT,
        is_docked=True,
    )
    # Inside docked area
    assert geom.is_point_in_docked_area(2160, 0) is True
    assert geom.is_point_in_docked_area(2500, 900) is True
    assert geom.is_point_in_docked_area(2879, 1799) is True

    # Outside docked area
    assert geom.is_point_in_docked_area(2159, 900) is False
    assert geom.is_point_in_docked_area(500, 500) is False
    assert geom.is_point_in_docked_area(2880, 1800) is False


def test_workspace_geometry_point_in_usable_canvas():
    geom = WorkspaceGeometry(
        physical_display=BoundingBox(left=0, top=0, width=2880, height=1800),
        work_area=BoundingBox(left=0, top=0, width=2160, height=1800),
        docked_bounds=BoundingBox(left=2160, top=0, width=720, height=1800),
        dock_edge=DockEdge.RIGHT,
        is_docked=True,
    )
    # Inside usable canvas
    assert geom.is_point_in_usable_canvas(0, 0) is True
    assert geom.is_point_in_usable_canvas(1000, 500) is True
    assert geom.is_point_in_usable_canvas(2159, 1799) is True

    # Inside docked area (not in usable canvas)
    assert geom.is_point_in_usable_canvas(2160, 500) is False


def test_workspace_geometry_negative_origin_virtual_desktop():
    # Multi-monitor setup where monitor 2 is to the left: virtual desktop starts at -1920
    geom = WorkspaceGeometry(
        physical_display=BoundingBox(left=-1920, top=0, width=3840, height=1080),
        work_area=BoundingBox(left=-1920, top=0, width=3840, height=1080),
        dock_edge=DockEdge.NONE,
        is_docked=False,
    )
    assert geom.physical_display.left == -1920
    assert geom.is_point_in_usable_canvas(-1000, 500) is True
    assert geom.is_point_in_usable_canvas(-1921, 500) is False


def test_workspace_health_details_model():
    health = WorkspaceHealthDetails(
        state=WorkspaceState.READY_FLOATING,
        dock_edge=DockEdge.NONE,
        is_docked=False,
        desktop_generation_id=1,
        monitor_count=1,
        primary_dpi=192,
        watchdog_active=True,
    )
    assert health.state == WorkspaceState.READY_FLOATING
    assert health.watchdog_active is True
    assert health.primary_dpi == 192
