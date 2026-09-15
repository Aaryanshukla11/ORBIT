"""Live End-to-End Acceptance Test for Calculator Arithmetic in ORBIT V1 MVP."""

import asyncio
import sys
import logging
import subprocess
import time

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")

from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.factory import create_capability_registry
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.contracts.runtime import SystemState, TaskStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_calc_test")

async def run_task(orchestrator, prompt: str, session_id: str = "calc_session", timeout: float = 35.0):
    print("\n" + "=" * 60)
    print(f"SUBMITTING TASK: '{prompt}'")
    print("=" * 60)

    task = await orchestrator.submit_task(session_id=session_id, prompt=prompt)
    print(f"Task ID: {task.task_id}, Initial Status: {task.status.value}")

    steps_seen = []
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        await asyncio.sleep(0.5)
        t = await orchestrator._task_manager.get_task(task.task_id)
        if t:
            if t.plan and t.plan.steps:
                steps_seen = t.plan.steps
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                dur = asyncio.get_event_loop().time() - start_time
                print(f"\nTask Finished in {dur:.2f}s: Status = {t.status.value}")
                print(f"Total Steps Planned: {len(steps_seen)}")
                for i, st in enumerate(steps_seen):
                    act = getattr(st, "action_type", None) or getattr(st, "action", None)
                    act_val = getattr(act, "value", act)
                    print(f"  Step {i+1}: {act_val} -> {st.description}")
                if t.error:
                    print(f"Error Detail: [{t.error.code}] {t.error.message}")
                if t.metadata.get("task_execution_result"):
                    res = t.metadata["task_execution_result"]
                    print(f"Execution Result is_success={res.get('is_success')}, completion_status={res.get('completion_status')}")
                return t

    print(f"\nTask TIMED OUT after {timeout}s")
    return await orchestrator._task_manager.get_task(task.task_id)

async def main():
    print("=" * 70)
    print("ORBIT V1 MVP - CALCULATOR ARITHMETIC ACCEPTANCE TEST")
    print("=" * 70)

    # Clean up any stale calc
    subprocess.run(["taskkill", "/F", "/IM", "CalculatorApp.exe", "/T"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "calc.exe", "/T"], capture_output=True)
    time.sleep(1.0)

    event_bus = EventBus()
    registry = create_capability_registry()
    orchestrator = OrbitOrchestrator(event_bus=event_bus, registry=registry)
    await orchestrator.initialize()

    print(f"Orchestrator Booted. Initial State: {orchestrator.system_state.value}")

    # TEST: Open Calculator and calculate 456 × 23
    t = await run_task(orchestrator, "Open Calculator and calculate 456 × 23")
    
    print(f"\n>>> TEST RESULT: {t.status.value} <<<")
    assert t.status == TaskStatus.COMPLETED, f"Calculator arithmetic test failed: status={t.status.value}"

    await orchestrator.shutdown()
    print("ALL CHECKS PASSED.")

if __name__ == "__main__":
    asyncio.run(main())
