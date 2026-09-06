"""Unit and integration tests for WorkspaceWatchdog, failure classification, and recovery policy."""

from __future__ import annotations

import asyncio
from typing import Optional
import pytest

from orbit.adapters.observation.freshness import FreshnessEvaluator
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
)
from orbit.adapters.workspace.geometry import (
    CoordinateValidationStatus,
    WorkspaceGeometryCoordinator,
)
from orbit.adapters.workspace.state import WorkspaceStateManager
from orbit.adapters.workspace.types import (
    DockEdge,
    WorkspaceGeometry,
    WorkspaceState,
)
from orbit.adapters.workspace.watchdog import (
    WatchdogNativeGateway,
    WorkspaceFailureCategory,
    WorkspaceHealthStatus,
    WorkspaceProbeResult,
    WorkspaceWatchdog,
    WorkspaceWatchdogPolicy,
)
from orbit.adapters.workspace.window import NativeWorkspaceWindow
from orbit.models.common import BoundingBox


class FakeWatchdogNativeGateway(WatchdogNativeGateway):
    """Deterministic fake gateway for simulating native Win32 window anomalies."""

    def __init__(
        self,
        window_exists: bool = True,
        window_rect: Optional[BoundingBox] = None,
        is_visible: bool = True,
    ) -> None:
        super().__init__()
        self._window_exists = window_exists
        self._window_rect = window_rect or BoundingBox(left=1440, top=0, width=480, height=1080)
        self._is_visible = is_visible
        self.set_position_calls: list[BoundingBox] = []

    def is_window(self, hwnd: int) -> bool:
        return self._window_exists

    def get_window_rect(self, hwnd: int) -> Optional[BoundingBox]:
        return self._window_rect

    def is_window_visible(self, hwnd: int) -> bool:
        return self._is_visible


class FakeWindowHolder:
    """Mock holder providing HWND and set_position for NativeAppBarDriver/NativeWorkspaceWindow."""

    def __init__(self, hwnd: int = 12345, rect: Optional[BoundingBox] = None) -> None:
        self.hwnd = hwnd
        self.rect = rect or BoundingBox(left=1440, top=0, width=480, height=1080)
        self.positions_set: list[BoundingBox] = []

    def set_position(self, rect: BoundingBox) -> None:
        self.rect = rect
        self.positions_set.append(rect)


class FakeAppBarDriver:
    """Mock AppBar driver for watchdog test isolation."""

    def __init__(self, window: Optional[FakeWindowHolder] = None) -> None:
        self.window = window or FakeWindowHolder()
        self.dock_edge = DockEdge.RIGHT
        self.docked_bounds = BoundingBox(left=1440, top=0, width=480, height=1080)
        self.is_docked = True


@pytest.mark.asyncio
async def test_watchdog_lifecycle_start_and_stop():
    sm = WorkspaceStateManager()
    gc = WorkspaceGeometryCoordinator(state_manager=sm)
    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        policy=WorkspaceWatchdogPolicy(poll_interval_sec=0.05),
    )

    assert wd.is_running is False

    # Start
    await wd.start()
    assert wd.is_running is True

    # Duplicate start is idempotent
    await wd.start()
    assert wd.is_running is True

    await asyncio.sleep(0.1)

    # Stop
    await wd.stop()
    assert wd.is_running is False

    # Duplicate stop is idempotent
    await wd.stop()
    assert wd.is_running is False


def test_watchdog_health_probe_floating_state():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    gen_before = sm.desktop_generation_id

    gc = WorkspaceGeometryCoordinator(state_manager=sm)
    wd = WorkspaceWatchdog(state_manager=sm, geometry_coordinator=gc)

    probe = wd.probe_health()
    assert probe.status == WorkspaceHealthStatus.HEALTHY
    assert probe.is_healthy is True
    assert probe.failure_category == WorkspaceFailureCategory.NONE
    assert sm.desktop_generation_id == gen_before


def test_watchdog_health_probe_docked_healthy():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)

    driver = FakeAppBarDriver()
    gw = FakeWatchdogNativeGateway(window_exists=True, window_rect=driver.docked_bounds)
    gc = WorkspaceGeometryCoordinator(state_manager=sm)

    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        appbar_driver=driver,
        gateway=gw,
    )

    probe = wd.probe_health()
    assert probe.status == WorkspaceHealthStatus.HEALTHY
    assert probe.is_healthy is True
    assert probe.failure_category == WorkspaceFailureCategory.NONE
    assert probe.hwnd == 12345


def test_watchdog_health_probe_window_destroyed_fails_closed():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)
    gen_docked = sm.desktop_generation_id

    driver = FakeAppBarDriver()
    # Simulate destroyed window
    gw = FakeWatchdogNativeGateway(window_exists=False)
    gc = WorkspaceGeometryCoordinator(state_manager=sm)

    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        appbar_driver=driver,
        gateway=gw,
    )

    probe = wd.probe_health()
    assert probe.status == WorkspaceHealthStatus.FAILED
    assert probe.is_healthy is False
    assert probe.failure_category == WorkspaceFailureCategory.WINDOW_DESTROYED
    assert probe.is_recoverable is False

    # State manager transitioned to FAILED
    assert sm.current_state == WorkspaceState.FAILED


