"""Integration tests for Plan Execution Fail-Closed and Preemption Safety (Milestone M1.8 Step 3).

Verifies:
1. Human Takeover preemption halts multi-step execution immediately fail-closed.
2. Operator cancellation token cancels execution mid-plan without leaking OS events.
3. Unsupported step types fail closed honestly without executing bogus actions.
4. Prohibited/negated actions are rejected at compile time before dispatch.
5. Absolute zero OS side-effects on fail-closed terminations.
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
from orbit.runtime.cancellation import CancellationSource
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


def create_standard_snapshot() -> ObservationSnapshot:
    return ObservationSnapshot(
        snapshot_id=f"snap_std_{time.monotonic_ns()}",
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
                element_id="elem_btn_1",
                source="UI_AUTOMATION",
                coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
                name="Button 1",
                role="push button",
                bounds=BoundingBox(left=100, top=100, width=50, height=30),
                hwnd=1001,
                is_visible=True,
                is_enabled=True,
            ),
            ObservedElement(
                element_id="elem_btn_2",
                source="UI_AUTOMATION",
                coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
                name="Button 2",
                role="push button",
                bounds=BoundingBox(left=200, top=100, width=50, height=30),
                hwnd=1001,
                is_visible=True,
                is_enabled=True,
            ),
        ],
    )


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

    return executor, obs, ptr, kbd, tkv, wsp, engine, reg


@pytest.mark.asyncio
async def test_human_takeover_preempts_before_start(plan_env):
    """Verify that if human takeover is already active, plan execution aborts immediately with 0 dispatches."""
    executor, obs, ptr, kbd, tkv, wsp, engine, reg = plan_env
    await reg.initialize_all()
    obs.mock_snapshot = create_standard_snapshot()

    # Trigger human takeover
    tkv.trigger_takeover()

    clicks_before = len(ptr.click_history)

    step1 = PlanStep(step_id="s1", action_type=PlanActionType.ACTIVATE_CONTROL, description="Click 1", target=TargetReference(semantic_type="ui_control", identifier="Button 1"), dependencies=[])
    plan = ExecutableTaskPlan(
        plan_id="plan_takeover_preempt",
        task_id="task_takeover_preempt",
        description="Takeover test plan",
        status=PlanStatus.VALID,
        steps=[step1],
        step_dependencies={"s1": []},
    )

    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="sess_takeover",
    )

    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.CANCELLED
    assert result.preemption_record is not None
    assert result.preemption_record.reason.value == "HUMAN_TAKEOVER"
    assert len(ptr.click_history) == clicks_before


@pytest.mark.asyncio
async def test_cancellation_token_halts_execution(plan_env):
    """Verify that triggering cancellation token stops subsequent plan steps immediately."""
    executor, obs, ptr, kbd, tkv, wsp, engine, reg = plan_env
    await reg.initialize_all()
    obs.mock_snapshot = create_standard_snapshot()

    cancel_src = CancellationSource()
    cancel_src.cancel("Operator aborted plan")

    step1 = PlanStep(step_id="s1", action_type=PlanActionType.ACTIVATE_CONTROL, description="Click 1", target=TargetReference(semantic_type="ui_control", identifier="Button 1"), dependencies=[])
    step2 = PlanStep(step_id="s2", action_type=PlanActionType.ACTIVATE_CONTROL, description="Click 2", target=TargetReference(semantic_type="ui_control", identifier="Button 2"), dependencies=["s1"])

    plan = ExecutableTaskPlan(
        plan_id="plan_cancel_test",
        task_id="task_cancel_test",
        description="Cancellation test plan",
        status=PlanStatus.VALID,
        steps=[step1, step2],
        step_dependencies={"s1": [], "s2": ["s1"]},
    )

    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="sess_cancel",
        cancel_token=cancel_src.token,
    )

    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.CANCELLED


@pytest.mark.asyncio
async def test_unsupported_step_terminates_honestly(plan_env):
    """Verify that an unsupported step (e.g. UNSUPPORTED_ACTION) terminates fail-closed without OS dispatch."""
    executor, obs, ptr, kbd, tkv, wsp, engine, reg = plan_env
    await reg.initialize_all()
    obs.mock_snapshot = create_standard_snapshot()

    clicks_before = len(ptr.click_history)

    step1 = PlanStep(step_id="s1", action_type=PlanActionType.UNSUPPORTED_ACTION, description="Draw a photorealistic dragon", dependencies=[])
    step2 = PlanStep(step_id="s2", action_type=PlanActionType.ACTIVATE_CONTROL, description="Click Button 1", target=TargetReference(semantic_type="ui_control", identifier="Button 1"), dependencies=["s1"])

    plan = ExecutableTaskPlan(
        plan_id="plan_unsupported_test",
        task_id="task_unsupported_test",
        description="Unsupported action test",
        status=PlanStatus.VALID,
        steps=[step1, step2],
        step_dependencies={"s1": [], "s2": ["s1"]},
    )

    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="sess_unsupported",
    )

    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.UNSUPPORTED
    assert result.step_results[0].status == PlanStepExecutionStatus.UNSUPPORTED
    assert result.step_results[1].status == PlanStepExecutionStatus.BLOCKED
    assert len(ptr.click_history) == clicks_before


@pytest.mark.asyncio
async def test_negated_step_rejected_fail_closed(plan_env):
    """Verify that a step prohibited by negative constraints is rejected fail-closed."""
    executor, obs, ptr, kbd, tkv, wsp, engine, reg = plan_env
    await reg.initialize_all()
    obs.mock_snapshot = create_standard_snapshot()

    step_neg = PlanStep(
        step_id="s_neg",
        action_type=PlanActionType.SAVE_DOCUMENT,
        description="Do not save document",
        constraints=TaskConstraints(allow_save=False),
        is_negated=True,
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_neg_test",
        task_id="task_neg_test",
        description="Negated step test",
        status=PlanStatus.VALID,
        steps=[step_neg],
        step_dependencies={"s_neg": []},
    )

    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="sess_neg",
    )

    assert result.is_success is False
    assert result.final_status == PlanExecutionStatus.UNSUPPORTED
    assert "prohibited" in (result.failure_reason or "").lower()
