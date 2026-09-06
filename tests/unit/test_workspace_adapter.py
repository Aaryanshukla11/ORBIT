"""Unit tests for ProductionWorkspaceAdapter lifecycle, operations, and health reporting."""

from __future__ import annotations

import asyncio
from typing import Optional
import pytest

from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.adapters.workspace.appbar import AppBarOperationResult, NativeAppBarDriver
from orbit.adapters.workspace.geometry import (
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
from orbit.adapters.workspace.watchdog import (
    WorkspaceHealthStatus,
    WorkspaceProbeResult,
    WorkspaceWatchdog,
    WorkspaceWatchdogPolicy,
)
from orbit.contracts.capabilities import (
    CapabilityHealthStatus,
    CapabilityLifecycleState,
)
from orbit.models.common import BoundingBox


class FakeWindowHolder:
    def __init__(self, hwnd: int = 4242, rect: Optional[BoundingBox] = None) -> None:
        self.hwnd = hwnd
        self.rect = rect or BoundingBox(left=1440, top=0, width=480, height=1080)

    def set_position(self, rect: BoundingBox) -> None:
        self.rect = rect


class FakeAppBarDriver(NativeAppBarDriver):
    def __init__(self) -> None:
        self._fake_window = FakeWindowHolder()
        self._fake_edge = DockEdge.NONE
        self._fake_bounds = None
        self._is_docked = False

    @property
    def window(self):
        return self._fake_window

    @property
    def dock_edge(self) -> DockEdge:
        return self._fake_edge

    @property
    def docked_bounds(self) -> Optional[BoundingBox]:
        return self._fake_bounds

    @property
    def is_docked(self) -> bool:
        return self._is_docked

    def register_and_dock(
        self,
        edge: DockEdge,
        requested_size_px: int,
        state_manager: Optional[WorkspaceStateManager] = None,
        custom_target_rect: Optional[BoundingBox] = None,
    ) -> AppBarOperationResult:
        self._fake_edge = edge
        self._fake_bounds = BoundingBox(left=1440, top=0, width=requested_size_px, height=1080)
        self._is_docked = True
        if state_manager:
            state_manager.transition_to(WorkspaceState.REGISTERING)
            state_manager.transition_to(WorkspaceState.DOCKED)
        return AppBarOperationResult(
            operation="SETPOS",
            success=True,
            edge=edge,
            requested_rect=self._fake_bounds,
            negotiated_rect=self._fake_bounds,
            final_rect=self._fake_bounds,
        )

    def unregister_and_release(
        self,
        state_manager: Optional[WorkspaceStateManager] = None,
    ) -> AppBarOperationResult:
        prev_edge = self._fake_edge
        prev_bounds = self._fake_bounds
        self._is_docked = False
        self._fake_edge = DockEdge.NONE
        self._fake_bounds = None
        if state_manager:
            state_manager.transition_to(WorkspaceState.RELEASING)
            state_manager.transition_to(WorkspaceState.READY_FLOATING)
        req_rect = prev_bounds or BoundingBox(left=0, top=0, width=480, height=1080)
        return AppBarOperationResult(
            operation="REMOVE",
            success=True,
            edge=prev_edge,
            requested_rect=req_rect,
            negotiated_rect=None,
            final_rect=None,
        )


@pytest.mark.asyncio
async def test_workspace_adapter_initialization_success():
    sm = WorkspaceStateManager()
    driver = FakeAppBarDriver()
    adapter = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        state_manager=sm,
        appbar_driver=driver,
    )

    assert adapter.is_ready is False
    await adapter.initialize()
    assert adapter.is_ready is True
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert sm.current_state == WorkspaceState.READY_FLOATING

    # Shutdown
    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED
    assert sm.current_state == WorkspaceState.STOPPED


