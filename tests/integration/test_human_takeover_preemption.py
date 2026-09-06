"""Integration tests for cross-capability human takeover preemption in ORBIT."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import Action, ActionStage, Step, SystemState, Task, TaskStatus
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.execution.context import (
    CancellationReason,
    DispatchStage,
    ExecutionContext,
)
from orbit.runtime.execution.engine import ClosedLoopExecutionEngine
from orbit.runtime.execution.models import ExecutionPolicy, ExecutionState
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.targeting import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetIntent,
    TargetResolutionResult,
    TargetResolutionStatus,
)
from orbit.runtime.cancellation import CancellationSource, CancellationToken
from orbit.runtime.verification import (
    ActionVerificationResult,
    ObservationEvidenceSummary,
    VerificationOutcome,
    VerificationStrategy,
)


def make_verification_result(outcome: VerificationOutcome, failure_reason: str = "Verification failed") -> ActionVerificationResult:
    return ActionVerificationResult(
        outcome=outcome,
        strategy_used=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        confidence=0.9,
        pre_generation_id=1,
        post_generation_id=1,
        pre_evidence=ObservationEvidenceSummary(
            snapshot_id="s1",
            desktop_generation_id=1,
            timestamp_ns=1000000,
            is_stale=False,
        ),
        failure_reason=failure_reason,
    )
from orbit.adapters.mocks.mock_keyboard import MockKeyboardAdapter
from orbit.adapters.mocks.mock_pointer import MockPointerAdapter
from orbit.adapters.mocks.mock_safety import MockSafetyCoordinator
from orbit.adapters.mocks.mock_takeover import MockHumanTakeoverAdapter
from orbit.adapters.mocks.mock_workspace import MockWorkspaceAdapter
from orbit.adapters.workspace.state import WorkspaceStateManager
from orbit.adapters.workspace.geometry import WorkspaceGeometryCoordinator
from orbit.adapters.workspace.types import WorkspaceState
from orbit.adapters.workspace.watchdog import (
    WatchdogNativeGateway,
    WorkspaceWatchdog,
)
from orbit.models.common import BoundingBox


def make_resolved_target(target_id: str, x: int = 100, y: int = 100, generation_id: int = 1) -> ResolvedTarget:
    bbox = TargetBoundingBox(left=x, top=y, right=x + 50, bottom=y + 30)
    safe_pt = SafeActionPoint(x=x + 25, y=y + 15, bounding_box=bbox, desktop_generation_id=generation_id)
    evidence = TargetEvidence(source="UIA", identifier=target_id, name=target_id, confidence=0.95)
    return ResolvedTarget(
        target_id=target_id,
        bounding_box=bbox,
        safe_point=safe_pt,
        confidence=0.95,
        evidence=evidence,
        observation_id="snap_1",
        desktop_generation_id=generation_id,
    )


class FakeWatchdogNativeGateway(WatchdogNativeGateway):
    def __init__(self, window_exists: bool = False) -> None:
        super().__init__()
        self._window_exists = window_exists

    def is_window(self, hwnd: int) -> bool:
        return self._window_exists

    def get_window_rect(self, hwnd: int):
        return BoundingBox(left=1440, top=0, width=480, height=1080)

    def is_window_visible(self, hwnd: int) -> bool:
        return self._window_exists


class FakeWindowHolder:
    def __init__(self) -> None:
        self.hwnd = 12345
        self.rect = BoundingBox(left=1440, top=0, width=480, height=1080)
        self.positions_set: list[BoundingBox] = []

    def set_position(self, rect: BoundingBox) -> None:
        self.rect = rect
        self.positions_set.append(rect)


class FakeAppBarDriver:
    def __init__(self) -> None:
        self.window = FakeWindowHolder()


@pytest.fixture
def event_bus():
    return EventBus()


# Scenario A: Takeover Before Dispatch
@pytest.mark.asyncio
async def test_scenario_a_takeover_before_dispatch(event_bus):
    """Observe -> Resolve -> Takeover activates -> ZERO pointer events."""
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    tkv = MockHumanTakeoverAdapter()
    sft = MockSafetyCoordinator()

    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    target = make_resolved_target("btn_ok", 100, 100, generation_id=1)
    mock_locator.locate_target = MagicMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=target))

    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        pointer=ptr,
        keyboard=kbd,
        takeover=tkv,
        safety=sft,
        target_locator=mock_locator,
    )

    # Takeover triggers before dispatch
    tkv.trigger_takeover()

    intent = TargetIntent(intent_id="i_ok", label="OK")
    res = await engine.execute_task_action(
        session_id="s_a",
        task_id="t_a",
        prompt="Click OK",
        target_intent=intent,
        action_type="pointer_click",
    )

    assert res.final_state == ExecutionState.HUMAN_TAKEOVER
    assert res.dispatch_stage == DispatchStage.NOT_DISPATCHED
    # Safety invariant: ZERO pointer events
    assert len(ptr.click_history) == 0
    assert len(ptr.move_history) <= 1
    # Safety coordinator emergency stop invoked
    assert sft.stop_count >= 1


# Scenario B: Takeover Between Resolution and Action
@pytest.mark.asyncio
async def test_scenario_b_takeover_between_resolution_and_action(event_bus):
    """Target resolved -> Takeover activates -> Coordinates invalidated -> ZERO input events."""
    ptr = MockPointerAdapter()
    tkv = MockHumanTakeoverAdapter()
    sft = MockSafetyCoordinator()

    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    target = make_resolved_target("btn_cancel", 200, 200, generation_id=1)

    # Trigger takeover inside target locator
    def locate_and_takeover(snapshot, intent):
        tkv.trigger_takeover()
        return TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=target)

    mock_locator.locate_target = MagicMock(side_effect=locate_and_takeover)

    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        pointer=ptr,
        takeover=tkv,
        safety=sft,
        target_locator=mock_locator,
    )

    intent = TargetIntent(intent_id="i_b", label="Cancel")
    res = await engine.execute_task_action(
        session_id="s_b",
        task_id="t_b",
        prompt="Click Cancel",
        target_intent=intent,
        action_type="pointer_click",
    )

    assert res.final_state == ExecutionState.HUMAN_TAKEOVER
    assert res.dispatch_stage == DispatchStage.NOT_DISPATCHED
    # ZERO clicks
    assert len(ptr.click_history) == 0


# Scenario C: Takeover After First Action in Multi-Step Workflow
@pytest.mark.asyncio
async def test_scenario_c_takeover_after_first_action_in_orchestrator(event_bus):
    """Action 1 dispatched -> Takeover activates -> Action 2 must never dispatch."""
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    tkv = MockHumanTakeoverAdapter()
    wsp = MockWorkspaceAdapter()
    sft = MockSafetyCoordinator()

    orch = OrbitOrchestrator(
        event_bus=event_bus,
        pointer=ptr,
        keyboard=kbd,
        takeover=tkv,
        workspace=wsp,
        safety=sft,
    )
    await orch.initialize()

    # Step 1: Pointer Click
    step1 = Step(
        step_id="step_1",
        step_index=0,
        description="First click",
        actions=[
            Action(
                task_id="task_c",
                action_id="act_1",
                action_type="pointer_click",
                parameters={"x": 50, "y": 50, "desktop_generation_id": 0},
            )
        ],
    )
    # Step 2: Keyboard Type
    step2 = Step(
        step_id="step_2",
        step_index=1,
        description="Second text input",
        actions=[
            Action(
                task_id="task_c",
                action_id="act_2",
                action_type="type_text",
                parameters={"text": "should_never_type"},
            )
        ],
    )

    token = CancellationToken(CancellationSource())
    # Execute step 1
    await orch._execute_action("sess_c", step1.actions[0], cancel_token=token)
    assert len(ptr.click_history) == 1

    # Human Takeover activates before Step 2
    tkv.trigger_takeover()
    await orch.handle_human_takeover("Physical mouse moved")

    # Step 2 execution attempt must fail-closed
    with pytest.raises(RuntimeError) as exc_info:
        await orch._execute_action("sess_c", step2.actions[0], cancel_token=token)

    assert "Human takeover is currently active" in str(exc_info.value)
    # ZERO keyboard inputs
    assert len(kbd.typed_history) == 0

    await orch.shutdown()


# Scenario D: Takeover During Retry Backoff
@pytest.mark.asyncio
async def test_scenario_d_takeover_during_retry_backoff(event_bus):
    """Attempt 1 fails verification -> Retry pending -> Takeover triggers -> Retry blocked."""
    ptr = MockPointerAdapter()
    tkv = MockHumanTakeoverAdapter()
    sft = MockSafetyCoordinator()

    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    target = make_resolved_target("btn_retry", 100, 100, generation_id=1)
    mock_locator.locate_target = MagicMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=target))

    # First attempt fails verification
    mock_verifier = MagicMock()
    mock_verifier.verify = MagicMock(return_value=make_verification_result(
        outcome=VerificationOutcome.VERIFIED_FAILURE,
        failure_reason="Checkbox state did not change",
    ))

    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        pointer=ptr,
        takeover=tkv,
        safety=sft,
        target_locator=mock_locator,
        action_verifier=mock_verifier,
    )

    # Trigger takeover shortly after attempt 1 during recovery delay
    async def takeover_after_delay():
        await asyncio.sleep(0.02)
        tkv.trigger_takeover()

    asyncio.create_task(takeover_after_delay())

    policy = ExecutionPolicy(max_total_attempts=3, retry_backoff_base_ms=200.0)
    intent = TargetIntent(intent_id="i_retry", label="Checkbox")

    res = await engine.execute_task_action(
        session_id="s_d",
        task_id="t_d",
        prompt="Check box",
        target_intent=intent,
        policy=policy,
    )

    assert res.final_state == ExecutionState.HUMAN_TAKEOVER
    # Only the initial click occurred; the retry was blocked
    assert len(ptr.click_history) == 1
    assert res.total_attempts == 1


# Scenario E: Takeover During Replan
@pytest.mark.asyncio
async def test_scenario_e_takeover_during_replan(event_bus):
    """Generation change triggers replan -> Takeover triggers -> Replan blocked."""
    ptr = MockPointerAdapter()
    tkv = MockHumanTakeoverAdapter()
    sft = MockSafetyCoordinator()

    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    target = make_resolved_target("btn_replan", 100, 100, generation_id=1)
    mock_locator.locate_target = MagicMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=target))

    # Workspace validation fails generation parity triggering replan recovery
    mock_wsp = MagicMock()
    validation_fail = MagicMock()
    validation_fail.is_valid = False
    validation_fail.status = "GENERATION_MISMATCH"
    validation_fail.error_message = "Active desktop generation 2 != expected generation 1"
    mock_wsp.validate_coordinate = MagicMock(return_value=validation_fail)

    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        pointer=ptr,
        takeover=tkv,
        workspace=mock_wsp,
        safety=sft,
        target_locator=mock_locator,
    )

    # Trigger takeover during replan backoff
    async def takeover_during_replan():
        await asyncio.sleep(0.02)
        tkv.trigger_takeover()

    asyncio.create_task(takeover_during_replan())

    policy = ExecutionPolicy(max_recovery_attempts=2, retry_backoff_base_ms=200.0)
    intent = TargetIntent(intent_id="i_replan", label="ReplanButton")

    res = await engine.execute_task_action(
        session_id="s_e",
        task_id="t_e",
        prompt="Click ReplanButton",
        target_intent=intent,
        policy=policy,
    )

    assert res.final_state == ExecutionState.HUMAN_TAKEOVER
    assert res.dispatch_stage == DispatchStage.NOT_DISPATCHED
    # ZERO clicks dispatched
    assert len(ptr.click_history) == 0


# Scenario F: Repeated Takeover Signals
@pytest.mark.asyncio
async def test_scenario_f_repeated_takeover_signals(event_bus):
    """Repeated takeover signals are safe no-ops and preserve state."""
    tkv = MockHumanTakeoverAdapter()
    orch = OrbitOrchestrator(event_bus=event_bus, takeover=tkv)
    await orch.initialize()

    await orch.handle_human_takeover("Signal 1")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    # Second signal must be idempotent and not raise
    await orch.handle_human_takeover("Signal 2")
    assert orch.system_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    await orch.shutdown()


# Scenario G: Shutdown and Takeover Race
@pytest.mark.asyncio
async def test_scenario_g_shutdown_and_takeover_race(event_bus):
    """Runtime shutdown and takeover race cleanly with no orphan tasks."""
    ptr = MockPointerAdapter()
    tkv = MockHumanTakeoverAdapter()
    sft = MockSafetyCoordinator()

    orch = OrbitOrchestrator(
        event_bus=event_bus,
        pointer=ptr,
        takeover=tkv,
        safety=sft,
    )
    await orch.initialize()

    # Race shutdown and takeover concurrently
    t1 = asyncio.create_task(orch.handle_human_takeover("Race takeover"))
    t2 = asyncio.create_task(orch.shutdown())

    await asyncio.gather(t1, t2, return_exceptions=True)

    # State must be cleanly terminal (either HUMAN_TAKEOVER_ACTIVE or SHUTDOWN)
    assert orch.system_state in {SystemState.HUMAN_TAKEOVER_ACTIVE, SystemState.SHUTDOWN}
    assert len(ptr.click_history) == 0


# Workspace Watchdog Suppression Verification
@pytest.mark.asyncio
async def test_workspace_watchdog_suppressed_during_takeover():
    """Verify that disruptive workspace recovery remains suppressed during human takeover."""
    is_takeover = True

    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)

    gc = WorkspaceGeometryCoordinator(state_manager=sm)
    driver = FakeAppBarDriver()
    gw = FakeWatchdogNativeGateway(window_exists=False)

    wd = WorkspaceWatchdog(
        state_manager=sm,
        geometry_coordinator=gc,
        appbar_driver=driver,
        gateway=gw,
        is_takeover_active_fn=lambda: is_takeover,
    )

    probe = wd.probe_health()
    rec = await wd.attempt_recovery(probe)
    assert rec is False
    assert len(driver.window.positions_set) == 0