@pytest.mark.asyncio
async def test_watchdog_health_probe_geometry_mismatch_and_recovery():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)

    driver = FakeAppBarDriver()
    # Simulate window drifted by 100px
    drifted_rect = BoundingBox(left=1340, top=0, width=480, height=1080)
    gw = FakeWatchdogNativeGateway(window_exists=True, window_rect=drifted_rect)
    gc = WorkspaceGeometryCoordinator(state_manager=sm)

    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        appbar_driver=driver,
        gateway=gw,
        policy=WorkspaceWatchdogPolicy(recovery_cooldown_sec=0.0),
    )

    probe = wd.probe_health()
    assert probe.status == WorkspaceHealthStatus.DEGRADED
    assert probe.failure_category == WorkspaceFailureCategory.GEOMETRY_MISMATCH
    assert probe.is_recoverable is True

    # Execute recovery
    recovered = await wd.attempt_recovery(probe)
    assert recovered is True
    assert len(driver.window.positions_set) == 1
    assert driver.window.positions_set[0] == driver.docked_bounds


@pytest.mark.asyncio
async def test_watchdog_recovery_budget_exhaustion():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)

    driver = FakeAppBarDriver()
    drifted_rect = BoundingBox(left=1340, top=0, width=480, height=1080)
    gw = FakeWatchdogNativeGateway(window_exists=True, window_rect=drifted_rect)
    gc = WorkspaceGeometryCoordinator(state_manager=sm)

    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        appbar_driver=driver,
        gateway=gw,
        policy=WorkspaceWatchdogPolicy(max_recovery_attempts=2, recovery_cooldown_sec=0.0),
    )

    # Trigger failure 1
    p1 = wd.probe_health()
    await wd.attempt_recovery(p1)

    # Trigger failure 2
    p2 = wd.probe_health()
    await wd.attempt_recovery(p2)

    # Trigger failure 3 (budget exhausted)
    p3 = wd.probe_health()
    rec3 = await wd.attempt_recovery(p3)
    assert rec3 is False

    # State manager transitioned to FAILED
    assert sm.current_state == WorkspaceState.FAILED


@pytest.mark.asyncio
async def test_watchdog_human_takeover_suppression():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)

    driver = FakeAppBarDriver()
    drifted_rect = BoundingBox(left=1340, top=0, width=480, height=1080)
    gw = FakeWatchdogNativeGateway(window_exists=True, window_rect=drifted_rect)
    gc = WorkspaceGeometryCoordinator(state_manager=sm)

    is_takeover = True

    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        appbar_driver=driver,
        gateway=gw,
        is_takeover_active_fn=lambda: is_takeover,
    )

    probe = wd.probe_health()
    assert probe.status == WorkspaceHealthStatus.DEGRADED

    # Recovery must be suppressed while takeover is active
    rec = await wd.attempt_recovery(probe)
    assert rec is False
    assert len(driver.window.positions_set) == 0


def test_watchdog_generation_invalidation_coordination():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)
    gen_docked = sm.desktop_generation_id

    evaluator = FreshnessEvaluator(max_ttl_ms=500.0)

    import time
    snap = ObservationSnapshot(
        snapshot_id="snap_watchdog_test",
        generation_id=gen_docked,
        timestamp_ns=time.perf_counter_ns(),
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
    )

    # Valid under docked generation
    state1, is_stale1, _ = evaluator.evaluate_freshness(snap, current_generation=sm.desktop_generation_id)
    assert state1 == FreshnessState.FRESH

    # Watchdog detects window destruction -> FAILED transition
    driver = FakeAppBarDriver()
    gw = FakeWatchdogNativeGateway(window_exists=False)
    gc = WorkspaceGeometryCoordinator(state_manager=sm)
    wd = WorkspaceWatchdog(state_manager=sm, geometry_coordinator=gc, appbar_driver=driver, gateway=gw)

    wd.probe_health()
    assert sm.current_state == WorkspaceState.FAILED

    # Increment generation on failure
    sm.increment_desktop_generation()

    # Observation snapshot is now STALE
    state2, is_stale2, reason2 = evaluator.evaluate_freshness(snap, current_generation=sm.desktop_generation_id)
    assert state2 == FreshnessState.STALE
    assert is_stale2 is True

    # Coordinate validation under gen_docked is rejected
    coord_res = gc.validate_coordinate(500, 500, expected_generation=gen_docked)
    assert coord_res.is_valid is False
    assert coord_res.status == CoordinateValidationStatus.STALE_COORDINATE_CONTEXT


@pytest.mark.asyncio
async def test_watchdog_live_os_probe():
    """Live OS test creating a real NativeWorkspaceWindow and running watchdog probe."""
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)

    win = NativeWorkspaceWindow()
    gc = WorkspaceGeometryCoordinator(state_manager=sm)

    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        window=win,
    )

    # Floating probe
    p_floating = wd.probe_health()
    assert p_floating.status == WorkspaceHealthStatus.HEALTHY

    # Start and stop watchdog loop live
    await wd.start()
    assert wd.is_running is True
    await asyncio.sleep(0.05)
    await wd.stop()
    assert wd.is_running is False
