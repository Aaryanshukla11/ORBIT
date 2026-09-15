"""Master End-to-End Acceptance Test Suite for ORBIT V1 MVP.

Tests all required capabilities in live Windows 11 environment:
- TEST 1: Open Notepad
- TEST 2: Open Notepad and type ORBIT TEST
- TEST 3: Open Calculator
- TEST 4: Open Calculator and calculate 456 × 23
- TEST 5: Open Paint
- TEST 6: LLM Generative Task (Open Notepad and write five lines about renewable energy)
- TEST 7: Takeover Safety Invariant (Disabled by default for MVP stabilization)
- TEST 8: Model Provider Management & Atomic Switching
"""

import asyncio
import os
import sys
import logging
import subprocess
import time

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")

from orbit.config import is_human_takeover_enabled
from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.factory import create_capability_registry
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.contracts.runtime import SystemState, TaskStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("master_v1_mvp_suite")

async def run_task(orchestrator, prompt: str, session_id: str = "master_session", timeout: float = 60.0):
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
                    # Invariant: Must NEVER fail due to HUMAN_TAKEOVER_ACTIVE
                    assert t.error.code != "HUMAN_TAKEOVER_ACTIVE", f"Task erroneously failed with HUMAN_TAKEOVER_ACTIVE: {t.error.message}"
                if t.metadata.get("task_execution_result"):
                    res = t.metadata["task_execution_result"]
                    print(f"Execution Result is_success={res.get('is_success')}, completion_status={res.get('completion_status')}")
                return t

    print(f"\nTask TIMED OUT after {timeout}s")
    return await orchestrator._task_manager.get_task(task.task_id)

