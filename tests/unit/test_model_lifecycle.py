"""Unit tests for Model Lifecycle and State Transition Engine (Milestone M1.9 Step 2)."""

import pytest

from orbit.runtime.models.lifecycle import (
    InvalidStateTransitionError,
    ModelLifecycleManager,
)
from orbit.runtime.models.models import ModelStatus


def test_initial_state_and_recording():
    mgr = ModelLifecycleManager()
    assert mgr.get_current_status("model-1") is None

    mgr.record_transition("model-1", ModelStatus.DISCOVERED, reason="Initial discovery")
    assert mgr.get_current_status("model-1") == ModelStatus.DISCOVERED

    history = mgr.get_history("model-1")
    assert len(history) == 1
    assert history[0].from_status is None
    assert history[0].to_status == ModelStatus.DISCOVERED


def test_valid_lifecycle_transitions():
    mgr = ModelLifecycleManager()
    mgr.record_transition("model-1", ModelStatus.DISCOVERED)

    # DISCOVERED -> INSTALLING -> INSTALLED -> AVAILABLE -> ACTIVE -> AVAILABLE
    mgr.transition("model-1", ModelStatus.INSTALLING, reason="Download start")
    assert mgr.get_current_status("model-1") == ModelStatus.INSTALLING

    mgr.transition("model-1", ModelStatus.INSTALLED, reason="Download finish")
    assert mgr.get_current_status("model-1") == ModelStatus.INSTALLED

    mgr.transition("model-1", ModelStatus.AVAILABLE, reason="Ready in registry")
    assert mgr.get_current_status("model-1") == ModelStatus.AVAILABLE

    mgr.transition("model-1", ModelStatus.ACTIVE, reason="Selected by user")
    assert mgr.get_current_status("model-1") == ModelStatus.ACTIVE

    mgr.transition("model-1", ModelStatus.AVAILABLE, reason="Deselected")
    assert mgr.get_current_status("model-1") == ModelStatus.AVAILABLE

    history = mgr.get_history("model-1")
    assert len(history) == 6


def test_invalid_lifecycle_transition_rejected():
    mgr = ModelLifecycleManager()
    mgr.record_transition("model-1", ModelStatus.UNAVAILABLE)

    # UNAVAILABLE -> ACTIVE is strictly forbidden without intermediate steps
    assert not mgr.can_transition(ModelStatus.UNAVAILABLE, ModelStatus.ACTIVE)

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        mgr.transition("model-1", ModelStatus.ACTIVE, reason="Attempt illegal jump")

    assert "Illegal state transition" in str(exc_info.value)
    assert mgr.get_current_status("model-1") == ModelStatus.UNAVAILABLE


def test_incompatible_cannot_transition_to_active():
    mgr = ModelLifecycleManager()
    mgr.record_transition("model-1", ModelStatus.INCOMPATIBLE)

    assert not mgr.can_transition(ModelStatus.INCOMPATIBLE, ModelStatus.ACTIVE)
    with pytest.raises(InvalidStateTransitionError):
        mgr.transition("model-1", ModelStatus.ACTIVE)


def test_failed_cannot_transition_to_active_without_retry():
    mgr = ModelLifecycleManager()
    mgr.record_transition("model-1", ModelStatus.FAILED)

    # Can retry via INSTALLING or DISCOVERED, but cannot jump to ACTIVE
    assert mgr.can_transition(ModelStatus.FAILED, ModelStatus.INSTALLING)
    assert mgr.can_transition(ModelStatus.FAILED, ModelStatus.DISCOVERED)
    assert not mgr.can_transition(ModelStatus.FAILED, ModelStatus.ACTIVE)

    with pytest.raises(InvalidStateTransitionError):
        mgr.transition("model-1", ModelStatus.ACTIVE)
