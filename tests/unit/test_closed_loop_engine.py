"""Unit tests for ORBIT M1.6 Step 3: Closed-Loop Execution Subsystem.

Covers:
- ClosedLoopStateMachine: valid transitions, illegal transitions, terminal states, history.
- RecoveryCoordinator: attempt limits, recovery limits, timeouts, backoff pacing.
- ClosedLoopExecutionEngine: bounded sense-plan-validate-act-verify cycle, preemption, replanning.
"""

import asyncio
from datetime import datetime, timezone
import pytest
import time
from typing import Optional

from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import SystemState
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ClosedLoopExecutionResult,
    ClosedLoopStateMachine,
    ExecutionPolicy,
    ExecutionState,
    RecoveryCoordinator,
    RecoveryReason,
)
from orbit.runtime.state_machine import StateTransitionError
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetIntent,
    TargetStrategy,
)
from orbit.runtime.verification import (
    ActionVerifier,
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
    VerificationStrategy,
)


# ============================================================================
# Helpers & Fixtures
# ============================================================================

def _make_snapshot(
    snapshot_id: str,
    generation_id: int = 0,
    elements=None,
    windows=None,
    is_stale: bool = False,
    invalidation_reason: Optional[str] = None,
) -> ObservationSnapshot:
    return ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=generation_id,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        windows=windows or [],
        detected_elements=elements or [],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
        is_stale=is_stale,
        invalidation_reason=invalidation_reason,
    )


@pytest.fixture
def execution_env():
    bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    tkv = MockHumanTakeoverAdapter()
    wsp = MockWorkspaceAdapter()
    sft = MockSafetyCoordinator()

    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()

    engine = ClosedLoopExecutionEngine(
        observation=obs,
        pointer=ptr,
        keyboard=kbd,
        takeover=tkv,
        workspace=wsp,
        safety=sft,
        target_locator=locator,
        action_verifier=verifier,
        event_bus=bus,
        clock=SystemClock(),
    )
    return engine, obs, ptr, wsp, tkv, bus


# ============================================================================
# 1. State Machine Tests
# ============================================================================

def test_state_machine_valid_happy_path_transitions():
    """Verify standard happy-path progression through execution lifecycle."""
    sm = ClosedLoopStateMachine()
    assert sm.current_state == ExecutionState.IDLE
    assert not sm.is_terminal

    sm.transition_to(ExecutionState.OBSERVING, "Pre-action observe")
    assert sm.current_state == ExecutionState.OBSERVING

    sm.transition_to(ExecutionState.RESOLVING_TARGET, "Locating element")
    assert sm.current_state == ExecutionState.RESOLVING_TARGET

    sm.transition_to(ExecutionState.VALIDATING, "Checking coordinates")
    assert sm.current_state == ExecutionState.VALIDATING

    sm.transition_to(ExecutionState.DISPATCHING, "Clicking target")
    assert sm.current_state == ExecutionState.DISPATCHING

    sm.transition_to(ExecutionState.RE_OBSERVING, "Post-action observe")
    assert sm.current_state == ExecutionState.RE_OBSERVING

    sm.transition_to(ExecutionState.VERIFYING, "Verifying outcome")
    assert sm.current_state == ExecutionState.VERIFYING

    sm.transition_to(ExecutionState.SUCCEEDED, "Target confirmed")
    assert sm.current_state == ExecutionState.SUCCEEDED
    assert sm.is_terminal

    # Transition history audit trail
    assert len(sm.transition_history) == 7
    from_states = [h[0] for h in sm.transition_history]
    to_states = [h[1] for h in sm.transition_history]
    assert from_states == [
        ExecutionState.IDLE.value,
        ExecutionState.OBSERVING.value,
        ExecutionState.RESOLVING_TARGET.value,
        ExecutionState.VALIDATING.value,
        ExecutionState.DISPATCHING.value,
        ExecutionState.RE_OBSERVING.value,
        ExecutionState.VERIFYING.value,
    ]
    assert to_states[-1] == ExecutionState.SUCCEEDED.value


def test_state_machine_rejects_illegal_transitions():
    """Verify illegal transitions are strictly rejected by the state machine."""
    sm = ClosedLoopStateMachine()
    # Cannot jump from IDLE to DISPATCHING directly
    with pytest.raises(StateTransitionError):
        sm.transition_to(ExecutionState.DISPATCHING)

    sm.transition_to(ExecutionState.OBSERVING)
    # Cannot jump from OBSERVING to SUCCEEDED
    with pytest.raises(StateTransitionError):
        sm.transition_to(ExecutionState.SUCCEEDED)


