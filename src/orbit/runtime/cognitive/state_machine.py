"""Canonical Agent Loop State Machine for ORBIT Closed-Loop Autonomous Execution.

Defines the 13 canonical runtime states, strict transition validation rules,
auditable state transition records, and terminal state protections.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentLoopState(str, Enum):
    """Canonical states of the authoritative closed-loop agent execution lifecycle."""

    INITIALIZING = "INITIALIZING"
    OBSERVING = "OBSERVING"
    REASONING = "REASONING"
    VALIDATING_ACTION = "VALIDATING_ACTION"
    GROUNDING_TARGET = "GROUNDING_TARGET"
    EXECUTING = "EXECUTING"
    WAITING_FOR_SETTLEMENT = "WAITING_FOR_SETTLEMENT"
    VERIFYING_EFFECT = "VERIFYING_EFFECT"
    EVALUATING_PROGRESS = "EVALUATING_PROGRESS"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Explicit legal transition graph for the agent loop state machine
LEGAL_STATE_TRANSITIONS: Dict[AgentLoopState, Set[AgentLoopState]] = {
    AgentLoopState.INITIALIZING: {
        AgentLoopState.OBSERVING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.OBSERVING: {
        AgentLoopState.REASONING,
        AgentLoopState.EVALUATING_PROGRESS,
        AgentLoopState.RECOVERING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.REASONING: {
        AgentLoopState.VALIDATING_ACTION,
        AgentLoopState.EVALUATING_PROGRESS,
        AgentLoopState.RECOVERING,
        AgentLoopState.COMPLETED,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.VALIDATING_ACTION: {
        AgentLoopState.GROUNDING_TARGET,
        AgentLoopState.RECOVERING,
        AgentLoopState.OBSERVING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.GROUNDING_TARGET: {
        AgentLoopState.EXECUTING,
        AgentLoopState.RECOVERING,
        AgentLoopState.OBSERVING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.EXECUTING: {
        AgentLoopState.WAITING_FOR_SETTLEMENT,
        AgentLoopState.VERIFYING_EFFECT,
        AgentLoopState.OBSERVING,
        AgentLoopState.RECOVERING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.WAITING_FOR_SETTLEMENT: {
        AgentLoopState.OBSERVING,
        AgentLoopState.VERIFYING_EFFECT,
        AgentLoopState.RECOVERING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.VERIFYING_EFFECT: {
        AgentLoopState.EVALUATING_PROGRESS,
        AgentLoopState.RECOVERING,
        AgentLoopState.OBSERVING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.EVALUATING_PROGRESS: {
        AgentLoopState.OBSERVING,
        AgentLoopState.COMPLETED,
        AgentLoopState.RECOVERING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    AgentLoopState.RECOVERING: {
        AgentLoopState.OBSERVING,
        AgentLoopState.EVALUATING_PROGRESS,
        AgentLoopState.GROUNDING_TARGET,
        AgentLoopState.EXECUTING,
        AgentLoopState.REASONING,
        AgentLoopState.FAILED,
        AgentLoopState.CANCELLED,
    },
    # Terminal states have NO outward transitions
    AgentLoopState.COMPLETED: set(),
    AgentLoopState.FAILED: set(),
    AgentLoopState.CANCELLED: set(),
}

TERMINAL_STATES: Set[AgentLoopState] = {
    AgentLoopState.COMPLETED,
    AgentLoopState.FAILED,
    AgentLoopState.CANCELLED,
}


class InvalidStateTransitionError(RuntimeError):
    """Raised when an illegal or terminal state machine transition is attempted."""

    def __init__(self, from_state: AgentLoopState, to_state: AgentLoopState, reason: str = "") -> None:
        msg = f"Invalid state transition attempted from {from_state.value} to {to_state.value}. {reason}".strip()
        super().__init__(msg)
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason


class AgentStateTransitionRecord(BaseModel):
    """Auditable, structured record of every state machine transition."""

    transition_id: str = Field(default_factory=lambda: f"tra_{uuid4().hex[:8]}")
    cycle_number: int = Field(default=0, description="Loop iteration / cycle number")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_before: AgentLoopState
    state_after: AgentLoopState
    observation_id: str = Field(default="", description="Active observation ID at transition")
    decision_id: Optional[str] = Field(default=None, description="Active decision ID")
    selected_model: Optional[str] = Field(default=None, description="Model identifier used")
    selected_model_provider: Optional[str] = Field(default=None, description="Model provider")
    action_id: Optional[str] = Field(default=None, description="Action identifier")
    action_type: Optional[str] = Field(default=None, description="Type of action")
    dispatch_success: bool = Field(default=False, description="Whether OS accepted dispatch")
    expected_effect_observed: bool = Field(default=False, description="Whether expected effect was observed")
    goal_satisfied: bool = Field(default=False, description="Whether user goal is verified satisfied")
    failure_reason: Optional[str] = Field(default=None, description="Reason if state is FAILED or RECOVERING")
    recovery_attempt: int = Field(default=0, description="Current recovery retry attempt number")
    duration_ms: float = Field(default=0.0, description="Time spent in preceding state in ms")


class AgentLoopStateMachine:
    """Authoritative state machine governing closed-loop agent execution."""

    def __init__(self, initial_state: AgentLoopState = AgentLoopState.INITIALIZING) -> None:
        self._current_state = initial_state
        self._history: List[AgentStateTransitionRecord] = []
        self._last_transition_time = time.perf_counter()

    @property
    def current_state(self) -> AgentLoopState:
        return self._current_state

    @property
    def is_terminal(self) -> bool:
        return self._current_state in TERMINAL_STATES

    @property
    def history(self) -> List[AgentStateTransitionRecord]:
        return list(self._history)

    def can_transition_to(self, target_state: AgentLoopState) -> bool:
        """Check if transitioning from current_state to target_state is legally allowed."""
        if self._current_state in TERMINAL_STATES:
            return False
        legal_targets = LEGAL_STATE_TRANSITIONS.get(self._current_state, set())
        return target_state in legal_targets

    def transition_to(
        self,
        target_state: AgentLoopState,
        cycle_number: int = 0,
        observation_id: str = "",
        decision_id: Optional[str] = None,
        selected_model: Optional[str] = None,
        selected_model_provider: Optional[str] = None,
        action_id: Optional[str] = None,
        action_type: Optional[str] = None,
        dispatch_success: bool = False,
        expected_effect_observed: bool = False,
        goal_satisfied: bool = False,
        failure_reason: Optional[str] = None,
        recovery_attempt: int = 0,
    ) -> AgentStateTransitionRecord:
        """Execute a state transition, validating against the transition rules and recording audit telemetry."""
        if not self.can_transition_to(target_state):
            if self._current_state in TERMINAL_STATES:
                reason = f"State machine is already in terminal state '{self._current_state.value}'."
            else:
                legal = [s.value for s in LEGAL_STATE_TRANSITIONS.get(self._current_state, set())]
                reason = f"Legal transitions from '{self._current_state.value}' are: {legal}"
            logger.error("State machine transition rejected: %s -> %s (%s)", self._current_state.value, target_state.value, reason)
            raise InvalidStateTransitionError(self._current_state, target_state, reason)

        now = time.perf_counter()
        dur_ms = (now - self._last_transition_time) * 1000.0
        self._last_transition_time = now

        old_state = self._current_state
        self._current_state = target_state

        rec = AgentStateTransitionRecord(
            cycle_number=cycle_number,
            state_before=old_state,
            state_after=target_state,
            observation_id=observation_id,
            decision_id=decision_id,
            selected_model=selected_model,
            selected_model_provider=selected_model_provider,
            action_id=action_id,
            action_type=action_type,
            dispatch_success=dispatch_success,
            expected_effect_observed=expected_effect_observed,
            goal_satisfied=goal_satisfied,
            failure_reason=failure_reason,
            recovery_attempt=recovery_attempt,
            duration_ms=dur_ms,
        )
        self._history.append(rec)
        logger.debug("State Machine: [%s -> %s] (cycle=%d, obs=%s, dur=%.1fms)", old_state.value, target_state.value, cycle_number, observation_id, dur_ms)
        return rec
