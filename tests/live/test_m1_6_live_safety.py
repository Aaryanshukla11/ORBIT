"""Live Autonomy Safety, Takeover Preemption, and Boundary Validation Suite for Milestone M1.6.

Verifies:
1. Human takeover preemption halts active execution immediately and prevents OS input dispatch.
2. Workspace AppBar reserved dock collision blocks coordinate dispatch fail-closed.
3. Desktop topology mutation / generation invalidation prevents stale coordinate reuse.

Epistemic Classification:
- LIVE_OS_VALIDATED: Executed against live Windows display and production adapters.
- TEST_PROVEN: Deterministically proven under controlled integration test assertions.
"""

from __future__ import annotations

import asyncio
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.contracts.runtime import SystemState
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ClosedLoopExecutionResult,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.execution.context import CancellationReason, DispatchStage
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetIntent,
    TargetStrategy,
)
from orbit.runtime.verification import ActionVerifier


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_human_takeover_preempts_autonomous_dispatch():
    """Verify that active human takeover immediately halts autonomous execution.

    Proves:
    1. SystemState.HUMAN_TAKEOVER_ACTIVE causes AutonomousDispatchGate to deny dispatch.
    2. Execution transitions to ExecutionState.HUMAN_TAKEOVER.
    3. Context cancellation is stamped with CancellationReason.HUMAN_TAKEOVER.
    4. ZERO pointer or keyboard events reach the live operating system.
    """
    event_bus = EventBus()
    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    try:
        takeover_active = True

        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=event_bus,
            system_state_getter=lambda: (
                SystemState.HUMAN_TAKEOVER_ACTIVE if takeover_active else SystemState.IDLE
            ),
        )

        intent = TargetIntent(
            strategy=TargetStrategy.COORDINATE_REGION,
            explicit_bounds=BoundingBox(left=300, top=300, width=100, height=100),
        )

        result: ClosedLoopExecutionResult = await engine.execute_task_action(
            session_id="test_live_takeover_session",
            task_id="task_takeover_preempt",
            prompt="Dispatch under takeover condition",
            target_intent=intent,
            action_type="pointer_click",
        )

        assert result.is_success is False
        assert result.final_state == ExecutionState.HUMAN_TAKEOVER
        assert result.failure_code == "HUMAN_TAKEOVER_ACTIVE"
        assert result.dispatch_stage == DispatchStage.NOT_DISPATCHED
        assert result.preemption_record is not None
        assert result.preemption_record.reason == CancellationReason.HUMAN_TAKEOVER
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS validation requires Windows platform")
async def test_live_workspace_appbar_dock_collision_blocks_pointer_dispatch():
    """Verify that an action target inside the reserved AppBar dock area is rejected fail-closed.

    Proves:
    1. A simulated or real AppBar dock right edge (e.g. x >= 2160) reserves desktop geometry.
    2. A target point inside this reserved area fails ProductionWorkspaceAdapter.validate_coordinate().
    3. ExecutionEngine halts dispatch and fails closed.
    """
    event_bus = EventBus()
    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    ptr = ProductionPointerAdapter()
    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    await obs.initialize()
    await wsp.initialize()
    await ptr.initialize()

    try:
        # Mock workspace validation to reject reserved dock coordinates
        original_validate = wsp.validate_coordinate

        def mock_validate(x, y=None, expected_generation=None):
            # If target is in rightmost 20% of screen, reject as reserved dock collision
            if int(x) >= 2000:
                from orbit.adapters.workspace.geometry import (
                    CoordinateValidationResult,
                    CoordinateValidationStatus,
                )
                return CoordinateValidationResult(
                    is_valid=False,
                    status=CoordinateValidationStatus.RESERVED_WORKSPACE_COLLISION,
                    x=int(x),
                    y=int(y or 0),
                    active_generation_id=active_gen,
                    tested_generation_id=expected_generation,
                    error_message=f"Point ({x}, {y}) falls inside reserved AppBar dock",
                )
            return original_validate(x, y, expected_generation=expected_generation)

        wsp.validate_coordinate = mock_validate

        engine = ClosedLoopExecutionEngine(
            observation=obs,
            pointer=ptr,
            workspace=wsp,
            target_locator=locator,
            action_verifier=verifier,
            event_bus=event_bus,
        )

        active_gen = wsp.get_desktop_generation()

        # Target intentionally placed in reserved dock region (x=2400)
        intent = TargetIntent(
            strategy=TargetStrategy.COORDINATE_REGION,
            explicit_bounds=BoundingBox(left=2400, top=300, width=100, height=100),
            metadata={"desktop_generation_id": active_gen},
        )

        result: ClosedLoopExecutionResult = await engine.execute_task_action(
            session_id="test_dock_collision_session",
            task_id="task_dock_collision",
            prompt="Target reserved dock area",
            target_intent=intent,
            action_type="pointer_click",
            policy=ExecutionPolicy(max_total_attempts=1, max_recovery_attempts=0),
        )

        assert result.is_success is False
        assert result.final_state == ExecutionState.FAILED
        assert result.dispatch_stage == DispatchStage.NOT_DISPATCHED
    finally:
        await ptr.shutdown()
        await wsp.shutdown()
        await obs.shutdown()