def test_state_machine_terminal_states_cannot_transition():
    """Verify terminal states are final and forbid further state changes."""
    for terminal in [
        ExecutionState.SUCCEEDED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
        ExecutionState.HUMAN_TAKEOVER,
    ]:
        sm = ClosedLoopStateMachine(initial_state=terminal)
        assert sm.is_terminal
        with pytest.raises(StateTransitionError):
            sm.transition_to(ExecutionState.OBSERVING)


def test_state_machine_idempotent_self_transition():
    """Verify transitioning to current state is a safe no-op."""
    sm = ClosedLoopStateMachine(initial_state=ExecutionState.OBSERVING)
    res = sm.transition_to(ExecutionState.OBSERVING)
    assert res == ExecutionState.OBSERVING
    assert len(sm.transition_history) == 0


# ============================================================================
# 2. Recovery Coordinator Tests
# ============================================================================

def test_recovery_coordinator_enforces_attempt_budget():
    """Verify total attempt cap is enforced without infinite loops."""
    policy = ExecutionPolicy(max_total_attempts=2, max_recovery_attempts=5)
    rc = RecoveryCoordinator(policy=policy)

    assert rc.can_recover(RecoveryReason.VERIFICATION_FAILED)
    rc.record_attempt()
    assert rc.total_attempts == 1

    assert rc.can_recover(RecoveryReason.VERIFICATION_FAILED)
    rc.record_attempt()
    assert rc.total_attempts == 2

    # Attempt limit reached (2 >= 2)
    assert not rc.can_recover(RecoveryReason.VERIFICATION_FAILED)
    assert "Max total action dispatch attempts exhausted" in rc.get_exhaustion_reason(RecoveryReason.VERIFICATION_FAILED)


def test_recovery_coordinator_enforces_recovery_budget():
    """Verify max recovery cycles cap is enforced."""
    policy = ExecutionPolicy(max_total_attempts=10, max_recovery_attempts=2)
    rc = RecoveryCoordinator(policy=policy)

    assert rc.can_recover(RecoveryReason.TARGET_NOT_FOUND)
    rc.record_recovery(RecoveryReason.TARGET_NOT_FOUND)
    assert rc.recovery_attempts == 1

    assert rc.can_recover(RecoveryReason.TARGET_NOT_FOUND)
    rc.record_recovery(RecoveryReason.TARGET_NOT_FOUND)
    assert rc.recovery_attempts == 2

    # Recovery limit reached (2 >= 2)
    assert not rc.can_recover(RecoveryReason.TARGET_NOT_FOUND)
    assert "Max recovery cycles exhausted" in rc.get_exhaustion_reason(RecoveryReason.TARGET_NOT_FOUND)


def test_recovery_coordinator_enforces_timeout():
    """Verify timeout expiration immediately denies recovery."""
    policy = ExecutionPolicy(execution_timeout_seconds=0.01)
    rc = RecoveryCoordinator(policy=policy, start_time=time.perf_counter() - 1.0)
    assert rc.is_timed_out
    assert not rc.can_recover(RecoveryReason.VERIFICATION_FAILED)
    assert "timeout exceeded" in rc.get_exhaustion_reason(RecoveryReason.VERIFICATION_FAILED)


def test_recovery_coordinator_backoff_scaling():
    """Verify exponential backoff calculation remains safely bounded."""
    policy = ExecutionPolicy(retry_backoff_base_ms=10.0)
    rc = RecoveryCoordinator(policy=policy)

    # Before any recovery: 10ms
    assert rc.compute_backoff_delay() == 0.01
    rc.record_recovery(RecoveryReason.VERIFICATION_FAILED)
    assert rc.compute_backoff_delay() == 0.01
    rc.record_recovery(RecoveryReason.VERIFICATION_FAILED)
    assert rc.compute_backoff_delay() == 0.02
    rc.record_recovery(RecoveryReason.VERIFICATION_FAILED)
    assert rc.compute_backoff_delay() == 0.04


# ============================================================================
# 3. Closed-Loop Engine End-to-End Tests
# ============================================================================

