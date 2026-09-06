"""Unit tests for TakeoverStateManager and state transition invariants."""

import time
import pytest
from orbit.adapters.takeover.classifier import (
    InputDevice,
    InputEventType,
    InputSource,
    TakeoverEvidence,
)
from orbit.adapters.takeover.state import (
    TakeoverState,
    TakeoverStateManager,
    TakeoverStateTransitionError,
)


def _make_evidence(event_id: int = 1) -> TakeoverEvidence:
    return TakeoverEvidence(
        event_id=event_id,
        timestamp_ns=time.perf_counter_ns(),
        device=InputDevice.MOUSE,
        event_type=InputEventType.MOUSE_MOVE,
        source=InputSource.USER_PHYSICAL,
        should_trigger_takeover=True,
        reason="Test takeover",
        x=10,
        y=20,
    )


def test_takeover_state_manager_initial_state():
    mgr = TakeoverStateManager()
    assert mgr.current_state == TakeoverState.STOPPED
    assert mgr.is_monitoring is False
    assert mgr.is_takeover_active is False


def test_takeover_state_manager_valid_lifecycle():
    mgr = TakeoverStateManager()
    assert mgr.transition_to(TakeoverState.STARTING) is True
    assert mgr.current_state == TakeoverState.STARTING

    assert mgr.transition_to(TakeoverState.MONITORING) is True
    assert mgr.current_state == TakeoverState.MONITORING
    assert mgr.is_monitoring is True
    assert mgr.is_takeover_active is False

    # Takeover trigger
    ev = _make_evidence(1)
    is_new = mgr.handle_takeover_event(ev)
    assert is_new is True
    assert mgr.current_state == TakeoverState.TAKEOVER_ACTIVE
    assert mgr.is_takeover_active is True
    assert mgr.last_evidence == ev

    # Explicit release flow
    assert mgr.transition_to(TakeoverState.RELEASING) is True
    assert mgr.transition_to(TakeoverState.MONITORING) is True
    assert mgr.current_state == TakeoverState.MONITORING
    assert mgr.is_takeover_active is False


def test_takeover_state_manager_invalid_transitions():
    mgr = TakeoverStateManager()
    # From STOPPED, cannot jump directly to TAKEOVER_ACTIVE or RELEASE_PENDING
    with pytest.raises(TakeoverStateTransitionError):
        mgr.transition_to(TakeoverState.TAKEOVER_ACTIVE)

    with pytest.raises(TakeoverStateTransitionError):
        mgr.transition_to(TakeoverState.RELEASE_PENDING)


def test_takeover_state_manager_deduplication():
    mgr = TakeoverStateManager(quiet_period_seconds=1.0)
    mgr.transition_to(TakeoverState.STARTING)
    mgr.transition_to(TakeoverState.MONITORING)

    ev1 = _make_evidence(1)
    ev2 = _make_evidence(2)
    ev3 = _make_evidence(3)

    # First event triggers transition
    assert mgr.handle_takeover_event(ev1) is True
    assert mgr.current_state == TakeoverState.TAKEOVER_ACTIVE

    # Rapid subsequent events are deduplicated
    assert mgr.handle_takeover_event(ev2) is False
    assert mgr.handle_takeover_event(ev3) is False
    assert mgr.current_state == TakeoverState.TAKEOVER_ACTIVE
    assert mgr.last_evidence == ev3


def test_takeover_state_manager_quiet_period():
    mgr = TakeoverStateManager(quiet_period_seconds=0.05)
    mgr.transition_to(TakeoverState.STARTING)
    mgr.transition_to(TakeoverState.MONITORING)

    ev = _make_evidence(1)
    mgr.handle_takeover_event(ev)
    assert mgr.current_state == TakeoverState.TAKEOVER_ACTIVE

    # Wait for quiet period timer to fire
    for _ in range(25):
        if mgr.current_state == TakeoverState.RELEASE_PENDING:
            break
        time.sleep(0.02)
    assert mgr.current_state == TakeoverState.RELEASE_PENDING


def test_takeover_state_manager_listener_notifications():
    mgr = TakeoverStateManager()
    transitions = []

    def on_change(old_st, new_st, ev):
        transitions.append((old_st, new_st))

    mgr.add_listener(on_change)
    mgr.transition_to(TakeoverState.STARTING)
    mgr.transition_to(TakeoverState.MONITORING)

    assert transitions == [
        (TakeoverState.STOPPED, TakeoverState.STARTING),
        (TakeoverState.STARTING, TakeoverState.MONITORING),
    ]
