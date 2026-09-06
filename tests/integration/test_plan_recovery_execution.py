"""Integration tests for orchestrator-level plan dispatch with dynamic recovery (M1.8 Step 4)."""

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
from orbit.runtime.execution import ExecutionPolicy
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.plan_execution import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanStepExecutionStatus,
)
from orbit.runtime.planning import (
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
)
from orbit.runtime.replanning import (
    DynamicReplanner,
    ReplanReason,
)
from orbit.runtime.task_understanding import TargetReference


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
def orchestrator_env():
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

    orchestrator = OrbitOrchestrator(
        event_bus=bus,
        registry=reg,
    )

    return {
        "orchestrator": orchestrator,
        "obs": obs,
        "ptr": ptr,
        "kbd": kbd,
        "tkv": tkv,
        "wsp": wsp,
        "sft": sft,
        "event_bus": bus,
    }


@pytest.mark.asyncio
async def test_orchestrator_execute_plan_with_dynamic_recovery(orchestrator_env):
    """Orchestrator.execute_plan must automatically recover from focus loss and complete."""
    env = orchestrator_env
    obs: MockObservationAdapter = env["obs"]
    orchestrator: OrbitOrchestrator = env["orchestrator"]

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
    )
    step_locate = PlanStep(
        step_id="step_locate",
        step_index=1,
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
        description="Locate text area",
        target=TargetReference(semantic_type="text_area", identifier="Text Editor"),
        dependencies=["step_open"],
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_orch_rec",
        task_id="task_orch_rec_1",
        description="Orchestrator plan with recovery",
        status=PlanStatus.VALID,
        steps=[step_open, step_locate],
        step_dependencies={"step_open": [], "step_locate": ["step_open"]},
    )

    result = await orchestrator.execute_plan(
        plan=plan,
        session_id="sess_orch_1",
        policy=ExecutionPolicy(
            max_total_attempts=1,
            max_target_resolution_attempts=1,
            max_recovery_attempts=0,
            allow_inconclusive_as_success=True,
        ),
    )

    assert result.is_success is True
    assert result.final_status == PlanExecutionStatus.SUCCEEDED
    assert result.diagnostics.get("total_replans", 0) == 1