@pytest.mark.asyncio
async def test_closed_loop_happy_path(execution_env):
    """(1) Happy path: Observe -> Resolve -> Validate -> Act -> Re-Observe -> Verify -> Success."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Setup element and snapshots
    el_pre = ObservedElement(
        element_id="btn_save",
        source="MSAA",
        name="Save",
        role="Button",
        bounds=BoundingBox(left=500, top=300, width=100, height=40),
        is_focused=False,
    )
    el_post = ObservedElement(
        element_id="btn_save",
        source="MSAA",
        name="Save",
        role="Button",
        bounds=BoundingBox(left=500, top=300, width=100, height=40),
        is_focused=True,
    )

    snap_pre = _make_snapshot("snap_1", generation_id=wsp.desktop_generation_id, elements=[el_pre])
    snap_post = _make_snapshot("snap_2", generation_id=wsp.desktop_generation_id, elements=[el_post])

    obs.queue_mock_snapshot(snap_pre)
    obs.queue_mock_snapshot(snap_post)

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Save")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_save",
        expected_property="is_focused",
        expected_value=True,
    )

    result = await engine.execute_task_action(
        session_id="sess_01",
        task_id="task_01",
        prompt="Click save button",
        target_intent=intent,
        expected_outcome=outcome,
    )

    assert result.is_success
    assert result.final_state == ExecutionState.SUCCEEDED
    assert result.total_attempts == 1
    assert result.total_recoveries == 0
    assert result.verification_result is not None
    assert result.verification_result.outcome == VerificationOutcome.VERIFIED_SUCCESS
    assert len(ptr.click_history) == 1
    click = ptr.click_history[0]
    # Coordinates inside element interior
    assert 500 < click["x"] < 600
    assert 300 < click["y"] < 340


@pytest.mark.asyncio
async def test_closed_loop_target_not_found_fails_closed(execution_env):
    """(2) Target not found: fails closed, returns TARGET_NOT_FOUND, 0 clicks."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    snap = _make_snapshot("snap_empty", generation_id=wsp.desktop_generation_id, elements=[])
    obs.mock_snapshot = snap

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="NonExistent")
    policy = ExecutionPolicy(max_target_resolution_attempts=1, max_recovery_attempts=0)

    result = await engine.execute_task_action(
        session_id="sess_02",
        task_id="task_02",
        prompt="Click missing element",
        target_intent=intent,
        policy=policy,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.failure_code == "TARGET_NOT_FOUND"
    assert len(ptr.click_history) == 0


@pytest.mark.asyncio
async def test_closed_loop_target_ambiguous_fails_closed(execution_env):
    """(3) Target ambiguous: multiple matching elements without discriminator fail closed."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    el1 = ObservedElement(element_id="btn_1", source="MSAA", name="Submit", role="Button", bounds=BoundingBox(left=100, top=100, width=50, height=20))
    el2 = ObservedElement(element_id="btn_2", source="MSAA", name="Submit", role="Button", bounds=BoundingBox(left=200, top=100, width=50, height=20))
    snap = _make_snapshot("snap_ambig", generation_id=wsp.desktop_generation_id, elements=[el1, el2])
    obs.mock_snapshot = snap

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Submit")
    policy = ExecutionPolicy(max_target_resolution_attempts=1, max_recovery_attempts=0)

    result = await engine.execute_task_action(
        session_id="sess_03",
        task_id="task_03",
        prompt="Click ambiguous submit",
        target_intent=intent,
        policy=policy,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.failure_code == "TARGET_AMBIGUOUS"
    assert len(ptr.click_history) == 0


@pytest.mark.asyncio
async def test_closed_loop_verification_retry_succeeds_on_second_attempt(execution_env):
    """(4) First verification fails, fresh re-observation captured, target re-resolved, second attempt succeeds."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Sequence of 4 snapshots:
    # 1. Attempt 1 Pre: is_focused = False
    # 2. Attempt 1 Post: is_focused = False (Verification fails!)
    # 3. Attempt 2 Pre: is_focused = False (Re-observation!)
    # 4. Attempt 2 Post: is_focused = True (Verification passes!)
    el_pre_1 = ObservedElement(element_id="btn_retry", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=400, top=200, width=80, height=30), is_focused=False)
    el_post_1 = ObservedElement(element_id="btn_retry", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=400, top=200, width=80, height=30), is_focused=False)
    el_pre_2 = ObservedElement(element_id="btn_retry", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=400, top=200, width=80, height=30), is_focused=False)
    el_post_2 = ObservedElement(element_id="btn_retry", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=400, top=200, width=80, height=30), is_focused=True)

    obs.queue_mock_snapshot(_make_snapshot("s1", wsp.desktop_generation_id, elements=[el_pre_1]))
    obs.queue_mock_snapshot(_make_snapshot("s2", wsp.desktop_generation_id, elements=[el_post_1]))
    obs.queue_mock_snapshot(_make_snapshot("s3", wsp.desktop_generation_id, elements=[el_pre_2]))
    obs.queue_mock_snapshot(_make_snapshot("s4", wsp.desktop_generation_id, elements=[el_post_2]))

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="OK")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_retry",
        expected_property="is_focused",
        expected_value=True,
    )
    policy = ExecutionPolicy(max_total_attempts=3, max_verification_retries=2, retry_backoff_base_ms=5.0)

    result = await engine.execute_task_action(
        session_id="sess_04",
        task_id="task_04",
        prompt="Click OK with retry",
        target_intent=intent,
        expected_outcome=outcome,
        policy=policy,
    )

    assert result.is_success
    assert result.final_state == ExecutionState.SUCCEEDED
    assert result.total_attempts == 2
    assert result.total_recoveries == 1
    assert len(ptr.click_history) == 2


