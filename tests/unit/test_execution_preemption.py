"""Unit tests for execution preemption, cancellation authority, and closed-loop safety."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import SystemState
from orbit.runtime.execution.context import (
    CancellationReason,
    DispatchStage,
    ExecutionContext,
    PreemptionRecord,
)
from orbit.runtime.execution.engine import ClosedLoopExecutionEngine
from orbit.runtime.execution.models import (
    ClosedLoopExecutionResult,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.execution.safety_gate import (
    AutonomousDispatchGate,
    PreemptionSafetyError,
)
from orbit.runtime.execution.state_machine import ClosedLoopStateMachine, StateTransitionError
from orbit.runtime.targeting import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetIntent,
    TargetResolutionResult,
    TargetResolutionStatus,
)
from orbit.runtime.verification import (
    ActionVerificationResult,
    ExpectedOutcome,
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


# 1 & 2: Cancellation authority behavior and reason recording
def test_cancellation_authority_reason_recording():
    ctx = ExecutionContext(execution_id="auth-test")
    assert not ctx.is_cancelled
    assert ctx.cancellation_reason is None

    ctx.cancel(CancellationReason.HUMAN_TAKEOVER, "Physical mouse input detected")
    assert ctx.is_cancelled
    assert ctx.cancellation_reason == CancellationReason.HUMAN_TAKEOVER
    assert "Physical mouse input" in (ctx.cancellation_message or "")


# 3 & 10: Idempotent cancellation and repeated cancellation safety
def test_idempotent_cancellation_and_repeated_calls():
    ctx = ExecutionContext(execution_id="idemp-test")
    ctx.cancel(CancellationReason.OPERATOR_CANCEL, "First cancel")
    first_reason = ctx.cancellation_reason
    first_msg = ctx.cancellation_message

    # Repeated cancellation signals must be safe no-ops and preserve primary reason
    ctx.cancel(CancellationReason.RUNTIME_SHUTDOWN, "Second cancel")
    assert ctx.cancellation_reason == first_reason
    assert ctx.cancellation_message == first_msg
    assert ctx.is_cancelled


# 4 & 5: Takeover pre-dispatch rejection & Pointer dispatch blocked (zero pointer clicks)
@pytest.mark.asyncio
async def test_pointer_dispatch_blocked_when_takeover_active():
    mock_ptr = MagicMock()
    mock_ptr.click = AsyncMock()
    mock_ptr.move_to = AsyncMock()

    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    target = make_resolved_target("btn_1", 150, 250, generation_id=1)
    mock_locator.locate_target = MagicMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=target))

    mock_takeover = MagicMock()
    mock_takeover.is_takeover_active = AsyncMock(return_value=True)

    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        pointer=mock_ptr,
        takeover=mock_takeover,
        target_locator=mock_locator,
    )

    intent = TargetIntent(intent_id="click_submit", label="Submit")
    res = await engine.execute_task_action(
        session_id="s1",
        task_id="t1",
        prompt="Click submit",
        target_intent=intent,
        action_type="pointer_click",
    )

    # Must be terminal HUMAN_TAKEOVER
    assert res.final_state == ExecutionState.HUMAN_TAKEOVER
    assert not res.is_success
    assert res.failure_code == "HUMAN_TAKEOVER_ACTIVE"
    assert res.dispatch_stage == DispatchStage.NOT_DISPATCHED

    # CRITICAL: ZERO pointer clicks dispatched
    mock_ptr.click.assert_not_called()
    mock_ptr.move_to.assert_not_called()


# 6: Keyboard dispatch blocked when takeover active
@pytest.mark.asyncio
async def test_keyboard_dispatch_blocked_when_takeover_active():
    mock_kbd = MagicMock()
    mock_kbd.type_text = AsyncMock()
    mock_kbd.press_shortcut = AsyncMock()

    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    target = make_resolved_target("input_field", 100, 100, generation_id=1)
    mock_locator.locate_target = MagicMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=target))

    ctx = ExecutionContext(execution_id="kbd-block")
    ctx.cancel(CancellationReason.HUMAN_TAKEOVER, "Human touched keyboard")

    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        keyboard=mock_kbd,
        target_locator=mock_locator,
    )

    intent = TargetIntent(intent_id="type_here", label="Input")
    res = await engine.execute_task_action(
        session_id="s1",
        task_id="t2",
        prompt="Type hello",
        target_intent=intent,
        action_type="type_text",
        action_parameters={"text": "hello"},
        context=ctx,
    )

    assert res.final_state == ExecutionState.HUMAN_TAKEOVER
    assert res.dispatch_stage == DispatchStage.NOT_DISPATCHED
    # ZERO keyboard dispatches
    mock_kbd.type_text.assert_not_called()
    mock_kbd.press_shortcut.assert_not_called()


# 7: Retry blocked after cancellation
@pytest.mark.asyncio
async def test_retry_blocked_after_cancellation():
    mock_ptr = MagicMock()
    mock_ptr.click = AsyncMock()

    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    target = make_resolved_target("btn_retry", 200, 300, generation_id=1)
    mock_locator.locate_target = MagicMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=target))

    # ActionVerifier fails first verification
    mock_verifier = MagicMock()
    mock_verifier.verify = MagicMock(return_value=make_verification_result(
        outcome=VerificationOutcome.VERIFIED_FAILURE,
        failure_reason="Element did not respond",
    ))

    ctx = ExecutionContext(execution_id="retry-cancel")

    # Cancel during pointer click execution so retry cannot happen
    async def click_and_cancel(*args, **kwargs):
        ctx.cancel(CancellationReason.OPERATOR_CANCEL, "Stop before retry")
        return True

    mock_ptr.click = AsyncMock(side_effect=click_and_cancel)

    policy = ExecutionPolicy(max_total_attempts=3, initial_backoff_seconds=0.01)
    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        pointer=mock_ptr,
        target_locator=mock_locator,
        action_verifier=mock_verifier,
    )

    intent = TargetIntent(intent_id="i1", label="RetryTarget")
    res = await engine.execute_task_action(
        session_id="s1",
        task_id="t3",
        prompt="Try action",
        target_intent=intent,
        policy=policy,
        context=ctx,
    )

    assert res.final_state == ExecutionState.CANCELLED
    # Attempt 1 dispatched, but retry attempts must be 0
    assert mock_ptr.click.call_count == 1
    assert res.total_recoveries == 0


# 8: Replan blocked after cancellation
@pytest.mark.asyncio
async def test_replan_blocked_after_cancellation():
    mock_obs = MagicMock()
    mock_snap = MagicMock()
    mock_obs.capture_snapshot = AsyncMock(return_value=mock_snap)

    mock_locator = MagicMock()
    # First returns stale observation triggering replan
    mock_locator.locate_target = MagicMock(return_value=TargetResolutionResult(
        status=TargetResolutionStatus.STALE_OBSERVATION,
        diagnostic_message="Obs snapshot generation mismatch",
    ))

    ctx = ExecutionContext(execution_id="replan-cancel")
    ctx.cancel(CancellationReason.HUMAN_TAKEOVER, "Takeover during replan")

    engine = ClosedLoopExecutionEngine(
        observation=mock_obs,
        target_locator=mock_locator,
    )

    intent = TargetIntent(intent_id="i_replan", label="ReplanTarget")
    res = await engine.execute_task_action(
        session_id="s1",
        task_id="t4",
        prompt="Replan action",
        target_intent=intent,
        context=ctx,
    )

    assert res.final_state == ExecutionState.HUMAN_TAKEOVER
    assert res.total_recoveries == 0
    # Replan locator should not be called in a loop
    assert mock_locator.locate_target.call_count <= 1


# 9: Terminal state remains terminal
def test_terminal_state_remains_terminal():
    sm = ClosedLoopStateMachine()
    sm.transition_to(ExecutionState.OBSERVING)
    sm.transition_to(ExecutionState.HUMAN_TAKEOVER, "Human takeover triggered")

    assert sm.is_terminal
    assert sm.current_state == ExecutionState.HUMAN_TAKEOVER

    # Attempting to transition from terminal state must raise StateTransitionError
    with pytest.raises(StateTransitionError):
        sm.transition_to(ExecutionState.OBSERVING)

    with pytest.raises(StateTransitionError):
        sm.transition_to(ExecutionState.RETRYING)


# 11: In-flight dispatch status semantics
@pytest.mark.asyncio
async def test_in_flight_dispatch_status_semantics():
    gate = AutonomousDispatchGate()
    ctx = ExecutionContext(execution_id="in-flight-test")

    async def in_flight_fail():
        raise asyncio.CancelledError()

    with pytest.raises(PreemptionSafetyError) as exc_info:
        await gate.execute_guarded(
            "click",
            ctx,
            in_flight_fail,
            current_state="DISPATCHING",
            attempt_number=1,
        )

    err = exc_info.value
    # Truthfully OUTCOME_UNKNOWN because the OS call began before cancellation
    assert err.dispatch_stage == DispatchStage.OUTCOME_UNKNOWN


# 12: Structured preemption history
def test_structured_preemption_history():
    ctx = ExecutionContext(execution_id="hist-test", max_history=3)
    for i in range(5):
        rec = PreemptionRecord(
            execution_id="hist-test",
            reason=CancellationReason.HUMAN_TAKEOVER,
            state_at_preemption=f"STATE_{i}",
            attempt_number=i,
            action_dispatched_status=DispatchStage.NOT_DISPATCHED,
        )
        ctx.record_preemption(rec)

    records = ctx.get_preemption_records()
    # Bounded to max_history=3
    assert len(records) == 3
    assert records[-1].state_at_preemption == "STATE_4"
    assert records[0].state_at_preemption == "STATE_2"
    assert ctx.last_preemption_record.attempt_number == 4
