"""Unit and coordination tests for WorkspaceGeometryCoordinator, multi-monitor topology, and DPI safety."""

from __future__ import annotations

from typing import Dict, List, Optional
import pytest

from orbit.adapters.observation.freshness import FreshnessEvaluator
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
)
from orbit.adapters.workspace.geometry import (
    CoordinateValidationResult,
    CoordinateValidationStatus,
    Win32TopologyGateway,
    WorkspaceGeometryCoordinator,
)
from orbit.adapters.workspace.state import WorkspaceStateManager
from orbit.adapters.workspace.types import (
    DisplayMonitorInfo,
    DockEdge,
    WorkspaceGeometry,
    WorkspaceState,
)
from orbit.models.common import BoundingBox


class FakeTopologyGateway(Win32TopologyGateway):
    """Deterministic fake gateway for multi-monitor, negative coordinates, and DPI test matrices."""

    def __init__(
        self,
        virtual_metrics: Optional[Dict[str, int]] = None,
        monitors: Optional[List[DisplayMonitorInfo]] = None,
        system_dpi: int = 96,
    ) -> None:
        super().__init__()
        self._metrics = virtual_metrics or {
            "left": 0,
            "top": 0,
            "width": 1920,
            "height": 1080,
            "monitor_count": 1,
        }
        self._monitors = monitors or [
            DisplayMonitorInfo(
                h_monitor=1001,
                bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
                work_area=BoundingBox(left=0, top=0, width=1920, height=1040),
                is_primary=True,
                dpi=system_dpi,
                scale_factor=round(system_dpi / 96.0, 4),
                device_name="\\\\.\\DISPLAY1",
            )
        ]
        self._system_dpi = system_dpi

    def get_virtual_desktop_metrics(self) -> Dict[str, int]:
        return dict(self._metrics)

    def get_system_dpi(self) -> int:
        return self._system_dpi

    def enumerate_monitors(self) -> List[DisplayMonitorInfo]:
        return list(self._monitors)


def test_geometry_single_monitor_default():
    sm = WorkspaceStateManager()
    gw = FakeTopologyGateway(system_dpi=192)
    coord = WorkspaceGeometryCoordinator(state_manager=sm, gateway=gw)

    geom = coord.query_current_geometry()
    assert geom.physical_display == BoundingBox(left=0, top=0, width=1920, height=1080)
    assert geom.work_area == BoundingBox(left=0, top=0, width=1920, height=1040)
    assert geom.dpi == 192
    assert geom.scale_factor == 2.0
    assert geom.is_docked is False
    assert len(geom.monitors) == 1
    assert geom.monitors[0].is_primary is True


def test_geometry_multi_monitor_topology():
    mon1 = DisplayMonitorInfo(
        h_monitor=1001,
        bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
        work_area=BoundingBox(left=0, top=0, width=1920, height=1040),
        is_primary=True,
        dpi=96,
        device_name="\\\\.\\DISPLAY1",
    )
    mon2 = DisplayMonitorInfo(
        h_monitor=1002,
        bounds=BoundingBox(left=1920, top=0, width=1920, height=1080),
        work_area=BoundingBox(left=1920, top=0, width=1920, height=1080),
        is_primary=False,
        dpi=144,
        scale_factor=1.5,
        device_name="\\\\.\\DISPLAY2",
    )
    gw = FakeTopologyGateway(
        virtual_metrics={"left": 0, "top": 0, "width": 3840, "height": 1080, "monitor_count": 2},
        monitors=[mon1, mon2],
    )
    coord = WorkspaceGeometryCoordinator(gateway=gw)
    geom = coord.query_current_geometry()

    assert geom.physical_display.width == 3840
    assert len(geom.monitors) == 2

    # Coordinate on Monitor 1
    res1 = coord.validate_coordinate(500, 500)
    assert res1.is_valid is True
    assert res1.target_monitor_index == 0
    assert res1.target_monitor_device == "\\\\.\\DISPLAY1"

    # Coordinate on Monitor 2
    res2 = coord.validate_coordinate(2500, 500)
    assert res2.is_valid is True
    assert res2.target_monitor_index == 1
    assert res2.target_monitor_device == "\\\\.\\DISPLAY2"


