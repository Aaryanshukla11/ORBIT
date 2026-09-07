"""Hierarchical state machines with strict transition validation."""

from __future__ import annotations

from typing import Dict, Set
from orbit.contracts.runtime import ActionStage, SystemState, TaskStatus


class StateTransitionError(Exception):
    """Raised when an invalid or forbidden state transition is attempted."""

    def __init__(self, current_state: str, target_state: str, entity_name: str = "Entity") -> None:
        self.current_state = current_state
        self.target_state = target_state
        self.entity_name = entity_name
        super().__init__(
            f"Invalid {entity_name} state transition: cannot transition from {current_state} to {target_state}"
        )


class SystemStateMachine:
    """Manages global ORBIT system lifecycle states."""

    _VALID_TRANSITIONS: Dict[SystemState, Set[SystemState]] = {
        SystemState.BOOTING: {SystemState.IDLE, SystemState.SHUTDOWN},
        SystemState.IDLE: {
            SystemState.BUSY,
            SystemState.HUMAN_TAKEOVER_ACTIVE,
            SystemState.UNRESOLVED_LOCKED,
            SystemState.SHUTDOWN,
        },
        SystemState.BUSY: {
            SystemState.IDLE,
            SystemState.PAUSED,
            SystemState.HUMAN_TAKEOVER_ACTIVE,
            SystemState.UNRESOLVED_LOCKED,
            SystemState.SHUTDOWN,
        },
        SystemState.PAUSED: {
            SystemState.BUSY,
            SystemState.IDLE,
            SystemState.HUMAN_TAKEOVER_ACTIVE,
            SystemState.UNRESOLVED_LOCKED,
            SystemState.SHUTDOWN,
        },
        SystemState.HUMAN_TAKEOVER_ACTIVE: {
            SystemState.IDLE,
            SystemState.BUSY,
            SystemState.UNRESOLVED_LOCKED,
            SystemState.SHUTDOWN,
        },
        SystemState.UNRESOLVED_LOCKED: {
            SystemState.IDLE,  # ONLY via explicit operator manual reset
            SystemState.SHUTDOWN,
        },
        SystemState.SHUTDOWN: set(),  # Terminal
    }

    def __init__(self, initial_state: SystemState = SystemState.BOOTING) -> None:
        self._state = initial_state

    @property
    def current_state(self) -> SystemState:
        return self._state

    def can_transition_to(self, target: SystemState) -> bool:
        if target == self._state:
            return True
        return target in self._VALID_TRANSITIONS.get(self._state, set())

    def transition_to(self, target: SystemState, recovery_token: str | None = None) -> SystemState:
        if target == self._state:
            return self._state

        if self._state == SystemState.UNRESOLVED_LOCKED and target == SystemState.IDLE:
            if recovery_token != "CONFIRM_OPERATOR_MANUAL_RESET":
                raise StateTransitionError(
                    self._state.value,
                    target.value,
                    "System (Requires valid CONFIRM_OPERATOR_MANUAL_RESET token to unlock)",
                )

        if not self.can_transition_to(target):
            raise StateTransitionError(self._state.value, target.value, "System")

        self._state = target
        return self._state


class TaskStateMachine:
    """Manages individual task progression lifecycle states."""

    _VALID_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
        TaskStatus.CREATED: {TaskStatus.QUEUED, TaskStatus.VALIDATING, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.QUEUED: {TaskStatus.VALIDATING, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.VALIDATING: {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
        TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.PAUSED, TaskStatus.FAILED},
        TaskStatus.RUNNING: {
            TaskStatus.VERIFYING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PAUSED,
        },
        TaskStatus.VERIFYING: {
            TaskStatus.COMPLETED,
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        },
        TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
        TaskStatus.COMPLETED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.CANCELLED: set(),
    }

    def __init__(self, initial_status: TaskStatus = TaskStatus.CREATED) -> None:
        self._status = initial_status

    @property
    def current_status(self) -> TaskStatus:
        return self._status

    def can_transition_to(self, target: TaskStatus) -> bool:
        if target == self._status:
            return True
        return target in self._VALID_TRANSITIONS.get(self._status, set())

    def transition_to(self, target: TaskStatus) -> TaskStatus:
        if target == self._status:
            return self._status

        if not self.can_transition_to(target):
            raise StateTransitionError(self._status.value, target.value, "Task")

        self._status = target
        return self._status


class ActionStateMachine:
    """Manages individual action execution stages."""

    _VALID_TRANSITIONS: Dict[ActionStage, Set[ActionStage]] = {
        ActionStage.PENDING: {
            ActionStage.AUTHORIZED,
            ActionStage.DISPATCHED,
            ActionStage.REJECTED,
            ActionStage.CANCELLED,
        },
        ActionStage.AUTHORIZED: {
            ActionStage.DISPATCHED,
            ActionStage.REJECTED,
            ActionStage.CANCELLED,
        },
        ActionStage.DISPATCHED: {
            ActionStage.EXECUTING,
            ActionStage.FAILED,
            ActionStage.CANCELLED,
        },
        ActionStage.EXECUTING: {
            ActionStage.VERIFYING,
            ActionStage.COMPLETED,
            ActionStage.FAILED,
            ActionStage.CANCELLED,
        },
        ActionStage.VERIFYING: {
            ActionStage.COMPLETED,
            ActionStage.FAILED,
            ActionStage.CANCELLED,
        },
        ActionStage.COMPLETED: set(),
        ActionStage.FAILED: set(),
        ActionStage.CANCELLED: set(),
        ActionStage.REJECTED: set(),
    }

    def __init__(self, initial_stage: ActionStage = ActionStage.PENDING) -> None:
        self._stage = initial_stage

    @property
    def current_stage(self) -> ActionStage:
        return self._stage

    def can_transition_to(self, target: ActionStage) -> bool:
        if target == self._stage:
            return True
        return target in self._VALID_TRANSITIONS.get(self._stage, set())

    def transition_to(self, target: ActionStage) -> ActionStage:
        if target == self._stage:
            return self._stage

        if not self.can_transition_to(target):
            raise StateTransitionError(self._stage.value, target.value, "Action")

        self._stage = target
        return self._stage
