"""Unit tests for 3-Level Goal Verification and Semantic Alignment."""

import pytest
from unittest.mock import MagicMock
from PIL import Image, ImageDraw

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.plan_execution.models import PlanExecutionResult, PlanExecutionStatus
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanActionType, PlanStatus, PlanStep
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import TaskCompletionStatus
from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)


@pytest.mark.asyncio
async def test_goal_verifier_rejects_cube_when_portrait_requested():
    """Level 3 Verification: Drawing strokes alone MUST NOT satisfy a portrait request."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_paint",
        active_window_title="Untitled - Paint",
        canvas_status="DRAWING_COMPLETED",
    )

    # Step history shows physical DRAW_STROKES was dispatched
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "cube"},
            )
        )
    ]

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_portrait_reject",
        objective=StructuredObjective(
            raw_prompt="Open Paint and draw a portrait of a boy",
            user_goal="Open Paint and draw a portrait of a boy",
            end_condition="canvas_has_boy_portrait",
        ),
        current_observation=obs,
        step_history=step_hist,
    )

    # MUST FAIL: primitive geometric strokes do not satisfy a boy portrait
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "Semantic Goal Verification FAILED" in " ".join(res.evidence.diagnostics.get("evidence_records", []))


@pytest.mark.asyncio
async def test_goal_verifier_accepts_cube_when_cube_requested():
    """Level 3 Verification: Geometric strokes DO satisfy a basic geometric shape request."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_paint_cube",
        active_window_title="Untitled - Paint",
        canvas_status="DRAWING_COMPLETED",
    )

    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "cube"},
            )
        )
    ]

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_cube_accept",
        objective=StructuredObjective(
            raw_prompt="Open Paint and draw a cube",
            user_goal="Open Paint and draw a cube",
            end_condition="canvas_has_cube",
        ),
        current_observation=obs,
        step_history=step_hist,
    )

    assert res.is_completed is True
    assert res.status == TaskCompletionStatus.COMPLETED


@pytest.mark.asyncio
async def test_full_verify_goal_rejects_portrait_on_pixel_changed_canvas():
    """Full verify_goal pipeline detects Level 2 pixel delta, but fails Level 3 Semantic check."""
    verifier = GoalVerifier()

    req = RawTaskRequest(raw_text="Open Paint and draw a portrait of a boy")
    intent = StructuredTaskIntent(
        sequence_index=0,
        goal=TaskGoal.DRAW,
        target=TargetReference(semantic_type="application", identifier="Paint"),
        constraints=TaskConstraints(application_name="Paint", content="portrait of a boy"),
    )
    und = TaskUnderstandingResult(
        request_id=req.task_id,
        raw_request=req,
        status=TaskUnderstandingStatus.UNDERSTOOD,
        intents=[intent],
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_draw",
        task_id="task_draw",
        description="Draw strokes",
        status=PlanStatus.VALID,
        steps=[PlanStep(step_id="s1", action_type=PlanActionType.DRAW_STROKES, description="draw")],
    )
    plan_res = PlanExecutionResult(
        plan_id="plan_draw",
        task_id="task_draw",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
    )

    # Initial blank canvas vs modified canvas (box drawn)
    pre_img = Image.new("RGB", (400, 400), (255, 255, 255))
    post_img = Image.new("RGB", (400, 400), (255, 255, 255))
    draw = ImageDraw.Draw(post_img)
    draw.rectangle((50, 50, 200, 200), outline=(0, 0, 0), width=4)

    paint_win = ObservedWindow(
        hwnd=9999,
        window_title="Untitled - Paint",
        process_name="mspaint.exe",
        process_id=3333,
        extended_bounds=BoundingBox(left=50, top=50, width=500, height=500),
        is_visible=True,
        is_foreground=True,
        dpi_scaling=1.0,
    )
    snap = ObservationSnapshot(
        snapshot_id="snap_paint_test",
        generation_id=1,
        timestamp_ns=100000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=paint_win,
        windows=[paint_win],
        detected_elements=[],
    )

    res = await verifier.verify_goal(
        understanding=und,
        plan=plan,
        plan_result=plan_res,
        post_snapshot=snap,
        pre_image=pre_img,
        post_image=post_img,
    )

    # Level 2 (pixel diff) succeeded, but Level 3 (Semantic verification) REJECTED!
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert res.failure_code == "SEMANTIC_GOAL_NOT_SATISFIED"
    assert "Level 3 Semantic Goal Verification failed" in res.failure_reason
