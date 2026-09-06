"""Unit tests for Workspace State Machine transitions, generation increments, and invariants."""

import threading
import pytest
from orbit.adapters.workspace.state import (
    WorkspaceStateManager,
    WorkspaceStateTransitionError,
)
from orbit.adapters.workspace.types import WorkspaceState


def test_initial_state():
    sm = WorkspaceStateManager()
    assert sm.current_state == WorkspaceState.UNINITIALIZED
    assert sm.is_ready is False
    assert sm.is_docked is False
    assert sm.desktop_generation_id == 1
    assert sm.topology_generation_id == 1


def test_valid_lifecycle_progression():
    sm = WorkspaceStateManager()

    # UNINITIALIZED -> READY_FLOATING
    sm.transition_to(WorkspaceState.READY_FLOATING, reason="Adapter initialized")
    assert sm.current_state == WorkspaceState.READY_FLOATING
    assert sm.is_ready is True
    assert sm.is_docked is False
    assert sm.desktop_generation_id == 1

    # READY_FLOATING -> REGISTERING
    sm.transition_to(WorkspaceState.REGISTERING, reason="Reserving Right 25%")
    assert sm.current_state == WorkspaceState.REGISTERING
    assert sm.desktop_generation_id == 1

    # REGISTERING -> DOCKED (increments generation)
    sm.transition_to(WorkspaceState.DOCKED, reason="Shell agreed and window positioned")
    assert sm.current_state == WorkspaceState.DOCKED
    assert sm.is_docked is True
    assert sm.desktop_generation_id == 2

    # DOCKED -> RELEASING (increments generation)
    sm.transition_to(WorkspaceState.RELEASING, reason="Undock requested")
    assert sm.current_state == WorkspaceState.RELEASING
    assert sm.desktop_generation_id == 3

    # RELEASING -> READY_FLOATING
    sm.transition_to(WorkspaceState.READY_FLOATING, reason="Unregistration complete")
    assert sm.current_state == WorkspaceState.READY_FLOATING
    assert sm.is_docked is False
    assert sm.desktop_generation_id == 3


def test_reconfiguration_lifecycle():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.DOCKED)
    assert sm.desktop_generation_id == 2

    # Reconfiguring in place: DOCKED -> REGISTERING (increments generation) -> DOCKED (increments generation)
    sm.transition_to(WorkspaceState.REGISTERING, reason="Reconfiguring to Left edge")
    assert sm.desktop_generation_id == 3
    sm.transition_to(WorkspaceState.DOCKED, reason="Reconfiguration committed")
    assert sm.desktop_generation_id == 4


def test_degraded_and_token_recovery():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.DOCKED)
    sm.transition_to(WorkspaceState.DEGRADED, reason="Explorer shell restarted")
    assert sm.current_state == WorkspaceState.DEGRADED

    # Recovery without token must fail
    with pytest.raises(WorkspaceStateTransitionError, match="requires valid recovery token"):
        sm.transition_to(WorkspaceState.READY_FLOATING, reason="Attempting reset without token")

    # Recovery with valid token succeeds
    sm.transition_to(
        WorkspaceState.READY_FLOATING,
        reason="Manual operator reset",
        recovery_token="CONFIRM_RESET",
    )
    assert sm.current_state == WorkspaceState.READY_FLOATING


def test_failed_and_recovery():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.REGISTERING)
    sm.transition_to(WorkspaceState.FAILED, reason="ABM_NEW returned 0")
    assert sm.current_state == WorkspaceState.FAILED

    # Recovery with valid token
    sm.transition_to(
        WorkspaceState.READY_FLOATING,
        reason="Operator reset after failure",
        recovery_token="CONFIRM_OPERATOR_MANUAL_RESET",
    )
    assert sm.current_state == WorkspaceState.READY_FLOATING


def test_terminal_stopped_state():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    sm.transition_to(WorkspaceState.STOPPED, reason="Process shutdown")
    assert sm.current_state == WorkspaceState.STOPPED

    # Any transition out of STOPPED must fail
    with pytest.raises(WorkspaceStateTransitionError):
        sm.transition_to(WorkspaceState.READY_FLOATING)

    with pytest.raises(WorkspaceStateTransitionError):
        sm.transition_to(WorkspaceState.UNINITIALIZED)


def test_invalid_transitions():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.UNINITIALIZED)

    # Cannot jump directly from UNINITIALIZED to DOCKED
    with pytest.raises(WorkspaceStateTransitionError):
        sm.transition_to(WorkspaceState.DOCKED)

    # Cannot jump directly from UNINITIALIZED to REGISTERING
    with pytest.raises(WorkspaceStateTransitionError):
        sm.transition_to(WorkspaceState.REGISTERING)


def test_idempotent_same_state_transition():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    gen_before = sm.desktop_generation_id
    res = sm.transition_to(WorkspaceState.READY_FLOATING)
    assert res == WorkspaceState.READY_FLOATING
    assert sm.desktop_generation_id == gen_before


def test_topology_generation_increment():
    sm = WorkspaceStateManager()
    top_gen = sm.increment_topology_generation()
    assert top_gen == 2
    assert sm.topology_generation_id == 2
    assert sm.desktop_generation_id == 2


def test_listeners_notification():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    events = []

    def on_change(old_st, new_st, reason):
        events.append((old_st, new_st, reason))

    sm.add_listener(on_change)
    sm.transition_to(WorkspaceState.REGISTERING, reason="Test reason")

    assert len(events) == 1
    assert events[0] == (WorkspaceState.READY_FLOATING, WorkspaceState.REGISTERING, "Test reason")

    sm.remove_listener(on_change)
    sm.transition_to(WorkspaceState.DOCKED)
    assert len(events) == 1  # No new event after removal


def test_transition_history():
    sm = WorkspaceStateManager()
    sm.transition_to(WorkspaceState.READY_FLOATING, reason="Init")
    sm.transition_to(WorkspaceState.REGISTERING, reason="Dock request")

    history = sm.get_transition_history()
    assert len(history) == 2
    assert history[0]["from_state"] == "UNINITIALIZED"
    assert history[0]["to_state"] == "READY_FLOATING"
    assert history[1]["from_state"] == "READY_FLOATING"
    assert history[1]["to_state"] == "REGISTERING"


def test_concurrent_transition_safety():
    sm = WorkspaceStateManager(initial_state=WorkspaceState.READY_FLOATING)
    errors = []

    def worker():
        try:
            for _ in range(50):
                _ = sm.desktop_generation_id
                _ = sm.current_state
                _ = sm.can_transition_to(WorkspaceState.REGISTERING)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
