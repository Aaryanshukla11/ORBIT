import asyncio
import sys
import logging

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")

from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.factory import create_capability_registry
from orbit.runtime.orchestrator import OrbitOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_notepad_test")

async def main():
    print("=" * 60)
    print("ORBIT P1 ACCEPTANCE TEST: 'Open Notepad'")
    print("=" * 60)

    event_bus = EventBus()
    registry = create_capability_registry()
    orchestrator = OrbitOrchestrator(event_bus=event_bus, registry=registry)
    await orchestrator.initialize()

    print(f"Orchestrator initialized. System State: {orchestrator.system_state.value}")

    print("\n--- Submitting Task: 'Open Notepad' ---")
    task = await orchestrator.submit_task(
        session_id="live_session",
        prompt="Open Notepad",
    )
    print(f"Submitted Task ID: {task.task_id}, Initial Status: {task.status.value}")

    for i in range(40):
        await asyncio.sleep(0.5)
        t = await orchestrator._task_manager.get_task(task.task_id)
        if t and t.status.value in ("completed", "failed", "cancelled"):
            print(f"\nTask Finished after {(i+1)*0.5:.1f}s: Status = {t.status.value}")
            if t.error:
                print(f"Error: [{t.error.code}] {t.error.message}")
            if t.metadata.get("task_execution_result"):
                res = t.metadata["task_execution_result"]
                print(f"Execution Result: is_success={res.get('is_success')}, status={res.get('completion_status')}")
                print(f"Total Steps: {res.get('total_steps')}, Verification: {res.get('verification_result')}")
                if res.get("failure_reason"):
                    print(f"Failure Reason: {res.get('failure_reason')}")
            break

    await orchestrator.shutdown()
    print("Test Completed.")

if __name__ == "__main__":
    asyncio.run(main())
