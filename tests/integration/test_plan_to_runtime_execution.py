"""Integration tests for Plan-to-Runtime Execution Bridge (Milestone M1.8 Step 3).

Verifies:
1. End-to-end multi-step plan execution through ClosedLoopExecutionEngine.
2. Fresh observation captured per step.
3. Abstract target grounding and safe coordinate generation at runtime.
4. Correct keyboard and pointer dispatch.
5. Post-action verification and audit result integrity.
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
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.clock import SystemClock
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
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
    TaskPlanningEngine,
)
from orbit.runtime.task_understanding import (
    TargetReference,
    TaskConstraints,
    TaskUnderstandingEngine,
)
from orbit.runtime.targeting import EvidenceBasedTargetLocator
from orbit.runtime.verification import ActionVerifier


def create_notepad_mock_snapshot(typed_text: str = "") -> ObservationSnapshot:
    win_bounds = BoundingBox(left=100, top=100, width=800, height=600)
    title = f"*{typed_text} - Notepad" if typed_text else "Untitled - Notepad"
    obs_win = ObservedWindow(
        hwnd=1001,
        process_id=4560,
        process_name="notepad.exe",
        window_title=title,
        extended_bounds=win_bounds,
        is_foreground=True,
        is_visible=True,
    )
    elements = [
        ObservedElement(
            element_id="elem_notepad_win",
            source="UI_AUTOMATION",
            coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
            name=title,
            role="window",
            bounds=BoundingBox(left=100, top=100, width=800, height=600),
            hwnd=1001,
            is_visible=True,
            is_enabled=True,
        ),
        ObservedElement(
            element_id="elem_notepad_editor",
            source="UI_AUTOMATION",
            coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
            name="Text Editor",
            role="edit",
            bounds=BoundingBox(left=120, top=160, width=760, height=520),
            hwnd=1001,
            is_visible=True,
            is_enabled=True,
            is_focused=True,
            value=typed_text if typed_text else None,
        ),
        ObservedElement(
            element_id="elem_save_btn",
            source="UI_AUTOMATION",
            coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
            name="Save",
            role="push button",
            bounds=BoundingBox(left=150, top=120, width=60, height=30),
            hwnd=1001,
            is_visible=True,
            is_enabled=True,
        ),
    ]
    if typed_text:
        elements.append(
            ObservedElement(
                element_id="elem_typed_text",
                source="UI_AUTOMATION",
                coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
                name=typed_text,
                role="text",
                bounds=BoundingBox(left=120, top=160, width=200, height=20),
                hwnd=1001,
                is_visible=True,
                is_enabled=True,
            )
        )
    return ObservationSnapshot(
        snapshot_id=f"snap_notepad_{time.monotonic_ns()}",
        generation_id=0,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=4.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        foreground_window=obs_win,
        windows=[obs_win],
        detected_elements=elements,
    )


@pytest.fixture
def plan_execution_env():
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
async def test_multi_step_notepad_flow_execution(plan_execution_env):
    """Verify execution of multi-step flow: Open Notepad -> Focus -> Locate Editor -> Type Text -> Verify."""
    executor, obs, ptr, kbd, wsp, engine, reg = plan_execution_env
    await reg.initialize_all()

    # Set mock snapshot for Notepad environment
    obs.mock_snapshot = create_notepad_mock_snapshot()

    # Build multi-step plan
    step1 = PlanStep(
        step_id="step_open",
        step_index=0,
        action_type=PlanActionType.ENSURE_APPLICATION_OPEN,
        description="Ensure Notepad is open",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
        dependencies=[],
    )
    step2 = PlanStep(
        step_id="step_focus",
        step_index=1,
        action_type=PlanActionType.FOCUS_APPLICATION,
        description="Focus Notepad window",
        target=TargetReference(semantic_type="application", identifier="Notepad"),
        dependencies=["step_open"],
    )
    step3 = PlanStep(
        step_id="step_locate_editor",
        step_index=2,
        action_type=PlanActionType.LOCATE_INPUT_SURFACE,
        description="Locate editor input surface",
        target=TargetReference(semantic_type="ui_control", identifier="Text Editor", role="edit"),
        dependencies=["step_focus"],
    )
    step4 = PlanStep(
        step_id="step_type",
        step_index=3,
        action_type=PlanActionType.ENTER_TEXT,
        description="Type Hello World",
        constraints=TaskConstraints(content="Hello World"),
        target=TargetReference(semantic_type="ui_control", identifier="Text Editor", role="edit"),
        dependencies=["step_locate_editor"],
    )
    step5 = PlanStep(
        step_id="step_verify",
        step_index=4,
        action_type=PlanActionType.VERIFY_TEXT_ENTRY,
        description="Verify text entry in Notepad",
        target=TargetReference(semantic_type="ui_control", identifier="Text Editor"),
        dependencies=["step_type"],
    )

    plan = ExecutableTaskPlan(
        plan_id="plan_notepad_flow",
        task_id="task_notepad_flow",
        description="Open Notepad and type Hello World",
        status=PlanStatus.VALID,
        steps=[step1, step2, step3, step4, step5],
        step_dependencies={
            "step_open": [],
            "step_focus": ["step_open"],
            "step_locate_editor": ["step_focus"],
            "step_type": ["step_locate_editor"],
            "step_verify": ["step_type"],
        },
    )

    # Execute plan through PlanExecutor
    result: PlanExecutionResult = await executor.execute_plan(
        plan=plan,
        session_id="session_notepad_test",
        policy=ExecutionPolicy(max_total_attempts=2, allow_inconclusive_as_success=True),
    )

    assert result.is_success is True
    assert result.final_status == PlanExecutionStatus.SUCCEEDED
    assert result.completed_steps == 5
    assert result.failed_steps == 0
    assert result.blocked_steps == 0
    assert len(result.step_results) == 5

    # Verify each step reached SUCCEEDED status
    for s_res in result.step_results:
        assert s_res.status == PlanStepExecutionStatus.SUCCEEDED

    # Verify typed history received text
    assert "Hello World" in kbd.typed_history

    # Verify pointer clicks were dispatched to focused coordinates
    assert len(ptr.click_history) >= 2


@pytest.mark.asyncio
async def test_orchestrator_execute_plan_integration():
    """Verify Orchestrator.submit_task with execute_plan=True executes generated plan seamlessly."""
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

    orch = OrbitOrchestrator(
        event_bus=bus,
        registry=reg,
        clock=SystemClock(),
    )
    await orch.initialize()

    obs.mock_snapshot = create_notepad_mock_snapshot(typed_text="M1.8 Step 3 Bridge")

    # Submit task with execute_plan=True
    task = await orch.submit_task(
        session_id="sess_orch_plan_exec",
        prompt="Open Notepad and type 'M1.8 Step 3 Bridge'",
        context={"execute_plan": True, "execution_policy": {"allow_inconclusive_as_success": True}},
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED
    assert "task_understanding" in final_task.metadata
    assert "task_plan" in final_task.metadata
    assert "plan_execution_result" in final_task.metadata

    exec_res = final_task.metadata["plan_execution_result"]
    assert exec_res["is_success"] is True
    assert exec_res["final_status"] == "SUCCEEDED"

    # Verify keyboard typed text
    assert "M1.8 Step 3 Bridge" in kbd.typed_history

    await orch.shutdown()
