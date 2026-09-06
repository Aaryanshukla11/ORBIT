"""Integration tests for dynamic replanning, plan repair, and runtime recovery (M1.8 Step 4)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest
import time

from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ExecutionPolicy,
)
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.plan_execution import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanExecutor,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning import (
    DeferredGroundingRequirement,
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.replanning import (
    DynamicReplanner,
    ExecutionFailureAnalyzer,
    PlanRepairEngine,
    ReplanBudget,
    ReplanHistoryTracker,
    ReplanReason,
    ReplanStatus,
    RepairedPlanValidator,
)
from orbit.runtime.task_understanding import TargetReference, TaskConstraints
from orbit.runtime.targeting import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import TargetStrategy
from orbit.runtime.verification import ActionVerifier


def create_mock_snapshot(
    is_foreground: bool = True,
    element_name: str = "Text Editor",
    generation_id: int = 0,
) -> ObservationSnapshot:
    win_bounds = BoundingBox(left=100, top=100, width=800, height=600)
    obs_win = ObservedWindow(
        hwnd=1001,
        process_id=4560,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        extended_bounds=win_bounds,
        is_foreground=is_foreground,
        is_visible=True,
    )
    return ObservationSnapshot(
        snapshot_id=f"snap_{time.monotonic_ns()}",
        generation_id=generation_id,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=4.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        foreground_window=obs_win if is_foreground else None,
        windows=[obs_win],
        detected_elements=[
            ObservedElement(
                element_id="elem_notepad_win",
                source="UI_AUTOMATION",
                coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
                name="Untitled - Notepad",
                role="window",
                bounds=win_bounds,
                hwnd=1001,
                is_visible=True,
                is_enabled=True,
            ),
            ObservedElement(
                element_id="elem_editor",
                source="UI_AUTOMATION",
                coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
                name=element_name,
                role="edit",
                bounds=BoundingBox(left=120, top=160, width=760, height=520),
                hwnd=1001,
                is_visible=True,
                is_enabled=True,
                is_focused=is_foreground,
            ),
        ],
    )


@pytest.fixture
def replan_execution_env():
    bus = EventBus()
    obs = MockObservationAdapter()
    obs.mock_snapshot = create_mock_snapshot(is_foreground=True, generation_id=0)
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    tkv = MockHumanTakeoverAdapter()
    wsp = MockWorkspaceAdapter()
    sft = MockSafetyCoordinator()

    reg = CapabilityRegistry()
    reg.register(CapabilityType.OBSERVATION, obs)
    reg.register(CapabilityType.POINTER, ptr)
    reg.register(CapabilityType.KEYBOARD, kbd)
    reg.register(CapabilityType.HUMAN_TAKEOVER, tkv)
    reg.register(CapabilityType.WORKSPACE, wsp)
    reg.register(CapabilityType.SAFETY, sft)

    target_locator = EvidenceBasedTargetLocator()
    action_verifier = ActionVerifier()

    engine = ClosedLoopExecutionEngine(
        capability_registry=reg,
        target_locator=target_locator,
        action_verifier=action_verifier,
        event_bus=bus,
    )

    replanner = DynamicReplanner(observation=obs)
    executor = PlanExecutor(
        execution_engine=engine,
        replanner=replanner,
        event_bus=bus,
    )

    return {
        "engine": engine,
        "executor": executor,
        "replanner": replanner,
        "obs": obs,
        "ptr": ptr,
        "kbd": kbd,
        "tkv": tkv,
        "wsp": wsp,
        "sft": sft,
        "event_bus": bus,
    }


@pytest.mark.asyncio
async def test_end_to_end_replanning_on_focus_loss(replan_execution_env):
    """When a step fails due to target loss/focus loss, replanner splices recovery step, resumes and succeeds."""
    env = replan_execution_env
    obs: MockObservationAdapter = env["obs"]
    executor: PlanExecutor = env["executor"]

    # Frame 1 & 2: Step 1 (ENSURE_APPLICATION_OPEN) pre and post
    snap1_pre = create_mock_snapshot(is_foreground=True, generation_id=0)
    snap1_post = create_mock_snapshot(is_foreground=True, generation_id=0)
    # Frame 3: Step 2 (LOCATE_INPUT_SURFACE) pre encounters obscured/minimized editor
    snap2_obscured = ObservationSnapshot(
        snapshot_id=f"snap_obscured_{time.monotonic_ns()}",
        generation_id=0,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=4.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        foreground_window=None,
        windows=[],
        detected_elements=[],
    )

    obs.queue_mock_snapshot(snap1_pre)
    obs.queue_mock_snapshot(snap1_post)
    obs.queue_mock_snapshot(snap2_obscured)

    step_open = PlanStep(
        step_id="step_open",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Ensure Notepad is open",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
        dependencies=[],
    )
    step_locate = PlanStep(
        step_id="step_locate",
        step_index=1,
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
        description="Locate text editor",
        target=TargetReference(semantic_type="text_area", identifier="Text Editor"),
        dependencies=["step_open"],
    )
    step_type = PlanStep(
        step_id="step_type",
        step_index=2,
        action_type=PlanActionType.ENTER_TEXT,
        description="Type Hello World",
        constraints=TaskConstraints(content="Hello World"),
        target=TargetReference(semantic_type="ui_control", identifier="Text Editor"),
        dependencies=["step_locate"],
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_focus_recovery",
        task_id="task_rec_1",
        description="Type text in Notepad with recovery",
        status=PlanStatus.VALID,
        steps=[step_open, step_locate, step_type],
        step_dependencies={
            "step_open": [],
            "step_locate": ["step_open"],
            "step_type": ["step_locate"],
        },
    )

    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="sess_rec_1",
        task_id="task_rec_1",
        policy=ExecutionPolicy(
            max_total_attempts=1,
            max_target_resolution_attempts=1,
            max_recovery_attempts=0,
            allow_inconclusive_as_success=True,
        ),
    )

    assert result.is_success is True
    assert result.final_status == PlanExecutionStatus.SUCCEEDED
    assert result.completed_steps == 4  # step_open, spliced_focus, step_locate, step_type
    assert result.failed_steps == 0

    # Verify replan diagnostics
    assert result.diagnostics.get("total_replans", 0) == 1
    replan_history = result.diagnostics.get("replan_history", [])
    assert len(replan_history) == 1
    record = replan_history[0]
    assert record["trigger_step_id"] == "step_locate"
    assert "step_open" in record["preserved_step_ids"]


@pytest.mark.asyncio
async def test_completed_steps_are_never_reexecuted(replan_execution_env):
    """Completed steps must remain succeeded and not be re-dispatched after replan."""
    env = replan_execution_env
    obs: MockObservationAdapter = env["obs"]
    ptr: MockPointerAdapter = env["ptr"]
    executor: PlanExecutor = env["executor"]

    snap1 = create_mock_snapshot(is_foreground=True, generation_id=0)
    snap2 = create_mock_snapshot(is_foreground=False, element_name="Hidden Editor", generation_id=0)  # Causes target drop on step 2
    snap3 = create_mock_snapshot(is_foreground=True, element_name="Text Editor", generation_id=0)
    snap4 = create_mock_snapshot(is_foreground=True, element_name="Text Editor", generation_id=0)
    snap5 = create_mock_snapshot(is_foreground=True, element_name="Text Editor", generation_id=0)

    obs.queue_mock_snapshot(snap1)
    obs.queue_mock_snapshot(snap2)
    obs.queue_mock_snapshot(snap3)
    obs.queue_mock_snapshot(snap4)
    obs.queue_mock_snapshot(snap5)

    step_1 = PlanStep(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Button 1",
        target=TargetReference(semantic_type="window", identifier="Untitled - Notepad"),
        dependencies=[],
    )
    step_2 = PlanStep(
        step_id="step_2",
        step_index=1,
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
        description="Locate Editor",
        target=TargetReference(semantic_type="text_area", identifier="Text Editor"),
        dependencies=["step_1"],
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_preserve_test",
        task_id="task_preserve_1",
        description="Preserve completed steps",
        status=PlanStatus.VALID,
        steps=[step_1, step_2],
        step_dependencies={"step_1": [], "step_2": ["step_1"]},
    )

    result = await executor.execute_plan(
        plan=plan,
        session_id="sess_p1",
        policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
    )
    assert result.is_success is True

    # Check that step_1 was only executed once
    step_1_results = [r for r in result.step_results if r.step_id == "step_1"]
    assert len(step_1_results) == 1
    assert step_1_results[0].status == PlanStepExecutionStatus.SUCCEEDED
