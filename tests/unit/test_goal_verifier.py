"""Unit tests for GoalVerifier independent verification (M1.8 Step 5)."""

import pytest
from PIL import Image, ImageDraw

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.perception import SemanticPerceptionEngine
from orbit.runtime.perception.models import OCRBoundingBox, OCRResult, OCRStatus, OCRTextRegion
from orbit.runtime.plan_execution.models import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanStepExecutionResult,
    PlanStepExecutionStatus,
)
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


def _make_understanding(goal: TaskGoal, app: str, content: str = None) -> TaskUnderstandingResult:
    req = RawTaskRequest(raw_text=f"Open {app} and write {content or ''}")
    intent = StructuredTaskIntent(
        sequence_index=0,
        goal=goal,
        target=TargetReference(semantic_type="application", identifier=app),
        constraints=TaskConstraints(application_name=app, content=content),
    )
    return TaskUnderstandingResult(
        request_id=req.task_id,
        raw_request=req,
        status=TaskUnderstandingStatus.UNDERSTOOD,
        intents=[intent],
    )


def _make_plan(plan_id: str = "plan_1") -> ExecutableTaskPlan:
    step = PlanStep(
        step_id="step_1",
        action_type=PlanActionType.ENTER_TEXT,
        description="Enter text",
    )
    return ExecutableTaskPlan(
        plan_id=plan_id,
        task_id="task_1",
        description="Test plan",
        status=PlanStatus.VALID,
        steps=[step],
    )


def _make_snapshot(generation_id: int = 1, hwnd: int = 12345, title: str = "Notepad", elements=None, is_stale: bool = False, fg_override=None) -> ObservationSnapshot:
    win = ObservedWindow(
        hwnd=hwnd,
        window_title=title,
        process_name="notepad.exe",
        process_id=9999,
        extended_bounds=BoundingBox(left=100, top=100, width=800, height=600),
        is_visible=True,
        is_foreground=True,
        dpi_scaling=1.0,
    )
    fg = fg_override if fg_override is not None else win
    return ObservationSnapshot(
        snapshot_id="snap_test",
        generation_id=generation_id,
        timestamp_ns=100000,
        ttl_ms=500.0,
        is_stale=is_stale,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=fg,
        windows=[win],
        detected_elements=elements or [],
    )


@pytest.mark.asyncio
async def test_goal_verifier_cancelled_execution_returns_cancelled():
    verifier = GoalVerifier()
    und = _make_understanding(TaskGoal.WRITE_TEXT, "Notepad", "Hello")
    plan = _make_plan()
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.CANCELLED,
        is_success=False,
        failure_code="HUMAN_TAKEOVER",
        failure_reason="Preempted by user",
    )

    res = await verifier.verify_goal(
        understanding=und,
        plan=plan,
        plan_result=plan_res,
        post_snapshot=_make_snapshot(),
    )

    assert res.status == TaskCompletionStatus.CANCELLED
    assert res.is_completed is False
    assert res.failure_code == "HUMAN_TAKEOVER"


@pytest.mark.asyncio
async def test_goal_verifier_missing_snapshot_returns_unverifiable():
    verifier = GoalVerifier()
    und = _make_understanding(TaskGoal.WRITE_TEXT, "Notepad", "Hello")
    plan = _make_plan()
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
    )

    res = await verifier.verify_goal(
        understanding=und,
        plan=plan,
        plan_result=plan_res,
        post_snapshot=None,
    )

    assert res.status == TaskCompletionStatus.UNVERIFIABLE
    assert res.is_completed is False
    assert "missing post-execution observation" in res.failure_reason.lower()


@pytest.mark.asyncio
async def test_goal_verifier_blocking_dialog_returns_blocked():
    verifier = GoalVerifier()
    und = _make_understanding(TaskGoal.WRITE_TEXT, "Notepad", "Hello")
    plan = _make_plan()
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
    )

    dialog_win = ObservedWindow(
        hwnd=8888,
        window_title="Critical Error Alert Dialog",
        process_name="error.exe",
        process_id=4444,
        extended_bounds=BoundingBox(left=300, top=300, width=400, height=200),
        is_visible=True,
        is_foreground=True,
        dpi_scaling=1.0,
    )
    snap = _make_snapshot(fg_override=dialog_win)

    res = await verifier.verify_goal(
        understanding=und,
        plan=plan,
        plan_result=plan_res,
        post_snapshot=snap,
    )

    assert res.status == TaskCompletionStatus.BLOCKED
    assert res.is_completed is False
    assert "unexpected dialog/popup" in res.failure_reason.lower()


