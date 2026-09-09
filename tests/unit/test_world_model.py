"""Unit tests for AgentWorldModel and WorldModelUpdater."""

import pytest
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
)
from orbit.runtime.cognitive.models import CurrentStateObservation
from orbit.runtime.world_model.model import AgentWorldModel, ControlSummary
from orbit.runtime.world_model.updater import WorldModelUpdater


def test_world_model_initialization():
    wm = AgentWorldModel()
    assert wm.session_id.startswith("wm_")
    assert wm.active_process_name == ""
    assert len(wm.action_history) == 0
    assert len(wm.failed_primitive_sequences) == 0


def test_update_from_observation():
    wm = AgentWorldModel()
    obs = CurrentStateObservation(
        active_process_name="notepad.exe",
        active_window_title="Untitled - Notepad",
        active_window_hwnd=12345,
    )
    updated = WorldModelUpdater.update_from_observation(wm, obs)
    assert updated.active_process_name == "notepad.exe"
    assert updated.active_window_title == "Untitled - Notepad"
    assert updated.active_window_hwnd == 12345


def test_bounded_action_history():
    wm = AgentWorldModel()
    action = AbstractAction(
        action_type=AbstractActionType.CLICK,
        parameters={"button": "left"},
        expected_effect="click button",
    )
    outcome = ActionExecutionOutcome(
        dispatch_success=True,
        expected_effect_observed=True,
        outcome_status=OutcomeStatus.EFFECT_VERIFIED,
    )

    # Record more actions than MAX_ACTION_HISTORY
    for _ in range(25):
        wm = WorldModelUpdater.record_action_outcome(wm, action, outcome)

    assert len(wm.action_history) == WorldModelUpdater.MAX_ACTION_HISTORY


def test_bounded_failed_sequences():
    wm = AgentWorldModel()
    for i in range(20):
        wm = WorldModelUpdater.record_failed_sequence(
            world_model=wm,
            sub_goal_title=f"Subgoal {i}",
            sequence=["CLICK", "TYPE_TEXT"],
            failed_at_index=1,
            action_that_failed="TYPE_TEXT",
            failure_reason="Element not focused",
            root_cause="focus_missing",
        )

    assert len(wm.failed_primitive_sequences) == WorldModelUpdater.MAX_FAILED_SEQUENCES
    assert wm.failed_primitive_sequences[-1].sub_goal_title == "Subgoal 19"


def test_record_facts():
    wm = AgentWorldModel()
    wm = WorldModelUpdater.record_fact(wm, "candidate_laptops", ["Laptop 1", "Laptop 2"])
    assert "candidate_laptops" in wm.known_information
    assert len(wm.known_information["candidate_laptops"]) == 2
