"""Integration tests for OrbitOrchestrator capability resolution and failure handling."""

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
from orbit.adapters.production import ProductionPointerAdapter
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_fails_honestly_when_capability_unavailable(event_bus: EventBus):
    """When a required capability (e.g. pointer) fails initialization, the task must fail honestly."""
    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    # Production pointer adapter with invalid ABI will fail initialization
    registry.register(CapabilityType.POINTER, ProductionPointerAdapter(abi_override={"platform_system": "linux"}))
    registry.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    registry.register(CapabilityType.HUMAN_TAKEOVER, MockHumanTakeoverAdapter())
    registry.register(CapabilityType.WORKSPACE, MockWorkspaceAdapter())
    registry.register(CapabilityType.SAFETY, MockSafetyCoordinator())

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    await orch.initialize()

    # Verify pointer is not ready in registry
    assert orch.registry.is_ready(CapabilityType.POINTER) is False

    task = await orch.submit_task(
        session_id="test_fail_sess",
        prompt="Perform click action",
    )

    # Wait for task completion/failure
    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.FAILED
    assert final_task.error is not None
    assert final_task.error.code == "CAPABILITY_UNAVAILABLE"
    assert "POINTER" in final_task.error.message

    await orch.shutdown()


@pytest.mark.asyncio
async def test_orchestrator_executes_successfully_with_ready_mocks(event_bus: EventBus):
    """When all capabilities are mock and ready, task executes and completes successfully."""
    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    registry.register(CapabilityType.POINTER, MockPointerAdapter())
    registry.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    registry.register(CapabilityType.HUMAN_TAKEOVER, MockHumanTakeoverAdapter())
    registry.register(CapabilityType.WORKSPACE, MockWorkspaceAdapter())
    registry.register(CapabilityType.SAFETY, MockSafetyCoordinator())

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    await orch.initialize()

    task = await orch.submit_task(
        session_id="test_success_sess",
        prompt="Run automated test task",
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED

    await orch.shutdown()
