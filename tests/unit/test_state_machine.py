"""Unit tests for runtime and task state machines."""

import pytest

from orbit.contracts.runtime import ActionStage, SystemState, TaskStatus
from orbit.runtime.state_machine import (
    ActionStateMachine,
    StateTransitionError,
    SystemStateMachine,
    TaskStateMachine,
)


def test_system_state_machine_valid_flow():
    sm = SystemStateMachine(SystemState.BOOTING)
    assert sm.current_state == SystemState.BOOTING

    sm.transition_to(SystemState.IDLE)
    assert sm.current_state == SystemState.IDLE

    sm.transition_to(SystemState.BUSY)
    assert sm.current_state == SystemState.BUSY

    sm.transition_to(SystemState.HUMAN_TAKEOVER_ACTIVE)
    assert sm.current_state == SystemState.HUMAN_TAKEOVER_ACTIVE

    sm.transition_to(SystemState.IDLE)
    assert sm.current_state == SystemState.IDLE


def test_system_state_machine_invalid_transition():
    sm = SystemStateMachine(SystemState.BOOTING)
    with pytest.raises(StateTransitionError):
        # Cannot jump from BOOTING directly to BUSY
        sm.transition_to(SystemState.BUSY)


def test_system_state_machine_unresolved_locked_requires_token():
    sm = SystemStateMachine(SystemState.IDLE)
    sm.transition_to(SystemState.UNRESOLVED_LOCKED)

    with pytest.raises(StateTransitionError):
        # Unlocking without valid token should fail
        sm.transition_to(SystemState.IDLE, recovery_token="WRONG_TOKEN")

    sm.transition_to(SystemState.IDLE, recovery_token="CONFIRM_OPERATOR_MANUAL_RESET")
    assert sm.current_state == SystemState.IDLE


def test_task_state_machine_progression():
    sm = TaskStateMachine(TaskStatus.CREATED)
    sm.transition_to(TaskStatus.VALIDATING)
    sm.transition_to(TaskStatus.READY)
    sm.transition_to(TaskStatus.RUNNING)
    sm.transition_to(TaskStatus.VERIFYING)
    sm.transition_to(TaskStatus.COMPLETED)
    assert sm.current_status == TaskStatus.COMPLETED

    # Terminal state cannot transition
    with pytest.raises(StateTransitionError):
        sm.transition_to(TaskStatus.RUNNING)


def test_action_state_machine_lifecycle():
    sm = ActionStateMachine(ActionStage.PENDING)
    sm.transition_to(ActionStage.DISPATCHED)
    sm.transition_to(ActionStage.EXECUTING)
    sm.transition_to(ActionStage.VERIFYING)
    sm.transition_to(ActionStage.COMPLETED)
    assert sm.current_stage == ActionStage.COMPLETED
