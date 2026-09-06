"""Integration tests for ORBIT M1.6 Step 3 Closed-Loop Execution Engine.

Validates the 6 mandatory scenarios:
- Scenario A — Immediate Success
- Scenario B — Verification Failure Then Retry Success
- Scenario C — Replan After Generation Change
- Scenario D — Retry Exhaustion
- Scenario E — Human Takeover Preemption
- Scenario F — Observation Failure
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
    RecoveryReason,
)
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


@pytest.mark.asyncio
async def test_scenario_a_immediate_success(execution_env):
    """Scenario A: Observe -> resolve target -> validate coordinate -> act -> verify -> SUCCEEDED."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    el_pre = ObservedElement(
        element_id="btn_submit",
        source="MSAA",
        name="Submit",
        role="Button",
        bounds=BoundingBox(left=400, top=300, width=120, height=35),
        is_focused=False,
    )
    el_post = ObservedElement(
        element_id="btn_submit",
        source="MSAA",
        name="Submit",
        role="Button",
        bounds=BoundingBox(left=400, top=300, width=120, height=35),
        is_focused=True,
    )

    obs.queue_mock_snapshot(_make_snapshot("s1", wsp.desktop_generation_id, elements=[el_pre]))
    obs.queue_mock_snapshot(_make_snapshot("s2", wsp.desktop_generation_id, elements=[el_post]))

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Submit")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_submit",
        expected_property="is_focused",
        expected_value=True,
    )

    result = await engine.execute_task_action(
        session_id="sess_scen_a",
        task_id="task_scen_a",
        prompt="Click submit button",
        target_intent=intent,
        expected_outcome=outcome,
    )

    assert result.is_success
    assert result.final_state == ExecutionState.SUCCEEDED
    assert result.total_attempts == 1
    assert result.total_recoveries == 0
    assert len(ptr.click_history) == 1
    assert 400 < ptr.click_history[0]["x"] < 520
    assert 300 < ptr.click_history[0]["y"] < 335


@pytest.mark.asyncio
async def test_scenario_b_verification_failure_then_retry_success(execution_env):
    """Scenario B: Attempt 1 NOT_VERIFIED -> retry -> attempt 2 re-resolves and succeeds -> SUCCEEDED."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Target element starts at (300, 200), moves to (500, 400) on attempt 2
    el1_pre = ObservedElement(element_id="btn_ok", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=300, top=200, width=80, height=30), is_focused=False)
    el1_post = ObservedElement(element_id="btn_ok", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=300, top=200, width=80, height=30), is_focused=False)

    el2_pre = ObservedElement(element_id="btn_ok", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=500, top=400, width=80, height=30), is_focused=False)
    el2_post = ObservedElement(element_id="btn_ok", source="MSAA", name="OK", role="Button", bounds=BoundingBox(left=500, top=400, width=80, height=30), is_focused=True)

    obs.queue_mock_snapshot(_make_snapshot("s1", wsp.desktop_generation_id, elements=[el1_pre]))
    obs.queue_mock_snapshot(_make_snapshot("s2", wsp.desktop_generation_id, elements=[el1_post]))
    obs.queue_mock_snapshot(_make_snapshot("s3", wsp.desktop_generation_id, elements=[el2_pre]))
    obs.queue_mock_snapshot(_make_snapshot("s4", wsp.desktop_generation_id, elements=[el2_post]))

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="OK")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_ok",
        expected_property="is_focused",
        expected_value=True,
    )

    result = await engine.execute_task_action(
        session_id="sess_scen_b",
        task_id="task_scen_b",
        prompt="Click OK button",
        target_intent=intent,
        expected_outcome=outcome,
    )

    assert result.is_success
    assert result.final_state == ExecutionState.SUCCEEDED
    assert result.total_attempts == 2
    assert result.total_recoveries == 1
    assert len(ptr.click_history) == 2

    # Verify attempt 2 dispatched to NEW coordinates, not old coordinates!
    click1 = ptr.click_history[0]
    click2 = ptr.click_history[1]
    assert 300 < click1["x"] < 380
    assert 200 < click1["y"] < 230
    assert 500 < click2["x"] < 580
    assert 400 < click2["y"] < 430


@pytest.mark.asyncio
async def test_scenario_c_replan_after_generation_change(execution_env):
    """Scenario C: Generation change N -> N+1 causes stale coordinate discard, bounded replan, safe dispatch."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    gen_0 = wsp.desktop_generation_id
    gen_1 = gen_0 + 1

    # Snapshot 1: Generation 0
    el_0 = ObservedElement(element_id="btn_dock", source="MSAA", name="DockBtn", role="Button", bounds=BoundingBox(left=100, top=100, width=60, height=30))
    snap_0 = _make_snapshot("s0", generation_id=gen_0, elements=[el_0])

    # Invalidate generation during validation cycle
    original_validate = wsp.validate_coordinate
    validation_calls = 0

    def _dynamic_validation(x, y, expected_generation=0):
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            # First attempt: simulate workspace generation increment during dispatch
            from orbit.adapters.workspace.geometry import CoordinateValidationResult, CoordinateValidationStatus
            return CoordinateValidationResult(
                is_valid=False,
                status=CoordinateValidationStatus.STALE_COORDINATE_CONTEXT,
                x=x,
                y=y,
                active_generation_id=gen_1,
                tested_generation_id=expected_generation,
                error_message="Desktop generation 0 is stale; current is 1",
            )
        # Second attempt: generation 1 is now valid
        wsp._desktop_generation_id = gen_1
        return original_validate(x, y, expected_generation=gen_1)

    wsp.validate_coordinate = _dynamic_validation

    # Snapshot 2: Fresh observation with generation 1
    el_1_pre = ObservedElement(element_id="btn_dock", source="MSAA", name="DockBtn", role="Button", bounds=BoundingBox(left=120, top=120, width=60, height=30), is_focused=False)
    el_1_post = ObservedElement(element_id="btn_dock", source="MSAA", name="DockBtn", role="Button", bounds=BoundingBox(left=120, top=120, width=60, height=30), is_focused=True)

    obs.queue_mock_snapshot(snap_0)
    obs.queue_mock_snapshot(_make_snapshot("s1_fresh", generation_id=gen_1, elements=[el_1_pre]))
    obs.queue_mock_snapshot(_make_snapshot("s2_post", generation_id=gen_1, elements=[el_1_post]))

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="DockBtn")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_dock",
        expected_property="is_focused",
        expected_value=True,
    )

    result = await engine.execute_task_action(
        session_id="sess_scen_c",
        task_id="task_scen_c",
        prompt="Click DockBtn",
        target_intent=intent,
        expected_outcome=outcome,
    )

    assert result.is_success
    assert result.final_state == ExecutionState.SUCCEEDED
    # Generation mismatch must have triggered a replan recovery without dispatching stale coordinate
    assert result.total_recoveries == 1
    assert result.total_attempts == 1
    assert len(ptr.click_history) == 1
    # Dispatched point must be from fresh generation 1 snapshot (120, 120), NOT stale snapshot (100, 100)
    assert 120 < ptr.click_history[0]["x"] < 180


