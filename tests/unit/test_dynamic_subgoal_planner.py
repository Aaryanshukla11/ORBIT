"""Unit tests for DynamicSubgoalPlanner (Phase 3B)."""

import pytest
from orbit.runtime.agent.progress_graph import SubgoalStatus
from orbit.runtime.cognitive.models import CurrentStateObservation
from orbit.runtime.cognitive.subgoal_planner import (
    ConditionPredicate,
    DynamicSubgoalNode,
    DynamicSubgoalPlanner,
)


def test_subgoal_dag_creation_and_dependencies():
    """Verify nodes are only schedulable once all prerequisite dependencies complete."""
    planner = DynamicSubgoalPlanner()

    n1 = planner.create_node(title="Open Paint")
    n2 = planner.create_node(title="Select Brush Tool", dependencies=[n1.node_id])
    n3 = planner.create_node(title="Draw Canvas Stroke", dependencies=[n2.node_id])

    # Initial schedulable: only n1
    sched = planner.get_schedulable_subgoals()
    assert len(sched) == 1
    assert sched[0].node_id == n1.node_id

    # Mark n1 completed -> n2 becomes schedulable
    planner.mark_completed(n1.node_id)
    sched = planner.get_schedulable_subgoals()
    assert len(sched) == 1
    assert sched[0].node_id == n2.node_id

    # Mark n2 completed -> n3 becomes schedulable
    planner.mark_completed(n2.node_id)
    sched = planner.get_schedulable_subgoals()
    assert len(sched) == 1
    assert sched[0].node_id == n3.node_id

    planner.mark_completed(n3.node_id)
    assert planner.is_all_completed() is True


def test_subgoal_precondition_evaluation():
    """Verify pre-conditions gate subgoal execution based on live observation state."""
    planner = DynamicSubgoalPlanner()

    pre = ConditionPredicate(predicate_type="WINDOW_ACTIVE", target_value="Untitled - Notepad")
    n1 = planner.create_node(title="Type Text", preconditions=[pre])

    # Observation with wrong window
    obs_wrong = CurrentStateObservation(observation_id="obs_1", active_window_title="File Explorer")
    sched = planner.get_schedulable_subgoals(observation=obs_wrong)
    assert len(sched) == 0
    assert n1.status == SubgoalStatus.BLOCKED

    # Observation with correct window
    n1.status = SubgoalStatus.PENDING
    obs_right = CurrentStateObservation(observation_id="obs_2", active_window_title="Untitled - Notepad")
    sched = planner.get_schedulable_subgoals(observation=obs_right)
    assert len(sched) == 1
    assert sched[0].node_id == n1.node_id


def test_subgoal_postcondition_verification():
    """Verify post-conditions must pass for mark_completed to succeed."""
    planner = DynamicSubgoalPlanner()

    post = ConditionPredicate(predicate_type="TEXT_OBSERVED", target_value="Hello World")
    n1 = planner.create_node(title="Type Greeting", postconditions=[post])

    # Attempt complete with missing text in OCR
    obs_empty = CurrentStateObservation(observation_id="obs_empty", ocr_tokens=["File", "Edit"])
    ok = planner.mark_completed(n1.node_id, observation=obs_empty)
    assert ok is False
    assert n1.status != SubgoalStatus.COMPLETED

    # Complete with valid text in OCR
    obs_valid = CurrentStateObservation(observation_id="obs_valid", ocr_tokens=["Hello", "World"])
    ok = planner.mark_completed(n1.node_id, observation=obs_valid)
    assert ok is True
    assert n1.status == SubgoalStatus.COMPLETED


def test_subgoal_failure_and_downstream_rollback():
    """Verify that exhausting retries blocks all downstream dependent subgoals."""
    planner = DynamicSubgoalPlanner()

    n1 = planner.create_node(title="Launch Editor", max_retries=2)
    n2 = planner.create_node(title="Write Content", dependencies=[n1.node_id])
    n3 = planner.create_node(title="Save File", dependencies=[n2.node_id])

    # Fail attempt 1 (still has retries)
    planner.mark_failed_and_rollback(n1.node_id, failure_reason="Process not found")
    assert n1.status == SubgoalStatus.READY
    assert n2.status == SubgoalStatus.PENDING

    # Fail attempt 2 (retry exhausted -> FAILED, dependents become BLOCKED)
    blocked = planner.mark_failed_and_rollback(n1.node_id, failure_reason="Process not found")
    assert n1.status == SubgoalStatus.FAILED
    assert n2.node_id in blocked
    assert n3.node_id in blocked
    assert n2.status == SubgoalStatus.BLOCKED
    assert n3.status == SubgoalStatus.BLOCKED


def test_subgoal_fallback_branch_activation():
    """Verify that failing primary branch triggers automatic fallback branch activation."""
    planner = DynamicSubgoalPlanner()

    # Main branch: GUI save
    n_main1 = planner.create_node(title="Click Save Button (GUI)", branch_id="main", max_retries=1)
    # Fallback branch: Hotkey save
    n_fall1 = planner.create_node(title="Send Hotkey Ctrl+S (Fallback)", branch_id="fallback_hotkey")

    assert planner.active_branch == "main"
    sched = planner.get_schedulable_subgoals()
    assert len(sched) == 1
    assert sched[0].node_id == n_main1.node_id

    # Fail main branch and switch to fallback_hotkey
    planner.mark_failed_and_rollback(n_main1.node_id, failure_reason="Save button hidden", fallback_branch_id="fallback_hotkey")
    assert planner.active_branch == "fallback_hotkey"

    sched = planner.get_schedulable_subgoals()
    assert len(sched) == 1
    assert sched[0].node_id == n_fall1.node_id
