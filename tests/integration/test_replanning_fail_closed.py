"""Integration tests for fail-closed guarantees in dynamic replanning (M1.8 Step 4)."""

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
from orbit.runtime.cancellation import CancellationSource, CancellationToken
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ExecutionPolicy,
)
from orbit.runtime.plan_execution import (
    PlanExecutionResult,
    PlanExecutionStatus,
    PlanExecutor,
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
    ReplanBudget,
    ReplanReason,
    ReplanStatus,
)
from orbit.runtime.task_understanding import TargetReference
from orbit.runtime.targeting import EvidenceBasedTargetLocator
from orbit.runtime.verification import ActionVerifier


def create_mock_snapshot(is_foreground: bool = True, generation_id: int = 0) -> ObservationSnapshot:
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
        ],
    )


@pytest.fixture
def fail_closed_env():
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

    budget = ReplanBudget(max_global_replans=2, max_step_replans=2)
    replanner = DynamicReplanner(observation=obs, budget=budget)
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
async def test_human_takeover_preempts_immediately_without_replan(fail_closed_env):
    """Human takeover must abort plan execution fail-closed with zero replan attempts."""
    env = fail_closed_env
    tkv: MockHumanTakeoverAdapter = env["tkv"]
    executor: PlanExecutor = env["executor"]
    obs: MockObservationAdapter = env["obs"]

    # Signal active takeover before plan dispatch
    tkv.trigger_takeover()
    obs.queue_mock_snapshot(create_mock_snapshot())

    step = PlanStep(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Window",
        target=TargetReference(semantic_type="window", identifier="Untitled - Notepad"),
    )
    plan = ExecutableTaskPlan(
        plan_id="plan_takeover",
        task_id="task_takeover",
        description="Takeover test",
        status=PlanStatus.VALID,
        steps=[step],
        step_dependencies={"step_1": []},
    )

    result = await executor.execute_plan(plan=plan, session_id="sess_takeover")
    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.CANCELLED
    assert result.diagnostics.get("total_replans", 0) == 0
    assert result.preemption_record is not None


@pytest.mark.asyncio
async def test_operator_cancellation_aborts_fail_closed(fail_closed_env):
    """Pre-cancelled token must abort plan execution fail-closed with zero replans."""
    env = fail_closed_env
    executor: PlanExecutor = env["executor"]

    cancel_source = CancellationSource()
    cancel_source.cancel("User cancelled operation")

    step = PlanStep(
        step_id="step_1",
        step_index=0,
        action_type=PlanActionType.ACTIVATE_CONTROL,
        description="Click Window",
        target=TargetReference(semantic_type="window", identifier="Untitled - Notepad"),
    )
    plan = ExecutableTaskPlan(
        plan_id="plan_cancel",
        task_id="task_cancel",
        description="Cancel test",
        status=PlanStatus.VALID,
        steps=[step],
        step_dependencies={"step_1": []},
    )

    result = await executor.execute_plan(
        plan=plan,
        session_id="sess_cancel",
        cancel_token=cancel_source.token,
    )
    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.CANCELLED
    assert result.diagnostics.get("total_replans", 0) == 0


@pytest.mark.asyncio
async def test_budget_exhaustion_terminates_fail_closed(fail_closed_env):
    """When a step repeatedly fails and exhausts replan budget, plan execution fails closed."""
    env = fail_closed_env
    obs: MockObservationAdapter = env["obs"]
    executor: PlanExecutor = env["executor"]

    # Always return unfocused snapshot to keep failing
    for _ in range(10):
        obs.queue_mock_snapshot(create_mock_snapshot(is_foreground=False, generation_id=0))

    step_open = PlanStep(
        step_id="step_open",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Ensure Notepad is open",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
    )
    step_fail = PlanStep(
        step_id="step_fail",
        step_index=1,
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
        description="Locate unfocused editor",
        target=TargetReference(semantic_type="text_area", identifier="Text Editor"),
        dependencies=["step_open"],
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_budget_exhaust",
        task_id="task_budget_1",
        description="Budget exhaustion test",
        status=PlanStatus.VALID,
        steps=[step_open, step_fail],
        step_dependencies={"step_open": [], "step_fail": ["step_open"]},
    )

    result = await executor.execute_plan(plan=plan, session_id="sess_b1")
    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.FAILED
    assert result.failed_steps >= 1
    # Total replan records capped at budget + exhaustion record
    assert result.diagnostics.get("total_replans", 0) <= 3
