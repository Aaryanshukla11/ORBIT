import asyncio
import logging
import time
from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.mocks import (
    MockObservationAdapter,
    MockPointerAdapter,
    MockKeyboardAdapter,
    MockWorkspaceAdapter,
    MockHumanTakeoverAdapter,
    MockSafetyCoordinator,
)
from orbit.contracts.capabilities import CapabilityType
from orbit.infrastructure.clock import SystemClock
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.contracts.runtime import TaskStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

async def main():
    event_bus = EventBus()
    registry = CapabilityRegistry()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()
    tkv = MockHumanTakeoverAdapter()
    sft = MockSafetyCoordinator()

    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)
    registry.register(CapabilityType.HUMAN_TAKEOVER, tkv)
    registry.register(CapabilityType.SAFETY, sft)

    orch = OrbitOrchestrator(event_bus=event_bus, registry=registry, clock=SystemClock())
    await orch.initialize()

    t0 = time.perf_counter()
    print("Submitting task: 'Execute dev task without flag'")
    task = await orch.submit_task(
        session_id="sess_dev_reject",
        prompt="Execute dev task without flag",
    )

    for i in range(200):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            print(f"Task finished in {time.perf_counter() - t0:.3f}s with status: {t.status}, error: {t.error}")
            break
        await asyncio.sleep(0.1)
    else:
        t = await orch.task_manager.get_task(task.task_id)
        print(f"Task TIMED OUT after {time.perf_counter() - t0:.3f}s with status: {t.status}")

    await orch.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
