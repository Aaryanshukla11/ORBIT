"""Unit tests for PointerStateManager, state transitions, and fail-closed hard lockout in ORBIT M1.2B."""

import pytest

from orbit.adapters.pointer.safety import MouseButton
from orbit.adapters.pointer.state import (
    LockoutReason,
    PointerStateManager,
    PointerStateSnapshot,
    PointerTransactionState,
)


def test_state_manager_initial_state():
    mgr = PointerStateManager()
    snap = mgr.get_snapshot()

    assert snap.transaction_state == PointerTransactionState.IDLE
    assert len(snap.held_buttons) == 0
    assert snap.is_locked is False
    assert snap.lockout_reason == LockoutReason.NONE


def test_valid_single_button_lifecycle():
    mgr = PointerStateManager()

    # Step 1: Start DOWN
    mgr.start_button_down(MouseButton.LEFT)
    assert mgr.transaction_state == PointerTransactionState.BUTTON_DOWN_IN_PROGRESS

    # Step 2: Confirm DOWN
    mgr.confirm_button_down(MouseButton.LEFT)
    assert mgr.transaction_state == PointerTransactionState.BUTTON_HELD_SYNTHETIC
    assert MouseButton.LEFT in mgr.held_buttons

    # Step 3: Start UP
    mgr.start_button_up(MouseButton.LEFT)
    assert mgr.transaction_state == PointerTransactionState.BUTTON_UP_IN_PROGRESS

    # Step 4: Confirm UP
    mgr.confirm_button_up(MouseButton.LEFT)
    assert mgr.transaction_state == PointerTransactionState.IDLE
    assert len(mgr.held_buttons) == 0


def test_double_down_rejection():
    mgr = PointerStateManager()
    mgr.start_button_down(MouseButton.LEFT)
    mgr.confirm_button_down(MouseButton.LEFT)

    # Attempting to press LEFT again must be rejected
    with pytest.raises(RuntimeError, match="Must be IDLE"):
        mgr.start_button_down(MouseButton.LEFT)


def test_release_unheld_button_rejection():
    mgr = PointerStateManager()
    # Cannot release when no button is held
    with pytest.raises(RuntimeError, match="Must be BUTTON_HELD_SYNTHETIC"):
        mgr.start_button_up(MouseButton.LEFT)

    # Press LEFT, then try to release RIGHT
    mgr.start_button_down(MouseButton.LEFT)
    mgr.confirm_button_down(MouseButton.LEFT)

    with pytest.raises(RuntimeError, match="not in held synthetic button set"):
        mgr.start_button_up(MouseButton.RIGHT)


def test_down_abort_returns_to_idle():
    mgr = PointerStateManager()
    mgr.start_button_down(MouseButton.RIGHT)
    assert mgr.transaction_state == PointerTransactionState.BUTTON_DOWN_IN_PROGRESS

    mgr.abort_button_down(MouseButton.RIGHT)
    assert mgr.transaction_state == PointerTransactionState.IDLE
    assert len(mgr.held_buttons) == 0


def test_button_up_dispatch_failure_locks_state_machine():
    mgr = PointerStateManager()
    mgr.start_button_down(MouseButton.LEFT)
    mgr.confirm_button_down(MouseButton.LEFT)

    mgr.start_button_up(MouseButton.LEFT)
    token = mgr.fail_button_up_and_lock(MouseButton.LEFT, LockoutReason.BUTTON_UP_DISPATCH_FAILED)

    assert mgr.is_locked is True
    assert mgr.transaction_state == PointerTransactionState.UNRESOLVED_LOCKED
    assert mgr.lockout_reason == LockoutReason.BUTTON_UP_DISPATCH_FAILED
    assert token.startswith("rec_ptr_")

    # While locked, all subsequent actions must be refused
    with pytest.raises(RuntimeError, match="UNRESOLVED_LOCKED"):
        mgr.start_button_down(MouseButton.RIGHT)

    with pytest.raises(RuntimeError, match="UNRESOLVED_LOCKED"):
        mgr.start_button_up(MouseButton.LEFT)


def test_emergency_sanitization_lifecycle():
    mgr = PointerStateManager()
    mgr.start_button_down(MouseButton.LEFT)
    mgr.confirm_button_down(MouseButton.LEFT)

    mgr.start_emergency_sanitization()
    assert mgr.transaction_state == PointerTransactionState.SANITIZATION_PENDING

    mgr.confirm_emergency_sanitization()
    assert mgr.transaction_state == PointerTransactionState.IDLE
    assert len(mgr.held_buttons) == 0


def test_emergency_sanitization_failure_locks_state():
    mgr = PointerStateManager()
    mgr.start_button_down(MouseButton.MIDDLE)
    mgr.confirm_button_down(MouseButton.MIDDLE)

    mgr.start_emergency_sanitization()
    token = mgr.fail_emergency_sanitization_and_lock(LockoutReason.SANITIZATION_DISPATCH_FAILED)

    assert mgr.is_locked is True
    assert mgr.transaction_state == PointerTransactionState.UNRESOLVED_LOCKED
    assert token is not None


def test_recovery_token_unlock_workflow():
    mgr = PointerStateManager()
    mgr.start_button_down(MouseButton.LEFT)
    mgr.confirm_button_down(MouseButton.LEFT)
    mgr.start_button_up(MouseButton.LEFT)
    token = mgr.fail_button_up_and_lock(MouseButton.LEFT, LockoutReason.BUTTON_UP_DISPATCH_FAILED)

    # Wrong token fails
    assert mgr.recover_locked_state("INVALID_TOKEN") is False
    assert mgr.is_locked is True

    # Empty token fails
    assert mgr.recover_locked_state("") is False
    assert mgr.is_locked is True

    # Correct token unlocks cleanly to IDLE
    assert mgr.recover_locked_state(token) is True
    assert mgr.is_locked is False
    assert mgr.transaction_state == PointerTransactionState.IDLE
    assert len(mgr.held_buttons) == 0