@pytest.mark.asyncio
async def test_scenario_d_retry_exhaustion_fails_closed(execution_env):
    """Scenario D: Action fails verification repeatedly until budget exhausted -> FAILED (exact attempt count)."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    el_pre = ObservedElement(element_id="btn_fail", source="MSAA", name="Broken", role="Button", bounds=BoundingBox(left=200, top=200, width=50, height=25), is_focused=False)
    el_post = ObservedElement(element_id="btn_fail", source="MSAA", name="Broken", role="Button", bounds=BoundingBox(left=200, top=200, width=50, height=25), is_focused=False)

    # Configure mock observation to return non-verifying snapshots
    obs.mock_snapshot = _make_snapshot("s_continuous", wsp.desktop_generation_id, elements=[el_pre])

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Broken")
    outcome = ExpectedOutcome(
        outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
        strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        target_id="btn_fail",
        expected_property="is_focused",
        expected_value=True,
    )
    policy = ExecutionPolicy(max_total_attempts=2, max_verification_retries=1, max_recovery_attempts=1)

    result = await engine.execute_task_action(
        session_id="sess_scen_d",
        task_id="task_scen_d",
        prompt="Click broken button",
        target_intent=intent,
        expected_outcome=outcome,
        policy=policy,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.total_attempts == 2
    assert len(ptr.click_history) == 2
    assert "exhausted" in (result.failure_reason or "").lower()


@pytest.mark.asyncio
async def test_scenario_e_human_takeover_preempts_execution(execution_env):
    """Scenario E: Takeover activates -> execution preempts immediately -> no further dispatches -> HUMAN_TAKEOVER."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Active takeover before observe/dispatch
    tkv.trigger_takeover()

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Any")
    result = await engine.execute_task_action(
        session_id="sess_scen_e",
        task_id="task_scen_e",
        prompt="Click with takeover active",
        target_intent=intent,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.HUMAN_TAKEOVER
    assert result.failure_code == "HUMAN_TAKEOVER_ACTIVE"
    assert len(ptr.click_history) == 0
    assert result.total_attempts == 0


@pytest.mark.asyncio
async def test_scenario_f_observation_failure_handling(execution_env):
    """Scenario F: Observation unavailable -> bounded retries -> fails closed without false success."""
    engine, obs, ptr, wsp, tkv, bus = execution_env

    # Mock observation throws exception on capture
    async def _failing_obs(**kwargs):
        raise RuntimeError("GDI display capture failed")

    obs.capture_snapshot = _failing_obs

    intent = TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="Any")
    policy = ExecutionPolicy(max_recovery_attempts=1)

    result = await engine.execute_task_action(
        session_id="sess_scen_f",
        task_id="task_scen_f",
        prompt="Click with broken observation",
        target_intent=intent,
        policy=policy,
    )

    assert not result.is_success
    assert result.final_state == ExecutionState.FAILED
    assert result.failure_code == "TARGET_OBSERVATION_UNAVAILABLE"
    assert result.total_attempts == 0
    assert len(ptr.click_history) == 0
