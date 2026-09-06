"""Hierarchical state machine for the closed-loop execution engine."""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple

from orbit.runtime.execution.models import ExecutionState
from orbit.runtime.state_machine import StateTransitionError


class ClosedLoopStateMachine:
    """Manages explicit execution states and transitions with diagnostic audit trail."""

    _TERMINAL_STATES: Set[ExecutionState] = {
        ExecutionState.SUCCEEDED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
        ExecutionState.HUMAN_TAKEOVER,
    }

    _VALID_TRANSITIONS: Dict[ExecutionState, Set[ExecutionState]] = {
        ExecutionState.IDLE: {
            ExecutionState.OBSERVING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.OBSERVING: {
            ExecutionState.PLANNING,
            ExecutionState.RESOLVING_TARGET,
            ExecutionState.RECOVERING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.PLANNING: {
            ExecutionState.RESOLVING_TARGET,
            ExecutionState.VALIDATING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.RESOLVING_TARGET: {
            ExecutionState.VALIDATING,
            ExecutionState.RECOVERING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.VALIDATING: {
            ExecutionState.ACTING,
            ExecutionState.DISPATCHING,
            ExecutionState.RECOVERING,
            ExecutionState.REPLANNING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.ACTING: {
            ExecutionState.DISPATCHING,
            ExecutionState.RE_OBSERVING,
            ExecutionState.VERIFYING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.DISPATCHING: {
            ExecutionState.ACTING,
            ExecutionState.RE_OBSERVING,
            ExecutionState.VERIFYING,
            ExecutionState.RECOVERING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.RE_OBSERVING: {
            ExecutionState.VERIFYING,
            ExecutionState.RECOVERING,
            ExecutionState.REPLANNING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.VERIFYING: {
            ExecutionState.SUCCEEDED,
            ExecutionState.RETRY_PENDING,
            ExecutionState.REPLANNING,
            ExecutionState.RECOVERING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.RETRY_PENDING: {
            ExecutionState.OBSERVING,
            ExecutionState.RESOLVING_TARGET,
            ExecutionState.RETRYING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.REPLANNING: {
            ExecutionState.OBSERVING,
            ExecutionState.RESOLVING_TARGET,
            ExecutionState.RETRYING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.RECOVERING: {
            ExecutionState.RETRYING,
            ExecutionState.RETRY_PENDING,
            ExecutionState.REPLANNING,
            ExecutionState.OBSERVING,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.RETRYING: {
            ExecutionState.OBSERVING,
            ExecutionState.RESOLVING_TARGET,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.HUMAN_TAKEOVER,
        },
        ExecutionState.SUCCEEDED: set(),
        ExecutionState.FAILED: set(),
        ExecutionState.CANCELLED: set(),
        ExecutionState.HUMAN_TAKEOVER: set(),
    }

    def __init__(self, initial_state: ExecutionState = ExecutionState.IDLE) -> None:
        self._state = initial_state
        self._history: List[Tuple[str, str, str, float]] = []

    @property
    def current_state(self) -> ExecutionState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in self._TERMINAL_STATES

    @property
    def transition_history(self) -> List[Tuple[str, str, str, float]]:
        return list(self._history)

    def can_transition_to(self, target: ExecutionState) -> bool:
        if target == self._state:
            return True
        if self._state in self._TERMINAL_STATES:
            return False
        return target in self._VALID_TRANSITIONS.get(self._state, set())

    def transition_to(self, target: ExecutionState, reason: str = "") -> ExecutionState:
        if target == self._state:
            return self._state

        if not self.can_transition_to(target):
            raise StateTransitionError(
                self._state.value,
                target.value,
                entity_name="ClosedLoopExecutionEngine",
            )

        from_state = self._state
        self._state = target
        self._history.append((from_state.value, target.value, reason, time.perf_counter()))
        return self._state
