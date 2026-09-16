"""Real Windows Live Execution Verification Runner for Acceptance Tests A, B, and C.

Executes autonomous natural language tasks directly against live Windows OS:
- Test A: "Open Notepad"
- Test B: "Open Notepad and type HELLO ORBIT"
- Test C: "Open Calculator"

Collects grounded forensic evidence:
- HWND and window bounds
- Process ID and executable name
- Dispatch events
- Goal verification evidence (Win32, OCR, UIA)
- Terminal task status
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time
from typing import Any, Dict

# Ensure src/ is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from orbit.adapters.factory import create_capability_registry
from orbit.config import AdapterMode, RuntimeConfig
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("LIVE_ACCEPTANCE_TESTS")


def clean_app_state():
    if sys.platform == "win32":
        import subprocess
        for img in ("notepad.exe", "CalculatorApp.exe"):
            try:
                subprocess.run(["taskkill", "/F", "/IM", img], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        time.sleep(0.5)


async def run_acceptance_tests():
    clean_app_state()
    logger.info("=================================================================")
    logger.info("ORBIT LIVE WINDOWS ACCEPTANCE TEST VERIFICATION RUNNER")
    logger.info("Platform: %s | Python: %s", sys.platform, sys.version)
    logger.info("=================================================================")

    config = RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION)
    event_bus = EventBus()
    registry = create_capability_registry(config)
    clock = SystemClock()

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
        clock=clock,
    )

    logger.info("Initializing Production Orchestrator and Capabilities...")
    await orchestrator.initialize()
    logger.info("Production Orchestrator initialized successfully.")

    results: Dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # TEST A: "Open Notepad"
    # -------------------------------------------------------------------------
    clean_app_state()
    logger.info("\n>>> STARTING ACCEPTANCE TEST A: 'Open Notepad' <<<")
    t0 = time.perf_counter()
    task_a = await orchestrator.submit_task(
        session_id="live_session_test_a",
        prompt="Open Notepad",
    )
    logger.info("Submitted Task A ID: %s", task_a.task_id)

    # Poll until terminal status
    for _ in range(120):
        t = await orchestrator.task_manager.get_task(task_a.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.25)

    final_a = await orchestrator.task_manager.get_task(task_a.task_id)
    dur_a = (time.perf_counter() - t0) * 1000.0
    rec_a = await orchestrator.history_store.get_record_by_task_id(task_a.task_id)

    results["TEST_A"] = {
        "prompt": "Open Notepad",
        "task_id": final_a.task_id if final_a else None,
        "status": final_a.status.value if final_a else "UNKNOWN",
        "duration_ms": dur_a,
        "error": final_a.error.model_dump() if final_a and final_a.error else None,
        "metadata": final_a.metadata if final_a else {},
        "history_record": rec_a.model_dump(mode="json") if rec_a else None,
    }
    logger.info(
        "TEST A COMPLETED with Status: %s in %.1f ms",
        final_a.status.value if final_a else "UNKNOWN",
        dur_a,
    )

    await asyncio.sleep(1.0)

    # -------------------------------------------------------------------------
    # TEST B: "Open Notepad and type HELLO ORBIT"
    # -------------------------------------------------------------------------
    logger.info("\n>>> STARTING ACCEPTANCE TEST B: 'Open Notepad and type HELLO ORBIT' <<<")
    t0 = time.perf_counter()
    task_b = await orchestrator.submit_task(
        session_id="live_session_test_b",
        prompt="Open Notepad and type HELLO ORBIT",
    )
    logger.info("Submitted Task B ID: %s", task_b.task_id)

    # Poll until terminal status
    for _ in range(120):
        t = await orchestrator.task_manager.get_task(task_b.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.25)

    final_b = await orchestrator.task_manager.get_task(task_b.task_id)
    dur_b = (time.perf_counter() - t0) * 1000.0
    rec_b = await orchestrator.history_store.get_record_by_task_id(task_b.task_id)

    results["TEST_B"] = {
        "prompt": "Open Notepad and type HELLO ORBIT",
        "task_id": final_b.task_id if final_b else None,
        "status": final_b.status.value if final_b else "UNKNOWN",
        "duration_ms": dur_b,
        "error": final_b.error.model_dump() if final_b and final_b.error else None,
        "metadata": final_b.metadata if final_b else {},
        "history_record": rec_b.model_dump(mode="json") if rec_b else None,
    }
    logger.info(
        "TEST B COMPLETED with Status: %s in %.1f ms",
        final_b.status.value if final_b else "UNKNOWN",
        dur_b,
    )

    await asyncio.sleep(1.0)
    clean_app_state()

    # -------------------------------------------------------------------------
    # TEST C: "Open Calculator"
    # -------------------------------------------------------------------------
    logger.info("\n>>> STARTING ACCEPTANCE TEST C: 'Open Calculator' <<<")
    t0 = time.perf_counter()
    task_c = await orchestrator.submit_task(
        session_id="live_session_test_c",
        prompt="Open Calculator",
    )
    logger.info("Submitted Task C ID: %s", task_c.task_id)

    # Poll until terminal status
    for _ in range(120):
        t = await orchestrator.task_manager.get_task(task_c.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.25)

    final_c = await orchestrator.task_manager.get_task(task_c.task_id)
    dur_c = (time.perf_counter() - t0) * 1000.0
    rec_c = await orchestrator.history_store.get_record_by_task_id(task_c.task_id)

    results["TEST_C"] = {
        "prompt": "Open Calculator",
        "task_id": final_c.task_id if final_c else None,
        "status": final_c.status.value if final_c else "UNKNOWN",
        "duration_ms": dur_c,
        "error": final_c.error.model_dump() if final_c and final_c.error else None,
        "metadata": final_c.metadata if final_c else {},
        "history_record": rec_c.model_dump(mode="json") if rec_c else None,
    }
    logger.info(
        "TEST C COMPLETED with Status: %s in %.1f ms",
        final_c.status.value if final_c else "UNKNOWN",
        dur_c,
    )

    await orchestrator.shutdown()
    await event_bus.close()

    logger.info("\n=================================================================")
    logger.info("ACCEPTANCE TEST SUMMARY:")
    for test_key, res in results.items():
        logger.info(
            "  %s ('%s'): Status = %s | Duration = %.1f ms | Error = %s",
            test_key,
            res["prompt"],
            res["status"],
            res["duration_ms"],
            res["error"]["code"] if res["error"] else "None",
        )
    logger.info("=================================================================")

    # Write output to results json file
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "acceptance_test_results.json"))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Results saved to: %s", out_path)

    return results


if __name__ == "__main__":
    asyncio.run(run_acceptance_tests())
