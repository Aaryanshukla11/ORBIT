"""Unit tests for ContextCheckpoint and CheckpointManager (Phase 2G.1)."""

import pytest
from datetime import datetime, timezone
from orbit.runtime.cognitive.context_checkpoint import CheckpointManager, ContextCheckpoint
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective


def test_checkpoint_creation_and_fields():
    objective = StructuredObjective(
        raw_prompt="Open Notepad and write test report",
        user_goal="Write test report in Notepad",
        end_condition="report_saved",
        target_entities=["notepad"],
    )
    obs = CurrentStateObservation(
        active_window_title="Untitled - Notepad",
        active_window_class="Notepad",
        visible_windows=[{"title": "Untitled - Notepad"}],
    )
    mgr = CheckpointManager(max_checkpoints=5, checkpoint_interval_steps=3)

    chk = mgr.create_checkpoint(
        step_index=3,
        objective=objective,
        observation=obs,
        accumulated_summary="Launched Notepad and focused editor",
        recent_actions_summary="Dispatched LAUNCH_APPLICATION -> Verified",
        key_facts={"target_file": "report.txt"},
        milestone_id="m1_launch",
        milestone_name="Launch Notepad",
        is_milestone_boundary=True,
    )

    assert chk.checkpoint_id.startswith("chk_")
    assert chk.step_index == 3
    assert chk.milestone_id == "m1_launch"
    assert chk.is_milestone_boundary is True
    assert chk.active_window_title == "Untitled - Notepad"
    assert chk.key_facts["target_file"] == "report.txt"
    assert mgr.checkpoint_count == 1


def test_checkpoint_cadence_and_ring_buffer():
    mgr = CheckpointManager(max_checkpoints=3, checkpoint_interval_steps=2)
    objective = StructuredObjective(
        raw_prompt="Multi-step test",
        user_goal="Execute multi-step task",
        end_condition="completed",
    )

    assert mgr.should_checkpoint(0) is False
    assert mgr.should_checkpoint(1) is False
    assert mgr.should_checkpoint(2) is True  # 2 - (-1) >= 2

    # Create 4 checkpoints, exceeding buffer of 3
    for step in [2, 4, 6, 8]:
        mgr.create_checkpoint(step_index=step, objective=objective)

    assert mgr.checkpoint_count == 3
    checkpoints = mgr.list_checkpoints()
    assert [c.step_index for c in checkpoints] == [4, 6, 8]
    assert mgr.get_latest_checkpoint().step_index == 8


def test_milestone_retrieval_and_clear():
    mgr = CheckpointManager(max_checkpoints=5)
    objective = StructuredObjective(
        raw_prompt="Goal",
        user_goal="Execute subgoals",
        end_condition="done",
    )

    mgr.create_checkpoint(step_index=1, objective=objective, milestone_id="ms_init")
    mgr.create_checkpoint(step_index=5, objective=objective, milestone_id="ms_edit")

    chk_init = mgr.get_checkpoint_by_milestone("ms_init")
    assert chk_init is not None
    assert chk_init.step_index == 1

    chk_edit = mgr.get_checkpoint_by_milestone("ms_edit")
    assert chk_edit is not None
    assert chk_edit.step_index == 5

    mgr.clear()
    assert mgr.checkpoint_count == 0
    assert mgr.get_latest_checkpoint() is None
