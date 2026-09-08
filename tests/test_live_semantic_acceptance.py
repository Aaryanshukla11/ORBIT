"""Live Acceptance Test Suite for ORBIT Semantic GUI Targeting.

Scenarios:
- Scenario A: "Open Calculator and click 7"
- Scenario B: "Open Calculator and click 1, then click 2"
- Scenario C: "Open Notepad and click File"
- Scenario D: "Open Calculator and click NonExistentFakeButton999" (Must truthfully fail with TARGET_NOT_FOUND)
"""

import asyncio
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("prototypes/prototype_d_observation"))

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator


async def run_live_scenarios():
    print("==================================================")
    print("STARTING ORBIT SEMANTIC TARGETING LIVE ACCEPTANCE")
    print("==================================================")

    bus = EventBus()
    obs = ProductionObservationAdapter()
    ptr = ProductionPointerAdapter()
    kbd = ProductionKeyboardAdapter()

    orchestrator = OrbitOrchestrator(
        event_bus=bus,
        observation=obs,
        pointer=ptr,
        keyboard=kbd,
    )
    await orchestrator.initialize()

    results = {}

    try:
        # Scenario A: "Open Calculator and click 7"
        print("\n--- SCENARIO A: 'Open Calculator and click 7' ---")
        t0 = time.perf_counter()
        res_a = await orchestrator.execute_task(prompt="Open Calculator and click 7")
        dur_a = time.perf_counter() - t0
        print(f"Scenario A finished in {dur_a:.2f}s | Success: {res_a.is_success} | Status: {res_a.completion_status.value}")
        results["Scenario A"] = {
            "prompt": "Open Calculator and click 7",
            "is_success": res_a.is_success,
            "status": res_a.completion_status.value,
            "failure_reason": res_a.failure_reason or (res_a.goal_verification_result.failure_reason if res_a.goal_verification_result else None),
            "duration_s": dur_a,
        }

        await asyncio.sleep(1.0)

        # Scenario B: "Open Calculator and click 1, then click 2"
        print("\n--- SCENARIO B: 'Open Calculator and click 1, then click 2' ---")
        t0 = time.perf_counter()
        res_b = await orchestrator.execute_task(prompt="Open Calculator and click 1, then click 2")
        dur_b = time.perf_counter() - t0
        print(f"Scenario B finished in {dur_b:.2f}s | Success: {res_b.is_success} | Status: {res_b.completion_status.value}")
        results["Scenario B"] = {
            "prompt": "Open Calculator and click 1, then click 2",
            "is_success": res_b.is_success,
            "status": res_b.completion_status.value,
            "failure_reason": res_b.failure_reason or (res_b.goal_verification_result.failure_reason if res_b.goal_verification_result else None),
            "duration_s": dur_b,
        }

        await asyncio.sleep(1.0)

        # Scenario C: "Open Notepad and click File"
        print("\n--- SCENARIO C: 'Open Notepad and click File' ---")
        t0 = time.perf_counter()
        res_c = await orchestrator.execute_task(prompt="Open Notepad and click File")
        dur_c = time.perf_counter() - t0
        print(f"Scenario C finished in {dur_c:.2f}s | Success: {res_c.is_success} | Status: {res_c.completion_status.value}")
        results["Scenario C"] = {
            "prompt": "Open Notepad and click File",
            "is_success": res_c.is_success,
            "status": res_c.completion_status.value,
            "failure_reason": res_c.failure_reason or (res_c.goal_verification_result.failure_reason if res_c.goal_verification_result else None),
            "duration_s": dur_c,
        }

        await asyncio.sleep(1.0)

        # Scenario D: "Open Calculator and click NonExistentFakeButton999" (Truthful failure test)
        print("\n--- SCENARIO D: 'Open Calculator and click NonExistentFakeButton999' ---")
        t0 = time.perf_counter()
        res_d = await orchestrator.execute_task(prompt="Open Calculator and click NonExistentFakeButton999")
        dur_d = time.perf_counter() - t0
        print(f"Scenario D finished in {dur_d:.2f}s | Success: {res_d.is_success} | Status: {res_d.completion_status.value}")
        results["Scenario D"] = {
            "prompt": "Open Calculator and click NonExistentFakeButton999",
            "is_success": res_d.is_success,
            "status": res_d.completion_status.value,
            "failure_reason": res_d.failure_reason or (res_d.goal_verification_result.failure_reason if res_d.goal_verification_result else None),
            "duration_s": dur_d,
        }

    finally:
        pass

    print("\n==================================================")
    print("SUMMARY OF LIVE ACCEPTANCE RESULTS")
    print("==================================================")
    for name, r in results.items():
        print(f"{name}: Success={r['is_success']}, Status={r['status']}, Reason='{r['failure_reason']}' ({r['duration_s']:.2f}s)")

    return results


if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(run_live_scenarios())
    except Exception as ex:
        print("TOP LEVEL EXCEPTION:", ex)
        traceback.print_exc()
