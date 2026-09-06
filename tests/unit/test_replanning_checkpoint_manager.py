"""Unit tests for Execution Checkpoint Manager (M1.8 Step 4)."""

import pytest
from orbit.adapters.observation.snapshot import (
    ObservationConfidence,
    ObservationSnapshot,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanActionType, PlanStatus, PlanStep
from orbit.runtime.replanning.checkpoint_manager import ExecutionCheckpointManager
from orbit.runtime.task_understanding.models import TargetReference


@pytest.fixture
def manager() -> ExecutionCheckpointManager:
    return ExecutionCheckpointManager()


@pytest.fixture
def sample_steps() -> list[PlanStep]:
    step_a = PlanStep(
        step_id="step_A",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Open Notepad",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
    )
    step_b = PlanStep(
        step_id="step_B",
        step_index=1,
        action_type=PlanActionType.FOCUS_APPLICATION,
        description="Focus Notepad",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
        dependencies=["step_A"],
    )
    step_c = PlanStep(
        step_id="step_C",
        step_index=2,
        action_type=PlanActionType.ENTER_TEXT,
        description="Type Hello",
        dependencies=["step_B"],
    )
    return [step_a, step_b, step_c]


def test_create_and_retrieve_checkpoints(manager, sample_steps):
    step_a, step_b, _ = sample_steps

    chk_a = manager.create_checkpoint(
        step=step_a,
        completed_step_ids={"step_A"},
        desktop_generation_id=1,
        application_name="Notepad",
        window_rect=(100, 100, 900, 700),
    )

    assert manager.total_checkpoints == 1
    assert manager.get_latest_checkpoint().checkpoint_id == chk_a.checkpoint_id
    assert manager.get_checkpoint_for_step("step_A").checkpoint_id == chk_a.checkpoint_id

    chk_b = manager.create_checkpoint(
        step=step_b,
        completed_step_ids={"step_A", "step_B"},
        desktop_generation_id=2,
        application_name="Notepad",
        window_rect=(100, 100, 900, 700),
    )

    assert manager.total_checkpoints == 2
    assert manager.get_latest_checkpoint().checkpoint_id == chk_b.checkpoint_id
    assert manager.get_checkpoint_for_step("step_B").checkpoint_id == chk_b.checkpoint_id


def test_find_safe_backtrack_checkpoint(manager, sample_steps):
    step_a, step_b, step_c = sample_steps

    chk_a = manager.create_checkpoint(
        step=step_a,
        completed_step_ids={"step_A"},
        desktop_generation_id=1,
        application_name="Notepad",
    )
    chk_b = manager.create_checkpoint(
        step=step_b,
        completed_step_ids={"step_A", "step_B"},
        desktop_generation_id=2,
        application_name="Notepad",
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_1",
        task_id="task_1",
        description="Test plan",
        status=PlanStatus.VALID,
        steps=sample_steps,
        step_dependencies={"step_A": [], "step_B": ["step_A"], "step_C": ["step_B"]},
    )

    # Failed step C depends on step B, so backtrack should locate checkpoint B
    target_chk = manager.find_safe_backtrack_checkpoint(step_c, plan)
    assert target_chk is not None
    assert target_chk.step_id == "step_B"
    assert target_chk.checkpoint_id == chk_b.checkpoint_id


def test_invalidate_after(manager, sample_steps):
    step_a, step_b, step_c = sample_steps

    manager.create_checkpoint(step=step_a, completed_step_ids={"step_A"})
    manager.create_checkpoint(step=step_b, completed_step_ids={"step_A", "step_B"})
    manager.create_checkpoint(step=step_c, completed_step_ids={"step_A", "step_B", "step_C"})

    assert manager.total_checkpoints == 3

    # Invalidate everything after step A
    invalidated = manager.invalidate_after("step_A")
    assert len(invalidated) == 2
    assert manager.total_checkpoints == 1
    assert manager.get_latest_checkpoint().step_id == "step_A"
    assert manager.get_checkpoint_for_step("step_B") is None


def test_is_valid_checkpoint_geometry_stability(manager, sample_steps):
    step_a, _, _ = sample_steps

    chk = manager.create_checkpoint(
        step=step_a,
        completed_step_ids={"step_A"},
        desktop_generation_id=5,
        application_name="Notepad",
        window_rect=(100, 100, 900, 700),
    )

    # Snapshot with matching window rect
    stable_snap = ObservationSnapshot(
        snapshot_id="snap_1",
        timestamp_ns=1000000,
        generation_id=5,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=1234,
                process_id=456,
                process_name="notepad.exe",
                window_title="Untitled - Notepad",
                extended_bounds=BoundingBox(left=100, top=100, width=800, height=600),
                is_visible=True,
                is_foreground=True,
            )
        ],
    )

    assert manager.is_valid_checkpoint(chk, stable_snap) is True

    # Snapshot with shifted window rect (e.g. moved)
    moved_snap = ObservationSnapshot(
        snapshot_id="snap_2",
        timestamp_ns=2000000,
        generation_id=6,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=1234,
                process_id=456,
                process_name="notepad.exe",
                window_title="Untitled - Notepad",
                extended_bounds=BoundingBox(left=200, top=200, width=800, height=600),
                is_visible=True,
                is_foreground=True,
            )
        ],
    )

    assert manager.is_valid_checkpoint(chk, moved_snap) is False
