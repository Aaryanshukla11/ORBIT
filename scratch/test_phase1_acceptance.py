import asyncio
import logging
import time

from orbit.adapters.factory import create_capability_registry
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.contracts.runtime import TaskStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("phase1_acceptance")

async def run_single_test(orc: OrbitOrchestrator, prompt: str, test_name: str, timeout_sec: float = 25.0):
    print(f"\n==================================================================")
    print(f"STARTING {test_name}: \"{prompt}\"")
    print(f"==================================================================")
    
    t_start = time.perf_counter()
    task = await orc.submit_task(session_id="acceptance_session", prompt=prompt)
    print(f"[SUBMITTED] Task ID: {task.task_id} | Initial Status: {task.status.value}")
    
    terminal_task = None
    elapsed = 0.0
    while elapsed < timeout_sec:
        await asyncio.sleep(0.5)
        elapsed = time.perf_counter() - t_start
        t = await orc.task_manager.get_task(task.task_id)
        if t and t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            terminal_task = t
            break
            
    if terminal_task is None:
        terminal_task = await orc.task_manager.get_task(task.task_id)
        print(f"[TIMEOUT] Task did not reach terminal state within {timeout_sec}s")
        
    duration_ms = (time.perf_counter() - t_start) * 1000.0
    rec = await orc.history_store.get_record(task.task_id)
    
    print(f"\n--- RESULTS FOR {test_name} ---")
    print(f"Task ID: {task.task_id}")
    print(f"Prompt: {prompt}")
    print(f"Final Status: {terminal_task.status.value if terminal_task else 'UNKNOWN'}")
    print(f"Duration: {duration_ms:.1f}ms")
    if terminal_task and terminal_task.error:
        print(f"Error Code: {terminal_task.error.code}")
        print(f"Error Message: {terminal_task.error.message}")
        
    if rec:
        print(f"Execution Record Status: {rec.status.value}")
        print(f"Steps Total: {rec.total_steps} | Steps Completed: {rec.steps_completed}")
        if rec.failure_code or rec.failure_reason:
            print(f"Record Failure Code: {rec.failure_code}")
            print(f"Record Failure Reason: {rec.failure_reason}")
            
    return terminal_task, rec

async def main():
    bus = EventBus()
    reg = create_capability_registry()
    msm = ModelSessionManager(event_bus=bus)
    orc = OrbitOrchestrator(event_bus=bus, registry=reg, model_session_manager=msm)
    
    print("Initializing ORBIT Orchestrator with Production Adapters...")
    await orc.initialize()
    print("ORBIT Orchestrator Initialized successfully.")
    
    # 1. TEST A: Open Notepad
    res_a, rec_a = await run_single_test(orc, "Open Notepad", "TEST A (Open Notepad)")
    
    await asyncio.sleep(1.0)
    
    # 2. TEST B: Open Notepad and type ORBIT TEST
    res_b, rec_b = await run_single_test(orc, "Open Notepad and type ORBIT TEST", "TEST B (Open Notepad and type ORBIT TEST)")
    
    await asyncio.sleep(1.0)
    
    # 3. TEST C: Open Paint
    res_c, rec_c = await run_single_test(orc, "Open Paint", "TEST C (Open Paint)")
    
    await asyncio.sleep(1.0)
    
    # 4. TEST D: Truthful Failure Test (Unavailable application)
    res_d, rec_d = await run_single_test(orc, "Open NonExistentFakeApp999", "TEST D (Truthful Failure Test)")
    
    await orc.shutdown()
    
    print("\n==================================================================")
    print("PHASE 1 ACCEPTANCE SUMMARY")
    print("==================================================================")
    print(f"TEST A (Open Notepad): {res_a.status.value if res_a else 'FAILED'}")
    print(f"TEST B (Open Notepad and type ORBIT TEST): {res_b.status.value if res_b else 'FAILED'}")
    print(f"TEST C (Open Paint): {res_c.status.value if res_c else 'FAILED'}")
    print(f"TEST D (Failure on Fake App): {res_d.status.value if res_d else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