@pytest.mark.asyncio
async def test_closed_loop_retry_budget_exhausted(execution_env):
    """(5) Retry budget exhausted: repeated verification failure terminates in FAILED."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Snapshot always shows is_focused=False
    el = ObservedElement(element_id="btn_stubborn", source="MSAA", name="Stubborn", role="Button", bounds=BoundingBox(left=300, top=300, width=80, height=30), is_focused=False)
    obs.mock_snapshot = _make_snapshot("s_stubborn", wsp.desktop_generation_id, elements=[el])

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Stubborn")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_stubborn",
        expected_property="is_focused",
        expected_value=True,
    )
    policy = ExecutionPolicy(max_total_attempts=2, max_verification_retries=1, max_recovery_attempts=1, retry_backoff_base_ms=5.0)

    result = await engine.execute_task_action(
        session_id="sess_05",
        task_id="task_05",
        prompt="Click stubborn button",
        target_intent=intent,
        expected_outcome=outcome,
        policy=policy,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.total_attempts == 2
    assert result.total_recoveries == 1
    assert "VERIFIED_FAILURE" in result.failure_code


@pytest.mark.asyncio
async def test_closed_loop_execution_timeout(execution_env):
    """(7) Overall execution timeout stops the engine cleanly."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    el = ObservedElement(element_id="btn_t", source="MSAA", name="Test", role="Button", bounds=BoundingBox(left=100, top=100, width=50, height=20))
    obs.mock_snapshot = _make_snapshot("snap_t", wsp.desktop_generation_id, elements=[el])

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Test")
    policy = ExecutionPolicy(execution_timeout_seconds=1.0)

    result = await engine.execute_task_action(
        session_id="sess_07",
        task_id="task_07",
        prompt="Timeout task",
        target_intent=intent,
        policy=policy,
        start_time=time.perf_counter() - 20.0,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.failure_code == "EXECUTION_TIMEOUT"


@pytest.mark.asyncio
async def test_closed_loop_stale_observation_before_dispatch(execution_env):
    """(8) Stale observation snapshot fails closed without pointer dispatch."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    el = ObservedElement(element_id="btn_stale", source="MSAA", name="StaleBtn", role="Button", bounds=BoundingBox(left=100, top=100, width=50, height=20))
    obs.mock_snapshot = _make_snapshot("snap_stale", wsp.desktop_generation_id, elements=[el], is_stale=True, invalidation_reason="TTL expired")

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="StaleBtn")
    policy = ExecutionPolicy(max_recovery_attempts=0)

    result = await engine.execute_task_action(
        session_id="sess_08",
        task_id="task_08",
        prompt="Stale task",
        target_intent=intent,
        policy=policy,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.failure_code == "TARGET_STALE_OBSERVATION"
    assert len(ptr.click_history) == 0


@pytest.mark.asyncio
async def test_closed_loop_workspace_dock_collision_prevents_pointer_dispatch(execution_env):
    """(11/12) Workspace coordinate validation blocks dispatch into reserved dock area."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Register right appbar of 400px (reserved: 1520..1920)
    await wsp.register_appbar(edge="right", size=400)

    # Place target button inside dock reservation (x=1600)
    el_docked = ObservedElement(
        element_id="btn_docked",
        source="MSAA",
        name="DockedButton",
        role="Button",
        bounds=BoundingBox(left=1600, top=500, width=100, height=40),
    )
    obs.mock_snapshot = _make_snapshot("snap_dock", wsp.desktop_generation_id, elements=[el_docked])

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="DockedButton")
    policy = ExecutionPolicy(max_recovery_attempts=0)

    result = await engine.execute_task_action(
        session_id="sess_12",
        task_id="task_12",
        prompt="Click docked button",
        target_intent=intent,
        policy=policy,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.failure_code == "RESERVED_WORKSPACE_COLLISION"
    assert len(ptr.click_history) == 0


@pytest.mark.asyncio
async def test_closed_loop_human_takeover_before_action(execution_env):
    """(13) Human takeover active before first action halts execution immediately."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    el = ObservedElement(element_id="btn_tkv", source="MSAA", name="TakeoverBtn", role="Button", bounds=BoundingBox(left=200, top=200, width=60, height=30))
    obs.mock_snapshot = _make_snapshot("snap_tkv", wsp.desktop_generation_id, elements=[el])

    # Trigger human takeover
    tkv.trigger_takeover()

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="TakeoverBtn")

    result = await engine.execute_task_action(
        session_id="sess_13",
        task_id="task_13",
        prompt="Takeover preempt task",
        target_intent=intent,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.HUMAN_TAKEOVER
    assert result.failure_code == "HUMAN_TAKEOVER_ACTIVE"
    assert len(ptr.click_history) == 0


@pytest.mark.asyncio
async def test_closed_loop_cancellation_before_dispatch(execution_env):
    """(15) Cancellation before dispatch halts closed loop cleanly."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    cancel_source = CancellationSource()
    cancel_source.cancel("Operator aborted task")

    el = ObservedElement(element_id="btn_c", source="MSAA", name="CancelBtn", role="Button", bounds=BoundingBox(left=200, top=200, width=60, height=30))
    obs.mock_snapshot = _make_snapshot("snap_c", wsp.desktop_generation_id, elements=[el])

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="CancelBtn")

    result = await engine.execute_task_action(
        session_id="sess_15",
        task_id="task_15",
        prompt="Cancel task",
        target_intent=intent,
        cancel_token=cancel_source.token,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.CANCELLED
    assert result.failure_code == "TASK_CANCELLED"
    assert len(ptr.click_history) == 0


@pytest.mark.asyncio
async def test_closed_loop_replanning_uses_fresh_coordinates(execution_env):
    """(18) Replanning after failed verification re-resolves moving element to fresh coordinates."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Target starts at (200, 200), fails verification, moves to (600, 600)
    el_pos_1 = ObservedElement(element_id="btn_move", source="MSAA", name="MoveBtn", role="Button", bounds=BoundingBox(left=200, top=200, width=80, height=30), is_focused=False)
    el_pos_1_unfocused = ObservedElement(element_id="btn_move", source="MSAA", name="MoveBtn", role="Button", bounds=BoundingBox(left=200, top=200, width=80, height=30), is_focused=False)
    el_pos_2 = ObservedElement(element_id="btn_move", source="MSAA", name="MoveBtn", role="Button", bounds=BoundingBox(left=600, top=600, width=80, height=30), is_focused=False)
    el_pos_2_focused = ObservedElement(element_id="btn_move", source="MSAA", name="MoveBtn", role="Button", bounds=BoundingBox(left=600, top=600, width=80, height=30), is_focused=True)

    obs.queue_mock_snapshot(_make_snapshot("s1", wsp.desktop_generation_id, elements=[el_pos_1]))
    obs.queue_mock_snapshot(_make_snapshot("s2", wsp.desktop_generation_id, elements=[el_pos_1_unfocused]))
    obs.queue_mock_snapshot(_make_snapshot("s3", wsp.desktop_generation_id, elements=[el_pos_2]))
    obs.queue_mock_snapshot(_make_snapshot("s4", wsp.desktop_generation_id, elements=[el_pos_2_focused]))

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="MoveBtn")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_move",
        expected_property="is_focused",
        expected_value=True,
    )
    policy = ExecutionPolicy(max_total_attempts=3, max_verification_retries=2, retry_backoff_base_ms=5.0)

    result = await engine.execute_task_action(
        session_id="sess_18",
        task_id="task_18",
        prompt="Click moving button",
        target_intent=intent,
        expected_outcome=outcome,
        policy=policy,
    )

    assert result.is_success
    assert len(ptr.click_history) == 2
    first_click = ptr.click_history[0]
    second_click = ptr.click_history[1]

    # First attempt clicked at original position (200..280, 200..230)
    assert 200 <= first_click["x"] <= 280
    assert 200 <= first_click["y"] <= 230

    # Second attempt clicked at FRESH position (600..680, 600..630)
    assert 600 <= second_click["x"] <= 680
    assert 600 <= second_click["y"] <= 630
