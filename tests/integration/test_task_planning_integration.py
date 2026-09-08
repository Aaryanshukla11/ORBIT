"""Integration tests for ORBIT Task Planning Subsystem with Orchestrator lifecycle (M1.8 Step 2)."""

import asyncio
import pytest
from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.planning import PlanActionType, PlanStatus
from orbit.runtime.task_understanding import TaskGoal, TaskUnderstandingStatus
from orbit.runtime.targeting.models import TargetIntent, TargetStrategy


@pytest.fixture
def orchestrator_env():
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

    return orch, obs, ptr, kbd, wsp, orch.task_manager


@pytest.mark.asyncio
async def test_orchestrator_plan_task_api(orchestrator_env):
    """Test orchestrator.plan_task() method directly."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    clicks_before = len(ptr.click_history)
    moves_before = len(ptr.move_history)
    typed_before = len(kbd.typed_history)

    plan = orch.plan_task("Open Notepad and type Hello World")
    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 6
    assert plan.steps[0].action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert plan.steps[4].action_type == PlanActionType.ENTER_TEXT
    assert plan.steps[4].constraints.content == "Hello World"

    # Assert zero OS interaction occurred during planning
    assert len(ptr.click_history) == clicks_before
    assert len(ptr.move_history) == moves_before
    assert len(kbd.typed_history) == typed_before

    await orch.shutdown()


@pytest.mark.asyncio
async def test_end_to_end_natural_language_to_plan_attaches_to_task(orchestrator_env):
    """Verify task submission runs understanding + planning, stores artifacts, and halts safely."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    clicks_before = len(ptr.click_history)
    typed_before = len(kbd.typed_history)

    task = await orch.submit_task(
        session_id="sess_plan_1",
        prompt="Open Notepad and type 'M1.8 Step 2 Plan Integration' and click Save",
        context={"plan_only": True},
    )

    for _ in range(50):
        t = await task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED

    # Verify task understanding attached
    assert "task_understanding" in final_task.metadata
    assert final_task.metadata["task_understanding"]["status"] == TaskUnderstandingStatus.UNDERSTOOD.value

    # Verify task plan attached
    assert "task_plan" in final_task.metadata
    plan_data = final_task.metadata["task_plan"]
    assert plan_data["status"] == PlanStatus.VALID.value
    assert len(plan_data["steps"]) == 9  # 2 (open) + 4 (type) + 3 (click)
    assert "explanation" in plan_data
    assert plan_data["explanation"]["total_steps"] == 9

    # Assert fail-closed safety: ZERO OS input events during planning lifecycle
    assert len(ptr.click_history) == clicks_before
    assert len(kbd.typed_history) == typed_before

    await orch.shutdown()


@pytest.mark.asyncio
async def test_ambiguous_task_planning_fails_closed(orchestrator_env):
    """Verify ambiguous prompt creates AMBIGUOUS plan and halts with zero OS actions."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    clicks_before = len(ptr.click_history)
    typed_before = len(kbd.typed_history)

    task = await orch.submit_task(
        session_id="sess_ambig_plan",
        prompt="Open it and click the button",
    )

    for _ in range(50):
        t = await task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED

    assert "task_plan" in final_task.metadata
    assert final_task.metadata["task_plan"]["status"] in {
        PlanStatus.AMBIGUOUS.value,
        PlanStatus.PARTIALLY_PLANNED.value,
    }

    assert len(ptr.click_history) == clicks_before
    assert len(kbd.typed_history) == typed_before

    await orch.shutdown()


@pytest.mark.asyncio
async def test_negation_in_orchestrator_plan_generation(orchestrator_env):
    """Verify negative constraint produces prohibited step without generating active dispatches."""
    orch, obs, ptr, kbd, wsp, task_manager = orchestrator_env
    await orch.initialize()

    plan = orch.plan_task("Open Notepad but do not save the document")
    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 3
    # Step 0: ENSURE_APPLICATION_OPEN
    # Step 1: VERIFY_APPLICATION_AVAILABLE
    # Step 2: SAVE_DOCUMENT (is_negated=True)
    assert plan.steps[2].is_negated is True
    assert "PROHIBITED" in plan.steps[2].description

    await orch.shutdown()