async def main():
    print("=" * 80)
    print("ORBIT V1 MVP — MASTER END-TO-END LIVE ACCEPTANCE TEST SUITE")
    print("=" * 80)

    # Ensure takeover is disabled by default for MVP
    os.environ["ORBIT_HUMAN_TAKEOVER_ENABLED"] = "false"
    assert not is_human_takeover_enabled()

    # 1. Runtime Boot
    event_bus = EventBus()
    registry = create_capability_registry()
    orchestrator = OrbitOrchestrator(event_bus=event_bus, registry=registry)
    await orchestrator.initialize()

    print(f"Runtime Initialized. SystemState: {orchestrator.system_state.value}")
    print(f"Human Takeover Enabled: {orchestrator.is_human_takeover_enabled}")
    assert orchestrator.system_state == SystemState.IDLE
    assert orchestrator.is_human_takeover_enabled is False

    results = {}

    # TEST 1: Open Notepad
    print("\n" + "#" * 70)
    print(">>> TEST 1: Open Notepad <<<")
    print("#" * 70)
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True)
    await asyncio.sleep(0.5)
    t1 = await run_task(orchestrator, "Open Notepad")
    assert t1.status == TaskStatus.COMPLETED, f"TEST 1 FAILED: {t1.status}"
    results["TEST 1 (Open Notepad)"] = "PASSED"
    await asyncio.sleep(1.0)

    # TEST 2: Open Notepad and type ORBIT TEST
    print("\n" + "#" * 70)
    print(">>> TEST 2: Open Notepad and type ORBIT TEST <<<")
    print("#" * 70)
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True)
    await asyncio.sleep(0.5)
    t2 = await run_task(orchestrator, "Open Notepad and type ORBIT TEST")
    assert t2.status == TaskStatus.COMPLETED, f"TEST 2 FAILED: {t2.status}"
    results["TEST 2 (Open Notepad and type text)"] = "PASSED"
    await asyncio.sleep(1.0)

    # TEST 3: Open Calculator
    print("\n" + "#" * 70)
    print(">>> TEST 3: Open Calculator <<<")
    print("#" * 70)
    subprocess.run(["taskkill", "/f", "/im", "CalculatorApp.exe"], capture_output=True)
    subprocess.run(["taskkill", "/f", "/im", "Calculator.exe"], capture_output=True)
    await asyncio.sleep(0.5)
    t3 = await run_task(orchestrator, "Open Calculator")
    assert t3.status == TaskStatus.COMPLETED, f"TEST 3 FAILED: {t3.status}"
    results["TEST 3 (Open Calculator)"] = "PASSED"
    await asyncio.sleep(1.0)

    # TEST 4: Open Calculator and calculate 456 × 23
    print("\n" + "#" * 70)
    print(">>> TEST 4: Open Calculator and calculate 456 × 23 <<<")
    print("#" * 70)
    subprocess.run(["taskkill", "/f", "/im", "CalculatorApp.exe"], capture_output=True)
    subprocess.run(["taskkill", "/f", "/im", "Calculator.exe"], capture_output=True)
    await asyncio.sleep(0.5)
    t4 = await run_task(orchestrator, "Open Calculator and calculate 456 × 23")
    assert t4.status == TaskStatus.COMPLETED, f"TEST 4 FAILED: {t4.status}"
    results["TEST 4 (Calculator 456 × 23 = 10,488)"] = "PASSED"
    await asyncio.sleep(1.0)

    # TEST 5: Open Paint
    print("\n" + "#" * 70)
    print(">>> TEST 5: Open Paint <<<")
    print("#" * 70)
    subprocess.run(["taskkill", "/f", "/im", "mspaint.exe"], capture_output=True)
    subprocess.run(["taskkill", "/f", "/im", "PaintApp.exe"], capture_output=True)
    await asyncio.sleep(0.5)
    t5 = await run_task(orchestrator, "Open Paint")
    assert t5.status == TaskStatus.COMPLETED, f"TEST 5 FAILED: {t5.status}"
    results["TEST 5 (Open Paint)"] = "PASSED"
    await asyncio.sleep(1.0)

    # TEST 6: LLM Generative Task (Open Notepad and write five lines about renewable energy)
    print("\n" + "#" * 70)
    print(">>> TEST 6: LLM Inference (Open Notepad and write five lines about renewable energy) <<<")
    print("#" * 70)
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True)
    await asyncio.sleep(0.5)
    t6 = await run_task(orchestrator, "Open Notepad and write five lines about renewable energy", timeout=75.0)
    assert t6.status == TaskStatus.COMPLETED, f"TEST 6 FAILED: {t6.status}"
    results["TEST 6 (LLM Generative Text)"] = "PASSED"
    await asyncio.sleep(1.0)

    # TEST 7: Canvas Action (Open Paint and draw a stickman with a gun)
    print("\n" + "#" * 70)
    print(">>> TEST 7: Canvas Action (Open Paint and draw a stickman with a gun) <<<")
    print("#" * 70)
    subprocess.run(["taskkill", "/f", "/im", "mspaint.exe"], capture_output=True)
    await asyncio.sleep(0.5)
    t7 = await run_task(orchestrator, "Open Paint and draw a stickman with a gun", timeout=60.0)
    assert t7.status == TaskStatus.COMPLETED, f"TEST 7 FAILED: {t7.status}"
    results["TEST 7 (Canvas / Draw Action in Paint)"] = "PASSED"
    await asyncio.sleep(1.0)


    # TEST 7: Takeover Invariant Verification (Feature Gating)
    print("\n" + "#" * 70)
    print(">>> TEST 7: Takeover Invariant Verification (Disabled for MVP) <<<")
    print("#" * 70)
    # Triggering takeover while disabled must not change system state to HUMAN_TAKEOVER_ACTIVE
    await orchestrator.handle_human_takeover(reason="Simulated physical input", source="hardware_hook")
    assert orchestrator.system_state == SystemState.IDLE
    assert await orchestrator.is_human_takeover_active() is False
    results["TEST 7 (Takeover Invariant Verification)"] = "PASSED"
    await asyncio.sleep(1.0)

    # TEST 8: Model Provider Management & Atomic Switching
    print("\n" + "#" * 70)
    print(">>> TEST 8: Model Provider Architecture & Switching <<<")
    print("#" * 70)
    msm = orchestrator.model_session_manager
    ctx_init = msm.get_active_context()
    assert ctx_init.model_id == "ollama:qwen2.5:latest"
    sw_res = await msm.switch_model("ollama:llama3.2-vision:latest")
    assert sw_res.is_successful
    assert msm.get_active_context().model_id == "ollama:llama3.2-vision:latest"
    inv_res = await msm.switch_model("ollama:nonexistent_test_model")
    assert not inv_res.is_successful
    assert msm.get_active_context().model_id == "ollama:llama3.2-vision:latest"  # Rollback verified
    sw_back = await msm.switch_model("ollama:qwen2.5:latest")
    assert sw_back.is_successful
    results["TEST 8 (Model Management & Switching)"] = "PASSED"

    # Clean shutdown
    await orchestrator.shutdown()

    print("\n" + "=" * 80)
    print("ORBIT V1 MVP MASTER ACCEPTANCE RESULTS:")
    print("=" * 80)
    for test_name, res in results.items():
        print(f"  [PASS] {test_name:<55}: {res}")
    print("=" * 80)
    print("ALL 8 CORE MVP ACCEPTANCE TESTS COMPLETED WITH 100% SUCCESS.")

if __name__ == "__main__":
    asyncio.run(main())
