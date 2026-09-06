"""Integration tests for Production Workspace capability, runtime factory, and orchestrator lifecycle."""

from __future__ import annotations

import asyncio
from typing import Optional
import pytest

from orbit.adapters.factory import create_capability_registry
from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.observation.freshness import FreshnessEvaluator
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
)
from orbit.adapters.production import (
    ProductionWorkspaceAdapter,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.workspace.appbar import AppBarOperationResult, NativeAppBarDriver
from orbit.adapters.workspace.geometry import CoordinateValidationStatus
from orbit.adapters.workspace.state import WorkspaceStateManager
from orbit.adapters.workspace.types import DockEdge, WorkspaceState
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityLifecycleState,
    CapabilityType,
    WorkspaceCapability,
)
from orbit.contracts.runtime import Action, ActionTier, ExecutionPlan, Step, SystemState, TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.orchestrator import OrbitOrchestrator


class FakeAppBarDriver(NativeAppBarDriver):
    def __init__(self) -> None:
        self._fake_edge = DockEdge.NONE
        self._fake_bounds = None
        self._is_docked = False

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


def test_factory_creates_production_workspace_adapter():
    cfg = RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION)
    registry = create_capability_registry(cfg)

    adapter = registry.get_optional(CapabilityType.WORKSPACE)
    assert adapter is not None
    assert isinstance(adapter, ProductionWorkspaceAdapter)


@pytest.mark.asyncio
async def test_orchestrator_initialization_with_production_workspace(event_bus: EventBus):
    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    registry.register(CapabilityType.POINTER, MockPointerAdapter())
    registry.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    registry.register(CapabilityType.HUMAN_TAKEOVER, MockHumanTakeoverAdapter())
    
    prod_wsp = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        appbar_driver=FakeAppBarDriver(),
    )
    registry.register(CapabilityType.WORKSPACE, prod_wsp)
    registry.register(CapabilityType.SAFETY, MockSafetyCoordinator())

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    await orch.initialize()

    assert orch.system_state == SystemState.IDLE
    assert orch.workspace is not None
    assert orch.registry.is_ready(CapabilityType.WORKSPACE) is True

    # Shutdown
    await orch.shutdown()
    assert orch.system_state == SystemState.SHUTDOWN
    assert prod_wsp.lifecycle_state == CapabilityLifecycleState.STOPPED


