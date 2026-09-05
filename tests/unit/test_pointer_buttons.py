"""Unit tests for ButtonTransactionExecutor and atomic click operations in ORBIT M1.2B."""

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


def make_test_executor(sendinput_fn=None, abi_valid=True):
    action_counter = ActionCounter()
    abi_res = (
        validate_runtime_abi()
        if abi_valid
        else validate_runtime_abi(simulated_override={"sizeof_input": 999})
    )
    abi_gate = AbiGate(validation_result=abi_res)

    if sendinput_fn is None:
        sendinput_fn = lambda n, packet, size: 1  # default mock accepts 1 packet

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


def test_button_down_and_up_success():
    executor, state_mgr, counter = make_test_executor()

    # BUTTON_DOWN
    res_down = executor.execute_button_down(MouseButton.LEFT)
    assert res_down.status == ButtonExecutionStatus.BUTTON_DOWN_ACCEPTED
    assert res_down.accepted_packets == 1
    assert state_mgr.transaction_state == PointerTransactionState.BUTTON_HELD_SYNTHETIC
    assert MouseButton.LEFT in state_mgr.held_buttons

    # BUTTON_UP
    res_up = executor.execute_button_up(MouseButton.LEFT)
    assert res_up.status == ButtonExecutionStatus.BUTTON_UP_ACCEPTED
    assert res_up.accepted_packets == 1
    assert state_mgr.transaction_state == PointerTransactionState.IDLE
    assert len(state_mgr.held_buttons) == 0


def test_button_down_dispatch_zero():
    # SendInput returns 0 (rejection)
    executor, state_mgr, counter = make_test_executor(sendinput_fn=lambda n, p, s: 0)

    res = executor.execute_button_down(MouseButton.RIGHT)
    assert res.status == ButtonExecutionStatus.DISPATCH_ZERO
    assert res.accepted_packets == 0
    assert state_mgr.transaction_state == PointerTransactionState.IDLE
    assert len(state_mgr.held_buttons) == 0


def test_button_up_dispatch_zero_fails_closed():
    # SendInput succeeds for DOWN (first call), but fails for UP (second call)
    calls = 0

    def mock_sendinput(n, p, s):
        nonlocal calls
        calls += 1
        return 1 if calls == 1 else 0

    executor, state_mgr, counter = make_test_executor(sendinput_fn=mock_sendinput)

    res_down = executor.execute_button_down(MouseButton.LEFT)
    assert res_down.status == ButtonExecutionStatus.BUTTON_DOWN_ACCEPTED

    res_up = executor.execute_button_up(MouseButton.LEFT)
    assert res_up.status == ButtonExecutionStatus.DISPATCH_ZERO_LOCKED
    assert res_up.is_locked is True
    assert res_up.recovery_token is not None
    assert state_mgr.is_locked is True
    assert state_mgr.transaction_state == PointerTransactionState.UNRESOLVED_LOCKED


def test_atomic_click_execution():
    executor, state_mgr, counter = make_test_executor()

    res = executor.execute_click(button=MouseButton.LEFT, dwell_ms=10.0)
    assert res.status == ClickExecutionStatus.CLICK_VERIFIED
    assert res.down_result is not None
    assert res.down_result.status == ButtonExecutionStatus.BUTTON_DOWN_ACCEPTED
    assert res.up_result is not None
    assert res.up_result.status == ButtonExecutionStatus.BUTTON_UP_ACCEPTED
    assert state_mgr.transaction_state == PointerTransactionState.IDLE


def test_multi_button_support():
    for btn in [MouseButton.LEFT, MouseButton.RIGHT, MouseButton.MIDDLE]:
        executor, state_mgr, counter = make_test_executor()
        res = executor.execute_click(button=btn, dwell_ms=5.0)
        assert res.status == ClickExecutionStatus.CLICK_VERIFIED
        assert res.button == btn


def test_emergency_sanitization_success():
    executor, state_mgr, counter = make_test_executor()

    # Manually hold a button
    executor.execute_button_down(MouseButton.MIDDLE)
    assert MouseButton.MIDDLE in state_mgr.held_buttons

    # Execute emergency sanitization
    san_res = executor.emergency_sanitize()
    assert san_res.success is True
    assert MouseButton.MIDDLE in san_res.released_buttons
    assert state_mgr.transaction_state == PointerTransactionState.IDLE
    assert len(state_mgr.held_buttons) == 0


def test_abi_invalid_rejection():
    executor, state_mgr, counter = make_test_executor(abi_valid=False)

    res_down = executor.execute_button_down(MouseButton.LEFT)
    assert res_down.status == ButtonExecutionStatus.REJECTED_ABI_INVALID

    res_click = executor.execute_click(MouseButton.LEFT)
    assert res_click.status == ClickExecutionStatus.REJECTED_ABI_INVALID