@pytest.mark.asyncio
async def test_workspace_adapter_register_and_unregister_appbar():
    sm = WorkspaceStateManager()
    driver = FakeAppBarDriver()
    adapter = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        state_manager=sm,
        appbar_driver=driver,
    )
    await adapter.initialize()
    geom_init = await adapter.get_geometry()
    initial_width = geom_init.work_area.width
    gen_init = adapter.get_desktop_generation()

    # Register AppBar
    res = await adapter.register_appbar("right", 480)
    assert res is True
    assert sm.is_docked is True
    assert adapter.get_desktop_generation() > gen_init
    gen_docked = adapter.get_desktop_generation()

    # Work area should reflect dock subtraction
    work_area = await adapter.get_work_area()
    assert work_area.width == initial_width - 480

    # Unregister AppBar
    res_un = await adapter.unregister_appbar()
    assert res_un is True
    assert sm.is_docked is False
    assert adapter.get_desktop_generation() > gen_docked

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_workspace_adapter_shutdown_idempotence():
    adapter = ProductionWorkspaceAdapter(auto_start_watchdog=False)
    await adapter.initialize()
    assert adapter.is_ready is True

    # First shutdown
    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED

    # Second shutdown must be safe
    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED


@pytest.mark.asyncio
async def test_workspace_adapter_health_reporting():
    adapter = ProductionWorkspaceAdapter(auto_start_watchdog=False)
    await adapter.initialize()

    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.HEALTHY
    assert health.capability_name == "ProductionWorkspace"
    assert "desktop_generation_id" in health.details
    assert "state" in health.details

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_workspace_adapter_coordinate_validation():
    adapter = ProductionWorkspaceAdapter(auto_start_watchdog=False)
    await adapter.initialize()

    gen = adapter.get_desktop_generation()
    val = adapter.validate_coordinate(500, 300, expected_generation=gen)
    assert val.is_valid is True
    assert val.status == CoordinateValidationStatus.VALID

    # Stale generation check
    val_stale = adapter.validate_coordinate(500, 300, expected_generation=gen + 99)
    assert val_stale.is_valid is False
    assert val_stale.status == CoordinateValidationStatus.STALE_COORDINATE_CONTEXT

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_workspace_adapter_recovery():
    sm = WorkspaceStateManager()
    adapter = ProductionWorkspaceAdapter(auto_start_watchdog=False, state_manager=sm)
    await adapter.initialize()

    # Force DEGRADED state
    sm.transition_to(WorkspaceState.DEGRADED, reason="Test degradation")
    assert sm.current_state == WorkspaceState.DEGRADED

    # Recover
    recovered = await adapter.recover_workspace(recovery_token="CONFIRM_RESET")
    assert recovered is True
    assert sm.current_state == WorkspaceState.READY_FLOATING

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_workspace_adapter_repeated_initialize_idempotent():
    adapter = ProductionWorkspaceAdapter(auto_start_watchdog=False)
    await adapter.initialize()
    assert adapter.is_ready is True
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY

    # Second initialization must be completely idempotent and safe
    await adapter.initialize()
    assert adapter.is_ready is True
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_workspace_adapter_repeated_unregister_idempotent():
    sm = WorkspaceStateManager()
    driver = FakeAppBarDriver()
    adapter = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        state_manager=sm,
        appbar_driver=driver,
    )
    await adapter.initialize()

    # Unregister when already floating -> idempotent True
    assert sm.is_docked is False
    res = await adapter.unregister_appbar()
    assert res is True
    assert sm.is_docked is False

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_workspace_adapter_failed_state_operator_recovery():
    sm = WorkspaceStateManager()
    adapter = ProductionWorkspaceAdapter(auto_start_watchdog=False, state_manager=sm)
    await adapter.initialize()

    # Transition to FAILED state
    sm.transition_to(WorkspaceState.FAILED, reason="Simulated critical failure")
    assert sm.current_state == WorkspaceState.FAILED

    # Health reflects FAILED
    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.FAILED

    # Recover with operator token
    recovered = await adapter.recover_workspace(recovery_token="CONFIRM_OPERATOR_MANUAL_RESET")
    assert recovered is True
    assert sm.current_state == WorkspaceState.READY_FLOATING

    health_recovered = await adapter.get_health()
    assert health_recovered.status == CapabilityHealthStatus.HEALTHY

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_workspace_adapter_watchdog_start_stop_cycles():
    adapter = ProductionWorkspaceAdapter(auto_start_watchdog=False)
    await adapter.initialize()

    assert adapter.watchdog.is_running is False

    # Cycle 1
    await adapter.watchdog.start()
    assert adapter.watchdog.is_running is True
    await adapter.watchdog.stop()
    assert adapter.watchdog.is_running is False

    # Cycle 2
    await adapter.watchdog.start()
    assert adapter.watchdog.is_running is True
    await adapter.watchdog.stop()
    assert adapter.watchdog.is_running is False

    await adapter.shutdown()

