"""Unit tests for AutonomousDispatchGate and in-flight action semantics."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.execution.context import (
    CancellationReason,
    DispatchStage,
    ExecutionContext,
)
from orbit.runtime.execution.safety_gate import (
    AutonomousDispatchGate,
    PreemptionSafetyError,
)


@pytest.mark.asyncio
async def test_gate_permits_when_clean():
    """Gate permits action when not cancelled and takeover is inactive."""
    ctx = ExecutionContext(execution_id="test-clean")
    gate = AutonomousDispatchGate()

    mock_action = AsyncMock(return_value="action_ok")
    stage, res = await gate.execute_guarded(
        "mock_action",
        ctx,
        mock_action,
        "DISPATCHING",
        1,
        0,
        generation_id=1,
        target_id="btn_1",
        arg1="foo",
    )

    assert stage == DispatchStage.DISPATCHED
    assert res == "action_ok"
    mock_action.assert_awaited_once_with(arg1="foo")
    assert ctx.last_preemption_record is None


@pytest.mark.asyncio
async def test_gate_rejects_fail_closed_when_cancelled():
    """Gate rejects before OS dispatch if context is cancelled."""
    ctx = ExecutionContext(execution_id="test-cancelled")
    ctx.cancel(CancellationReason.OPERATOR_CANCEL, "Operator abort")

    gate = AutonomousDispatchGate()
    mock_action = AsyncMock()

    with pytest.raises(PreemptionSafetyError) as exc_info:
        await gate.execute_guarded(
            "mock_action",
            ctx,
            mock_action,
            "DISPATCHING",
            attempt_number=1,
            replan_number=0,
            generation_id=10,
            target_id="btn_submit",
        )

    err = exc_info.value
    assert err.dispatch_stage == DispatchStage.NOT_DISPATCHED
    assert err.reason == CancellationReason.OPERATOR_CANCEL
    # ZERO OS calls
    mock_action.assert_not_called()

    # Verify forensic preemption record
    rec = ctx.last_preemption_record
    assert rec is not None
    assert rec.execution_id == "test-cancelled"
    assert rec.reason == CancellationReason.OPERATOR_CANCEL
    assert rec.action_dispatched_status == DispatchStage.NOT_DISPATCHED
    assert rec.last_known_observation_generation == 10
    assert rec.last_target_resolution_result == "btn_submit"


@pytest.mark.asyncio
async def test_gate_rejects_fail_closed_when_takeover_active():
    """Gate rejects before OS dispatch if human takeover is active."""
    takeover_active = True

    def check_takeover():
        return takeover_active

    ctx = ExecutionContext(
        execution_id="test-takeover",
        takeover_checker=check_takeover,
    )
    gate = AutonomousDispatchGate()
    mock_action = AsyncMock()

    with pytest.raises(PreemptionSafetyError) as exc_info:
        await gate.execute_guarded(
            "pointer_click",
            ctx,
            mock_action,
            "DISPATCHING",
            attempt_number=2,
            generation_id=5,
            target_id="menu_item",
        )

    err = exc_info.value
    assert err.dispatch_stage == DispatchStage.NOT_DISPATCHED
    assert err.reason == CancellationReason.HUMAN_TAKEOVER
    mock_action.assert_not_called()

    rec = ctx.last_preemption_record
    assert rec is not None
    assert rec.reason == CancellationReason.HUMAN_TAKEOVER
    assert rec.action_dispatched_status == DispatchStage.NOT_DISPATCHED


@pytest.mark.asyncio
async def test_gate_invokes_emergency_safety_on_rejection():
    """Gate calls emergency safety coordinator when rejecting."""
    safety_called = False

    async def emergency_stop():
        nonlocal safety_called
        safety_called = True

    ctx = ExecutionContext(execution_id="test-safety-cb")
    ctx.cancel(CancellationReason.HUMAN_TAKEOVER)

    gate = AutonomousDispatchGate(emergency_safety_fn=emergency_stop)
    mock_action = AsyncMock()

    with pytest.raises(PreemptionSafetyError):
        await gate.execute_guarded("click", ctx, mock_action)

    assert safety_called is True
    mock_action.assert_not_called()


@pytest.mark.asyncio
async def test_gate_in_flight_cancellation_epistemic_truthfulness():
    """If cancellation interrupts an in-flight OS call, gate reports OUTCOME_UNKNOWN."""
    ctx = ExecutionContext(execution_id="test-in-flight")
    gate = AutonomousDispatchGate()

    async def in_flight_action():
        # Action started, and gets cancelled while running
        raise asyncio.CancelledError()

    with pytest.raises(PreemptionSafetyError) as exc_info:
        await gate.execute_guarded(
            "slow_click",
            ctx,
            in_flight_action,
            "DISPATCHING",
            attempt_number=1,
        )

    err = exc_info.value
    # Must NOT falsely claim NOT_DISPATCHED because the call was already in flight!
    assert err.dispatch_stage == DispatchStage.OUTCOME_UNKNOWN

    rec = ctx.last_preemption_record
    assert rec is not None
    assert rec.action_dispatched_status == DispatchStage.OUTCOME_UNKNOWN


@pytest.mark.asyncio
async def test_gate_can_dispatch_helper():
    """can_dispatch accurately previews gate allowance."""
    ctx = ExecutionContext()
    gate = AutonomousDispatchGate()

    allowed, msg, reason = await gate.can_dispatch(ctx)
    assert allowed is True
    assert msg is None

    ctx.cancel(CancellationReason.RUNTIME_SHUTDOWN)
    allowed, msg, reason = await gate.can_dispatch(ctx)
    assert allowed is False
    assert reason == CancellationReason.RUNTIME_SHUTDOWN
    assert "cancelled" in msg
