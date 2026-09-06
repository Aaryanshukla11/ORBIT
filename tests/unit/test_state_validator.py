"""Unit tests for Desktop State Validator (M1.8 Step 4)."""

import pytest
from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedWindow
from orbit.models.common import BoundingBox
from orbit.runtime.planning.models import PlanActionType, PlanStep
from orbit.runtime.replanning.models import ExecutionCheckpoint, ReplanReason
from orbit.runtime.replanning.state_validator import StateValidator
from orbit.runtime.task_understanding.models import TargetReference


@pytest.fixture
def validator() -> StateValidator:
    return StateValidator()


@pytest.fixture
def step() -> PlanStep:
    return PlanStep(
        step_id="step_calc",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click 5 on Calculator",
        target=TargetReference(semantic_type="application", identifier="Calculator"),
    )


def test_validate_state_generation_mismatch(validator, step):
    snap = ObservationSnapshot(
        snapshot_id="snap_1",
        timestamp_ns=1000000,
        generation_id=20,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
    )

    res = validator.validate_step_state(step, snap, expected_generation_id=19)
    assert not res.is_valid
    assert res.detected_issue == ReplanReason.STALE_GENERATION


def test_validate_state_app_missing(validator, step):
    snap = ObservationSnapshot(
        snapshot_id="snap_2",
        timestamp_ns=2000000,
        generation_id=20,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=111,
                process_id=222,
                process_name="notepad.exe",
                window_title="Untitled - Notepad",
                extended_bounds=BoundingBox(left=0, top=0, width=500, height=500),
                is_visible=True,
                is_foreground=True,
            )
        ],
    )

    res = validator.validate_step_state(step, snap, expected_generation_id=20)
    assert not res.is_valid
    assert res.detected_issue == ReplanReason.APPLICATION_NOT_AVAILABLE


def test_validate_state_window_moved(validator, step):
    chk = ExecutionCheckpoint(
        checkpoint_id="chk_calc",
        step_id="step_open",
        application_name="Calculator",
        window_rect=(100, 100, 600, 600),
    )

    snap = ObservationSnapshot(
        snapshot_id="snap_3",
        timestamp_ns=3000000,
        generation_id=20,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=222,
                process_id=333,
                process_name="CalculatorApp.exe",
                window_title="Calculator",
                extended_bounds=BoundingBox(left=300, top=300, width=500, height=500),
                is_visible=True,
                is_foreground=True,
            )
        ],
    )

    res = validator.validate_step_state(step, snap, checkpoint=chk, expected_generation_id=20)
    assert not res.is_valid
    assert res.detected_issue == ReplanReason.WINDOW_MOVED


def test_validate_state_window_resized(validator, step):
    chk = ExecutionCheckpoint(
        checkpoint_id="chk_calc",
        step_id="step_open",
        application_name="Calculator",
        window_rect=(100, 100, 600, 600),
    )

    snap = ObservationSnapshot(
        snapshot_id="snap_4",
        timestamp_ns=4000000,
        generation_id=20,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=222,
                process_id=333,
                process_name="CalculatorApp.exe",
                window_title="Calculator",
                extended_bounds=BoundingBox(left=100, top=100, width=700, height=800),
                is_visible=True,
                is_foreground=True,
            )
        ],
    )

    res = validator.validate_step_state(step, snap, checkpoint=chk, expected_generation_id=20)
    assert not res.is_valid
    assert res.detected_issue == ReplanReason.WINDOW_RESIZED