@pytest.mark.asyncio
async def test_goal_verifier_application_missing_returns_failed():
    verifier = GoalVerifier()
    und = _make_understanding(TaskGoal.WRITE_TEXT, "Notepad", "Hello")
    plan = _make_plan()
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
    )

    # Snapshot without Notepad
    calc_win = ObservedWindow(
        hwnd=7777,
        window_title="Calculator",
        process_name="calc.exe",
        process_id=2222,
        extended_bounds=BoundingBox(left=100, top=100, width=400, height=400),
        is_visible=True,
        is_foreground=True,
        dpi_scaling=1.0,
    )
    snap = ObservationSnapshot(
        snapshot_id="snap_calc",
        generation_id=1,
        timestamp_ns=100000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=calc_win,
        windows=[calc_win],
        detected_elements=[],
    )

    res = await verifier.verify_goal(
        understanding=und,
        plan=plan,
        plan_result=plan_res,
        post_snapshot=snap,
    )

    assert res.status == TaskCompletionStatus.FAILED
    assert res.is_completed is False
    assert "not present" in res.failure_reason.lower()


@pytest.mark.asyncio
async def test_goal_verifier_text_verified_via_accessibility():
    verifier = GoalVerifier()
    und = _make_understanding(TaskGoal.WRITE_TEXT, "Notepad", "ORBIT Autonomy Test Passed")
    plan = _make_plan()
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
    )

    el = ObservedElement(
        element_id="el_doc",
        source="accessibility",
        name="Text Editor: ORBIT Autonomy Test Passed",
        control_type="Edit",
        role="edit",
        bounds=BoundingBox(left=105, top=105, width=790, height=590),
    )
    snap = _make_snapshot(elements=[el])

    res = await verifier.verify_goal(
        understanding=und,
        plan=plan,
        plan_result=plan_res,
        post_snapshot=snap,
    )

    assert res.status == TaskCompletionStatus.COMPLETED
    assert res.is_completed is True
    assert res.evidence.verified_text == "ORBIT Autonomy Test Passed"
    assert "Edit:Text Editor: ORBIT Autonomy Test Passed" in res.evidence.accessibility_matched_elements


@pytest.mark.asyncio
async def test_goal_verifier_text_missing_returns_unverifiable():
    verifier = GoalVerifier()
    und = _make_understanding(TaskGoal.WRITE_TEXT, "Notepad", "Secret Payload 12345")
    plan = _make_plan()
    # Plan execution reported success (e.g. typing actions were sent)
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
    )

    # But snapshot contains blank editor without matching text
    el = ObservedElement(
        element_id="el_doc",
        source="accessibility",
        name="Text Editor",
        control_type="Edit",
        role="edit",
        bounds=BoundingBox(left=105, top=105, width=790, height=590),
    )
    snap = _make_snapshot(elements=[el])

    res = await verifier.verify_goal(
        understanding=und,
        plan=plan,
        plan_result=plan_res,
        post_snapshot=snap,
    )

    # MUST NOT EQUATE ACTION EXECUTION WITH TASK SUCCESS!
    assert res.status == TaskCompletionStatus.UNVERIFIABLE
    assert res.is_completed is False
    assert "could not be independently verified" in res.failure_reason.lower()


@pytest.mark.asyncio
async def test_goal_verifier_drawing_visual_pixel_diff():
    verifier = GoalVerifier()
    und = _make_understanding(TaskGoal.CLICK_TARGET, "Paint", "Draw Circle")
    plan = _make_plan()
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
    )

    # Initial blank canvas (white 400x400)
    pre_img = Image.new("RGB", (400, 400), (255, 255, 255))
    # Post canvas with drawn strokes (black rectangle / circle)
    post_img = Image.new("RGB", (400, 400), (255, 255, 255))
    draw = ImageDraw.Draw(post_img)
    draw.ellipse((50, 50, 350, 350), outline=(0, 0, 0), width=5)

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
        snapshot_id="snap_paint",
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

    assert res.status == TaskCompletionStatus.COMPLETED
    assert res.is_completed is True
    assert res.evidence.canvas_pixel_difference_ratio > 0.0001
