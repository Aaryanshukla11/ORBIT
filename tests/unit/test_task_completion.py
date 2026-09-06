"""Unit tests for TaskCompletionEngine (M1.8 Step 5)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.cancellation import CancellationSource
from orbit.runtime.plan_execution.models import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanStepExecutionResult,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanActionType
from orbit.runtime.task_completion import (
    GoalVerifier,
    TaskCompletionEngine,
    TaskCompletionStatus,
    TaskExecutionResult,
)


def _make_snapshot(text: str = "Test Output") -> ObservationSnapshot:
    win = ObservedWindow(
        hwnd=12345,
        window_title="Untitled - Notepad",
        process_name="notepad.exe",
        process_id=9999,
        extended_bounds=BoundingBox(left=100, top=100, width=800, height=600),
        is_visible=True,
        is_foreground=True,
        dpi_scaling=1.0,
    )
    el = ObservedElement(
        element_id="el_edit",
        source="accessibility",
        name=f"Text Editor: {text}",
        control_type="Edit",
        role="edit",
        bounds=BoundingBox(left=110, top=110, width=780, height=580),
    )
    return ObservationSnapshot(
        snapshot_id="snap_unit",
        generation_id=1,
        timestamp_ns=100000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=win,
        windows=[win],
        detected_elements=[el],
    )


@pytest.mark.asyncio
async def test_task_completion_engine_successful_flow():
    mock_plan_executor = MagicMock()
    mock_obs = MagicMock()

    # Setup mock observation
    snap = _make_snapshot(text="Hello ORBIT")
    mock_obs.capture_snapshot = AsyncMock(return_value=snap)
    mock_obs.capture_screen = AsyncMock(return_value=None)

    # Setup mock plan executor
    step_res = PlanStepExecutionResult(
        step_id="s1",
        step_index=0,
        action_type=PlanActionType.ENTER_TEXT,
        status=PlanStepExecutionStatus.SUCCEEDED,
    )
    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
        total_steps=1,
        completed_steps=1,
        step_results=[step_res],
    )
    mock_plan_executor.execute_plan = AsyncMock(return_value=plan_res)
    mock_plan_executor.execution_engine = MagicMock(observation=mock_obs)

    engine = TaskCompletionEngine(
        plan_executor=mock_plan_executor,
        observation=mock_obs,
    )

    result: TaskExecutionResult = await engine.execute_task(
        goal="Open Notepad and write: Hello ORBIT",
        session_id="unit_session",
    )

    assert result.completion_status == TaskCompletionStatus.COMPLETED
    assert result.is_success is True
    assert result.understanding is not None
    assert result.plan is not None
    assert result.plan_execution_result is not None
    assert result.evidence.verified_text == "Hello ORBIT"
    assert result.evidence.application_is_open is True


@pytest.mark.asyncio
async def test_task_completion_engine_unsupported_goal():
    mock_plan_executor = MagicMock()
    engine = TaskCompletionEngine(plan_executor=mock_plan_executor)

    result: TaskExecutionResult = await engine.execute_task(
        goal="Bake a chocolate cake in the kitchen",
    )

    assert result.completion_status == TaskCompletionStatus.UNSUPPORTED
    assert result.is_success is False
    assert result.failure_code == "UNSUPPORTED_TASK"
    mock_plan_executor.execute_plan.assert_not_called()


@pytest.mark.asyncio
async def test_task_completion_engine_cancelled_by_token():
    mock_plan_executor = MagicMock()
    cancel_src = CancellationSource()
    cancel_src.cancel("Operator cancelled task")

    plan_res = PlanExecutionResult(
        plan_id="p1",
        task_id="t1",
        final_status=PlanExecutionStatus.CANCELLED,
        is_success=False,
        failure_code="OPERATOR_CANCEL",
        failure_reason="Operator cancelled task",
    )
    mock_plan_executor.execute_plan = AsyncMock(return_value=plan_res)
    mock_plan_executor.execution_engine = MagicMock(observation=None)

    engine = TaskCompletionEngine(plan_executor=mock_plan_executor)

    result = await engine.execute_task(
        goal="Open Notepad and write hello",
        cancel_token=cancel_src.token,
    )

    assert result.completion_status == TaskCompletionStatus.CANCELLED
    assert result.is_success is False
