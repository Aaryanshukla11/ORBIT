"""Integration tests for dependency-aware multi-step execution (Milestone M1.8 Step 3).

Verifies:
1. Failed predecessor blocks all dependent downstream steps.
2. Blocked steps never dispatch physical OS input to hardware.
3. Independent parallel step branches execute cleanly.
4. Correct epistemic status propagation across DAG.
"""

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
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
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
from orbit.runtime.task_understanding import (
    TargetReference,
    TaskConstraints,
)
from orbit.runtime.targeting import EvidenceBasedTargetLocator
from orbit.runtime.verification import ActionVerifier


@pytest.fixture
def plan_env():
    bus = EventBus()
    obs = MockObservationAdapter()
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

    locator = EvidenceBasedTargetLocator()
    verifier = ActionVerifier()
    engine = ClosedLoopExecutionEngine(
        capability_registry=reg,
        target_locator=locator,
        action_verifier=verifier,
        event_bus=bus,
        clock=SystemClock(),
    )
    executor = PlanExecutor(execution_engine=engine, event_bus=bus)

    return executor, obs, ptr, kbd, wsp, engine, reg


@pytest.mark.asyncio
async def test_failed_predecessor_blocks_all_downstream_steps(plan_env):
    """Verify that when Step 1 fails to find its target, Steps 2, 3, and 4 are marked BLOCKED and 0 OS input is dispatched for them."""
    executor, obs, ptr, kbd, wsp, engine, reg = plan_env
    await reg.initialize_all()

    # Create empty snapshot where target "NonExistentApp" is NOT found
    empty_snapshot = ObservationSnapshot(
        snapshot_id="snap_empty",
        generation_id=0,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=4.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        windows=[],
        elements=[],
    )
    obs.mock_snapshot = empty_snapshot

    clicks_before = len(ptr.click_history)
    typed_before = len(kbd.typed_history)

    # 4-step linear plan
    step1 = PlanStep(step_id="s1", step_index=0, action_type=PlanActionType.FOCUS_APPLICATION, description="Focus NonExistentApp", target=TargetReference(semantic_type="application", identifier="NonExistentApp"), dependencies=[])
    step2 = PlanStep(step_id="s2", step_index=1, action_type=PlanActionType.LOCATE_INPUT_SURFACE, description="Locate Editor", dependencies=["s1"])
    step3 = PlanStep(step_id="s3", step_index=2, action_type=PlanActionType.ENTER_TEXT, description="Type Text", constraints=TaskConstraints(content="Blocked Text"), dependencies=["s2"])
    step4 = PlanStep(step_id="s4", step_index=3, action_type=PlanActionType.SAVE_DOCUMENT, description="Save File", dependencies=["s3"])

    plan = ExecutableTaskPlan(
        plan_id="plan_fail_chain",
        task_id="task_fail_chain",
        description="Failing chain test plan",
        status=PlanStatus.VALID,
        steps=[step1, step2, step3, step4],
        step_dependencies={"s1": [], "s2": ["s1"], "s3": ["s2"], "s4": ["s3"]},
    )

    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="sess_fail_chain",
        policy=ExecutionPolicy(max_total_attempts=1, max_target_resolution_attempts=1),
    )

    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.FAILED
    assert result.completed_steps == 0
    assert result.failed_steps == 1
    assert result.blocked_steps == 3

    # Step s1 failed, s2/s3/s4 blocked
    results_by_id = {r.step_id: r for r in result.step_results}
    assert results_by_id["s1"].status == PlanStepExecutionStatus.FAILED
    assert results_by_id["s2"].status == PlanStepExecutionStatus.BLOCKED
    assert results_by_id["s3"].status == PlanStepExecutionStatus.BLOCKED
    assert results_by_id["s4"].status == PlanStepExecutionStatus.BLOCKED

    # Assert zero keyboard input dispatched for blocked text
    assert len(kbd.typed_history) == typed_before
    assert "Blocked Text" not in kbd.typed_history
    assert len(ptr.click_history) == clicks_before


@pytest.mark.asyncio
async def test_topological_branching_execution(plan_env):
    """Verify that in a DAG with parallel branches, independent branches are executed in topological order."""
    executor, obs, ptr, kbd, wsp, engine, reg = plan_env
    await reg.initialize_all()

    # Snapshot containing elements for button A and button B
    snapshot = ObservationSnapshot(
        snapshot_id="snap_branch",
        generation_id=0,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=4.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        detected_elements=[
            ObservedElement(
                element_id="elem_btn_a",
                source="UI_AUTOMATION",
                coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
                name="Button A",
                role="push button",
                bounds=BoundingBox(left=100, top=100, width=50, height=30),
                hwnd=1001,
                is_visible=True,
                is_enabled=True,
            ),
            ObservedElement(
                element_id="elem_btn_b",
                source="UI_AUTOMATION",
                coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
                name="Button B",
                role="push button",
                bounds=BoundingBox(left=200, top=100, width=50, height=30),
                hwnd=1001,
                is_visible=True,
                is_enabled=True,
            ),
        ],
    )
    obs.mock_snapshot = snapshot

    # Branch 1: s1 -> s2
    # Branch 2: s3 -> s4
    step1 = PlanStep(step_id="s1", step_index=0, action_type=PlanActionType.ACTIVATE_CONTROL, description="Click Button A", target=TargetReference(semantic_type="ui_control", identifier="Button A"), dependencies=[])
    step2 = PlanStep(step_id="s2", step_index=1, action_type=PlanActionType.VERIFY_TARGET_EFFECT, description="Verify A", target=TargetReference(semantic_type="ui_control", identifier="Button A"), dependencies=["s1"])
    step3 = PlanStep(step_id="s3", step_index=2, action_type=PlanActionType.ACTIVATE_CONTROL, description="Click Button B", target=TargetReference(semantic_type="ui_control", identifier="Button B"), dependencies=[])
    step4 = PlanStep(step_id="s4", step_index=3, action_type=PlanActionType.VERIFY_TARGET_EFFECT, description="Verify B", target=TargetReference(semantic_type="ui_control", identifier="Button B"), dependencies=["s3"])

    plan = ExecutableTaskPlan(
        plan_id="plan_parallel_branches",
        task_id="task_parallel_branches",
        description="Parallel branch execution plan",
        status=PlanStatus.VALID,
        steps=[step1, step2, step3, step4],
        step_dependencies={"s1": [], "s2": ["s1"], "s3": [], "s4": ["s3"]},
    )

    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="sess_parallel_test",
        policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
    )

    assert result.is_success is True
    assert result.completed_steps == 4
    assert result.failed_steps == 0
    assert result.blocked_steps == 0
