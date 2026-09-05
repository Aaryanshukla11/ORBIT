"""Unit tests for Button and Click cooperative cancellation in ORBIT M1.2B."""

import pytest

from orbit.adapters.pointer.buttons import (
    ButtonExecutionStatus,
    ButtonTransactionExecutor,
    ClickExecutionStatus,
)
from orbit.adapters.pointer.health import ActionCounter
from orbit.adapters.pointer.movement import NativeDispatchGateway
from orbit.adapters.pointer.safety import (
    AbiGate,
    MouseButton,
    validate_runtime_abi,
)
from orbit.adapters.pointer.state import PointerStateManager, PointerTransactionState
from orbit.runtime.cancellation import CancellationSource, CancellationToken


def make_test_executor(sendinput_fn=None):
    action_counter = ActionCounter()
    abi_res = validate_runtime_abi()
    abi_gate = AbiGate(validation_result=abi_res)

    if sendinput_fn is None:
        sendinput_fn = lambda n, packet, size: 1

    gateway = NativeDispatchGateway(
        abi_gate=abi_gate,
        action_counter=action_counter,
        sendinput_override=sendinput_fn,
    )
    state_mgr = PointerStateManager()
    executor = ButtonTransactionExecutor(
        native_gateway=gateway,
        state_manager=state_mgr,
        abi_gate=abi_gate,
        action_counter=action_counter,
    )
    return executor, state_mgr, action_counter


def test_button_down_cancellation_before_dispatch():
    executor, state_mgr, counter = make_test_executor()

    src = CancellationSource()
    src.cancel()  # Cancel token before invoking

    res = executor.execute_button_down(MouseButton.LEFT, cancellation_token=src.token)
    assert res.status == ButtonExecutionStatus.CANCELLED_BEFORE_DISPATCH
    assert res.accepted_packets == 0
    assert state_mgr.transaction_state == PointerTransactionState.IDLE
    assert len(state_mgr.held_buttons) == 0


def test_click_cancellation_during_dwell_triggers_sanitization():
    executor, state_mgr, counter = make_test_executor()

    src = CancellationSource()

    def sendinput_with_cancel_trigger(n, p, s):
        src.cancel()  # cancel token when DOWN is dispatched
        return 1

    executor.gateway._sendinput_override = sendinput_with_cancel_trigger

    res = executor.execute_click(
        button=MouseButton.LEFT,
        dwell_ms=50.0,
        cancellation_token=src.token,
    )

    assert res.status == ClickExecutionStatus.CANCELLED_DURING_DWELL_SANITIZED
    assert res.sanitization_result is not None
    assert res.sanitization_result["success"] is True
    assert state_mgr.transaction_state == PointerTransactionState.IDLE
    assert len(state_mgr.held_buttons) == 0


def test_click_cancellation_during_dwell_with_failed_sanitization_locks():
    calls = 0

    def mock_sendinput(n, p, s):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 1  # DOWN succeeds
        return 0  # Sanitization UP fails

    executor, state_mgr, counter = make_test_executor(sendinput_fn=mock_sendinput)

    src = CancellationSource()
    src.cancel()

    # Manually execute DOWN
    down_res = executor.execute_button_down(MouseButton.LEFT)
    assert down_res.status == ButtonExecutionStatus.BUTTON_DOWN_ACCEPTED

    san_res = executor.emergency_sanitize()
    assert san_res.success is False
    assert san_res.is_locked is True
    assert state_mgr.is_locked is True
    assert state_mgr.transaction_state == PointerTransactionState.UNRESOLVED_LOCKED