def test_geometry_negative_origin_virtual_desktop():
    # Secondary monitor placed to the left of primary monitor
    sec_mon = DisplayMonitorInfo(
        h_monitor=2001,
        bounds=BoundingBox(left=-1920, top=0, width=1920, height=1080),
        work_area=BoundingBox(left=-1920, top=0, width=1920, height=1080),
        is_primary=False,
        dpi=96,
        device_name="\\\\.\\DISPLAY_LEFT",
    )
    pri_mon = DisplayMonitorInfo(
        h_monitor=2002,
        bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
        work_area=BoundingBox(left=0, top=0, width=1920, height=1040),
        is_primary=True,
        dpi=96,
        device_name="\\\\.\\DISPLAY_PRI",
    )
    gw = FakeTopologyGateway(
        virtual_metrics={"left": -1920, "top": 0, "width": 3840, "height": 1080, "monitor_count": 2},
        monitors=[sec_mon, pri_mon],
    )
    coord = WorkspaceGeometryCoordinator(gateway=gw)
    geom = coord.query_current_geometry()

    assert geom.physical_display == BoundingBox(left=-1920, top=0, width=3840, height=1080)

    # Validate point with negative X
    res_neg = coord.validate_coordinate(-500, 300)
    assert res_neg.is_valid is True
    assert res_neg.x == -500
    assert res_neg.target_monitor_index == 0
    assert res_neg.target_monitor_device == "\\\\.\\DISPLAY_LEFT"


def test_geometry_docked_workspace_work_area_subtraction():
    sm = WorkspaceStateManager()
    gw = FakeTopologyGateway()
    coord = WorkspaceGeometryCoordinator(state_manager=sm, gateway=gw)

    # Dock on RIGHT edge with 480px width
    dock_bounds = BoundingBox(left=1440, top=0, width=480, height=1080)
    geom = coord.query_current_geometry(
        dock_edge=DockEdge.RIGHT,
        docked_bounds=dock_bounds,
        is_docked=True,
    )

    assert geom.is_docked is True
    assert geom.work_area == BoundingBox(left=0, top=0, width=1440, height=1080)

    # Point in usable canvas
    res_canvas = coord.validate_coordinate(500, 500, target_geometry=geom)
    assert res_canvas.is_valid is True
    assert res_canvas.in_usable_canvas is True
    assert res_canvas.in_docked_area is False

    # Point in reserved dock area
    res_dock = coord.validate_coordinate(1500, 500, target_geometry=geom)
    assert res_dock.is_valid is False
    assert res_dock.status == CoordinateValidationStatus.RESERVED_WORKSPACE_COLLISION
    assert res_dock.in_docked_area is True


def test_geometry_docked_workspace_left_top_bottom():
    coord = WorkspaceGeometryCoordinator(gateway=FakeTopologyGateway())

    # LEFT dock
    geom_l = coord.query_current_geometry(
        dock_edge=DockEdge.LEFT,
        docked_bounds=BoundingBox(left=0, top=0, width=400, height=1080),
        is_docked=True,
    )
    assert geom_l.work_area == BoundingBox(left=400, top=0, width=1520, height=1080)

    # TOP dock
    geom_t = coord.query_current_geometry(
        dock_edge=DockEdge.TOP,
        docked_bounds=BoundingBox(left=0, top=0, width=1920, height=200),
        is_docked=True,
    )
    assert geom_t.work_area == BoundingBox(left=0, top=200, width=1920, height=880)

    # BOTTOM dock
    geom_b = coord.query_current_geometry(
        dock_edge=DockEdge.BOTTOM,
        docked_bounds=BoundingBox(left=0, top=880, width=1920, height=200),
        is_docked=True,
    )
    assert geom_b.work_area == BoundingBox(left=0, top=0, width=1920, height=880)


def test_coordinate_validation_generation_parity():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    gen_init = sm.desktop_generation_id

    coord = WorkspaceGeometryCoordinator(state_manager=sm, gateway=FakeTopologyGateway())

    # Valid under current generation
    res1 = coord.validate_coordinate(100, 100, expected_generation=gen_init)
    assert res1.is_valid is True
    assert res1.status == CoordinateValidationStatus.VALID

    # Material workspace change (docking increments desktop_generation_id)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)
    gen_after_dock = sm.desktop_generation_id
    assert gen_after_dock > gen_init

    # Stale coordinate evaluated under gen_init must be rejected fail-closed
    res_stale = coord.validate_coordinate(100, 100, expected_generation=gen_init)
    assert res_stale.is_valid is False
    assert res_stale.status == CoordinateValidationStatus.STALE_COORDINATE_CONTEXT
    assert res_stale.tested_generation_id == gen_init
    assert res_stale.active_generation_id == gen_after_dock

    # Fresh coordinate evaluated under active generation passes
    res_fresh = coord.validate_coordinate(100, 100, expected_generation=gen_after_dock)
    assert res_fresh.is_valid is True