@pytest.mark.asyncio
async def test_workspace_generation_coordination_with_observation_and_pointer(event_bus: EventBus):
    driver = FakeAppBarDriver()
    prod_wsp = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        appbar_driver=driver,
    )
    await prod_wsp.initialize()

    gen1 = prod_wsp.get_desktop_generation()
    evaluator = FreshnessEvaluator(max_ttl_ms=500.0)

    import time
    snap1 = ObservationSnapshot(
        snapshot_id="snap_gen1",
        generation_id=gen1,
        timestamp_ns=time.perf_counter_ns(),
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
    )

    # Valid under generation 1
    state1, is_stale1, _ = evaluator.evaluate_freshness(snap1, current_generation=prod_wsp.get_desktop_generation())
    assert state1 == FreshnessState.FRESH
    assert is_stale1 is False

    # Dock workspace -> generation incremented
    await prod_wsp.register_appbar("right", 480)
    gen2 = prod_wsp.get_desktop_generation()
    assert gen2 > gen1

    # Snapshot 1 is now STALE
    state2, is_stale2, reason2 = evaluator.evaluate_freshness(snap1, current_generation=prod_wsp.get_desktop_generation())
    assert state2 == FreshnessState.STALE
    assert is_stale2 is True
    assert "GENERATION_MISMATCH" in str(reason2)

    # Pointer coordinate evaluated under gen1 is rejected
    val_res = prod_wsp.validate_coordinate(500, 500, expected_generation=gen1)
    assert val_res.is_valid is False
    assert val_res.status == CoordinateValidationStatus.STALE_COORDINATE_CONTEXT

    # Pointer coordinate under active gen2 is accepted
    val_res2 = prod_wsp.validate_coordinate(500, 500, expected_generation=gen2)
    assert val_res2.is_valid is True

    await prod_wsp.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_human_takeover_suppresses_workspace_recovery(event_bus: EventBus):
    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    registry.register(CapabilityType.POINTER, MockPointerAdapter())
    registry.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    registry.register(CapabilityType.HUMAN_TAKEOVER, MockHumanTakeoverAdapter())

    prod_wsp = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        appbar_driver=FakeAppBarDriver(),
    )
    registry.register(CapabilityType.WORKSPACE, prod_wsp)
    registry.register(CapabilityType.SAFETY, MockSafetyCoordinator())

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    await orch.initialize()

    # Before takeover
    assert prod_wsp.is_takeover_active_fn() is False

    # Trigger human takeover
    await orch.handle_human_takeover(reason="User physically moved mouse")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    # Watchdog takeover check returns True
    assert prod_wsp.is_takeover_active_fn() is True

    # Release takeover
    await orch.release_takeover()
    assert orch.system_state == SystemState.IDLE
    assert prod_wsp.is_takeover_active_fn() is False

    await orch.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_workspace_dock_and_undock_actions(event_bus: EventBus):
    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    registry.register(CapabilityType.POINTER, MockPointerAdapter())
    registry.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    registry.register(CapabilityType.HUMAN_TAKEOVER, MockHumanTakeoverAdapter())

    driver = FakeAppBarDriver()
    prod_wsp = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        appbar_driver=driver,
    )
    registry.register(CapabilityType.WORKSPACE, prod_wsp)
    registry.register(CapabilityType.SAFETY, MockSafetyCoordinator())

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    await orch.initialize()

    gen_init = prod_wsp.get_desktop_generation()

    from orbit.runtime.cancellation import CancellationSource
    cancel_src = CancellationSource()

    # 1. Dock action
    dock_action = Action(
        action_id="act_dock",
        task_id="task_workspace",
        action_type="workspace_dock",
        tier=ActionTier.TIER_1_SAFE,
        parameters={"edge": "right", "size": 400},
    )
    await orch._execute_action("sess_01", dock_action, cancel_src.token)
    assert prod_wsp.state_manager.is_docked is True
    assert prod_wsp.get_desktop_generation() > gen_init
    gen_docked = prod_wsp.get_desktop_generation()

    # 2. Undock action
    undock_action = Action(
        action_id="act_undock",
        task_id="task_workspace",
        action_type="workspace_undock",
        tier=ActionTier.TIER_1_SAFE,
        parameters={},
    )
    await orch._execute_action("sess_01", undock_action, cancel_src.token)
    assert prod_wsp.state_manager.is_docked is False
    assert prod_wsp.get_desktop_generation() > gen_docked

    await orch.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_shutdown_during_human_takeover_no_deadlock(event_bus: EventBus):
    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    registry.register(CapabilityType.POINTER, MockPointerAdapter())
    registry.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    registry.register(CapabilityType.HUMAN_TAKEOVER, MockHumanTakeoverAdapter())

    prod_wsp = ProductionWorkspaceAdapter(
        auto_start_watchdog=False,
        appbar_driver=FakeAppBarDriver(),
    )
    registry.register(CapabilityType.WORKSPACE, prod_wsp)
    registry.register(CapabilityType.SAFETY, MockSafetyCoordinator())

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    await orch.initialize()

    # Trigger human takeover
    await orch.handle_human_takeover(reason="Operator takeover")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    # Shutdown directly while in takeover
    await asyncio.wait_for(orch.shutdown(), timeout=5.0)
    assert orch.system_state == SystemState.SHUTDOWN
    assert prod_wsp.lifecycle_state == CapabilityLifecycleState.STOPPED

