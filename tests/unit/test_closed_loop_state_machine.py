"""Unit tests for ClosedLoopStateMachine.

Validates:
1. Valid state transitions
2. Illegal transitions rejected
3. Terminal states remain terminal
4. Successful execution path
5. Failed execution path
6. Cancelled execution path
7. Idempotent transitions & audit history
"""

import pytest
from orbit.runtime.execution.models import ExecutionState
from orbit.runtime.execution.state_machine import ClosedLoopStateMachine
from orbit.runtime.state_machine import StateTransitionError


def test_valid_state_transitions_happy_path():
    """Verify happy-path transition sequence: IDLE -> OBSERVING -> RESOLVING -> VALIDATING -> ACTING -> VERIFYING -> SUCCEEDED."""
    sm = ClosedLoopStateMachine()
    assert sm.current_state == ExecutionState.IDLE
    assert not sm.is_terminal

    sm.transition_to(ExecutionState.OBSERVING, "Pre-action observe")
    assert sm.current_state == ExecutionState.OBSERVING

    sm.transition_to(ExecutionState.RESOLVING_TARGET, "Locating element")
    assert sm.current_state == ExecutionState.RESOLVING_TARGET

    sm.transition_to(ExecutionState.VALIDATING, "Checking coordinates")
    assert sm.current_state == ExecutionState.VALIDATING

    sm.transition_to(ExecutionState.ACTING, "Executing click")
    assert sm.current_state == ExecutionState.ACTING

    sm.transition_to(ExecutionState.VERIFYING, "Checking post-action state")
    assert sm.current_state == ExecutionState.VERIFYING

    sm.transition_to(ExecutionState.SUCCEEDED, "Target state confirmed")
    assert sm.current_state == ExecutionState.SUCCEEDED
    assert sm.is_terminal


def test_illegal_state_transitions_rejected():
    """Verify illegal transitions raise StateTransitionError."""
    sm = ClosedLoopStateMachine()

    # Cannot jump from IDLE directly to ACTING or VERIFYING
    with pytest.raises(StateTransitionError):
        sm.transition_to(ExecutionState.ACTING)

    with pytest.raises(StateTransitionError):
        sm.transition_to(ExecutionState.VERIFYING)

    sm.transition_to(ExecutionState.OBSERVING)
    # Cannot jump from OBSERVING to SUCCEEDED without acting/verifying
    with pytest.raises(StateTransitionError):
        sm.transition_to(ExecutionState.SUCCEEDED)


def test_terminal_states_remain_terminal():
    """Verify terminal states (SUCCEEDED, FAILED, CANCELLED, HUMAN_TAKEOVER) cannot transition out."""
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

        with pytest.raises(StateTransitionError):
            sm.transition_to(ExecutionState.IDLE)


def test_successful_execution_path():
    """Verify successful path records complete transition audit trail."""
    sm = ClosedLoopStateMachine()
    sm.transition_to(ExecutionState.OBSERVING, "Observe")
    sm.transition_to(ExecutionState.RESOLVING_TARGET, "Resolve")
    sm.transition_to(ExecutionState.VALIDATING, "Validate")
    sm.transition_to(ExecutionState.DISPATCHING, "Dispatch")
    sm.transition_to(ExecutionState.RE_OBSERVING, "Re-observe")
    sm.transition_to(ExecutionState.VERIFYING, "Verify")
    sm.transition_to(ExecutionState.SUCCEEDED, "Confirmed")

    assert sm.current_state == ExecutionState.SUCCEEDED
    assert len(sm.transition_history) == 7
    assert sm.transition_history[-1][1] == ExecutionState.SUCCEEDED.value


def test_failed_execution_path():
    """Verify failure transition from active states transitions to FAILED and terminates."""
    for active_state in [
        ExecutionState.OBSERVING,
        ExecutionState.RESOLVING_TARGET,
        ExecutionState.VALIDATING,
        ExecutionState.ACTING,
        ExecutionState.VERIFYING,
        ExecutionState.RECOVERING,
    ]:
        sm = ClosedLoopStateMachine(initial_state=active_state)
        sm.transition_to(ExecutionState.FAILED, "Fatal error occurred")
        assert sm.current_state == ExecutionState.FAILED
        assert sm.is_terminal


def test_cancelled_execution_path():
    """Verify cancellation transition from active states transitions to CANCELLED and terminates."""
    sm = ClosedLoopStateMachine(initial_state=ExecutionState.VALIDATING)
    sm.transition_to(ExecutionState.CANCELLED, "Operator requested cancel")
    assert sm.current_state == ExecutionState.CANCELLED
    assert sm.is_terminal


def test_retry_pending_and_replanning_transitions():
    """Verify RETRY_PENDING and REPLANNING transitions loop safely back to OBSERVING."""
    sm = ClosedLoopStateMachine(initial_state=ExecutionState.VERIFYING)
    sm.transition_to(ExecutionState.RETRY_PENDING, "Verification failed, retrying")
    assert sm.current_state == ExecutionState.RETRY_PENDING

    sm.transition_to(ExecutionState.OBSERVING, "Fresh observation for retry")
    assert sm.current_state == ExecutionState.OBSERVING

    sm.transition_to(ExecutionState.RESOLVING_TARGET, "Resolving target")
    sm.transition_to(ExecutionState.VALIDATING, "Validating again")
    sm.transition_to(ExecutionState.REPLANNING, "Generation changed, replanning")
    assert sm.current_state == ExecutionState.REPLANNING

    sm.transition_to(ExecutionState.OBSERVING, "Fresh observation after generation change")
    assert sm.current_state == ExecutionState.OBSERVING


def test_idempotent_self_transition():
    """Verify transitioning to current state is idempotent and does not log duplicate events."""
    sm = ClosedLoopStateMachine(initial_state=ExecutionState.OBSERVING)
    res = sm.transition_to(ExecutionState.OBSERVING)
    assert res == ExecutionState.OBSERVING
    assert len(sm.transition_history) == 0