def test_coordinate_validation_out_of_bounds():
    coord = WorkspaceGeometryCoordinator(gateway=FakeTopologyGateway())

    # Beyond right border (width 1920)
    res_oob_right = coord.validate_coordinate(2000, 500)
    assert res_oob_right.is_valid is False
    assert res_oob_right.status == CoordinateValidationStatus.OUT_OF_BOUNDS

    # Negative when display starts at 0
    res_oob_neg = coord.validate_coordinate(-10, 500)
    assert res_oob_neg.is_valid is False
    assert res_oob_neg.status == CoordinateValidationStatus.OUT_OF_BOUNDS


def test_observation_snapshot_generation_coordination():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    evaluator = FreshnessEvaluator(max_ttl_ms=500.0)

    import time
    now_ns = time.perf_counter_ns()

    # Snapshot captured under generation 1
    snap = ObservationSnapshot(
        snapshot_id="snap_coord_test_1",
        generation_id=sm.desktop_generation_id,
        timestamp_ns=now_ns,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
    )

    # Valid while generation is identical
    state, is_stale, reason = evaluator.evaluate_freshness(snap, current_generation=sm.desktop_generation_id)
    assert state == FreshnessState.FRESH
    assert is_stale is False

    # Dock workspace -> generation increments
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)

    # Re-evaluate snapshot -> must be STALE due to GENERATION_MISMATCH
    state2, is_stale2, reason2 = evaluator.evaluate_freshness(snap, current_generation=sm.desktop_generation_id)
    assert state2 == FreshnessState.STALE
    assert is_stale2 is True
    assert "GENERATION_MISMATCH" in str(reason2)


def test_dpi_scale_factor_calculations():
    # Test DPI 96 (1.0x baseline)
    info_96 = DisplayMonitorInfo(
        bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
        work_area=BoundingBox(left=0, top=0, width=1920, height=1040),
        dpi=96,
    )
    assert info_96.scale_factor == 1.0

    # Test DPI 144 (1.5x)
    info_144 = DisplayMonitorInfo(
        bounds=BoundingBox(left=0, top=0, width=1920, height=1080),
        work_area=BoundingBox(left=0, top=0, width=1920, height=1040),
        dpi=144,
    )
    assert info_144.scale_factor == 1.5

    # Test DPI 192 (2.0x)
    info_192 = DisplayMonitorInfo(
        bounds=BoundingBox(left=0, top=0, width=2880, height=1800),
        work_area=BoundingBox(left=0, top=0, width=2880, height=1800),
        dpi=192,
    )
    assert info_192.scale_factor == 2.0


def test_pointer_stale_generation_prevention():
    """Verify that pointer validation gates block dispatch when evaluated against a stale generation."""
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    gen1 = sm.desktop_generation_id

    coord = WorkspaceGeometryCoordinator(state_manager=sm, gateway=FakeTopologyGateway())

    # Initial validation passes
    v1 = coord.validate_coordinate(200, 200, expected_generation=gen1)
    assert v1.is_valid is True

    # Topology or workspace change occurs
    sm.increment_desktop_generation()
    gen2 = sm.desktop_generation_id
    assert gen2 > gen1

    # Stale generation check fails
    v2 = coord.validate_coordinate(200, 200, expected_generation=gen1)
    assert v2.is_valid is False
    assert v2.status == CoordinateValidationStatus.STALE_COORDINATE_CONTEXT


def test_live_topology_query():
    """Live OS query ensuring native Win32 calls run without errors on host."""
    gw = Win32TopologyGateway()
    metrics = gw.get_virtual_desktop_metrics()
    assert metrics["width"] > 0
    assert metrics["height"] > 0
    assert metrics["monitor_count"] >= 1

    monitors = gw.enumerate_monitors()
    assert len(monitors) >= 1
    primary_mon = next((m for m in monitors if m.is_primary), None)
    assert primary_mon is not None
    assert primary_mon.bounds.width > 0
    assert primary_mon.dpi >= 96
    assert primary_mon.scale_factor >= 1.0

    coord = WorkspaceGeometryCoordinator(gateway=gw)
    geom = coord.query_current_geometry()
    assert geom.physical_display.width > 0
    assert geom.dpi >= 96
