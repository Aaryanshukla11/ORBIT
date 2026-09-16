import asyncio
import logging
from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.factory import create_capability_registry
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.model_runtime.session_manager import ModelSessionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

async def main():
    bus = EventBus()
    reg = create_capability_registry()
    msm = ModelSessionManager(event_bus=bus)
    orc = OrbitOrchestrator(event_bus=bus, registry=reg, model_session_manager=msm)
    
    await orc.initialize()
    print("Orchestrator successfully initialized.")
    
    print("--- Executing: Open Notepad ---")
    task = await orc.submit_task(session_id="test_sess", prompt="Open Notepad")
    print(f"Task submitted: {task.task_id}, status: {task.status}")
    
    # Wait for completion
    for _ in range(40):
        await asyncio.sleep(0.5)
        t = await orc.get_task(task.task_id)
        if t and t.status.value in ("COMPLETED", "FAILED", "CANCELLED"):
            print(f"Task finished with status: {t.status}")
            if t.error:
                print(f"Task error: {t.error}")
            break
            
    await orc.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
