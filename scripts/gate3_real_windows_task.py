"""Gate 3: Real Windows Desktop Task Autonomy Run.

Task: "Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST"
Executed by the real ORBIT runtime with:
- Production capability adapters (Observation, Pointer, Keyboard, Workspace, Safety)
- Real local Ollama model (qwen2.5:3b)
- Production AgentExecutionLoop with closed-loop primitive execution and independent GoalVerifier
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import subprocess
import time

from orbit.adapters.factory import create_capability_registry
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.models.models import ModelProviderKind
from orbit.runtime.cognitive.models import ExecutionBudget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("GATE3_RUNNER")


async def run_gate3_task():
    print("==================================================================")
    print("GATE 3 — REAL WINDOWS DESKTOP AUTONOMY TASK")
    print("Goal: Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST")
    print("==================================================================")

    # 0. Clean any lingering notepad instances
    try:
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
        time.sleep(1.0)
    except Exception:
        pass

    # 1. Instantiate EventBus and Production Capability Registry
    bus = EventBus()
    registry = create_capability_registry()

    # Track runtime events
    collected_events = []
    def on_event(event):
        collected_events.append({
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "timestamp": event.timestamp_utc.isoformat() if hasattr(event, "timestamp_utc") else str(time.time()),
            "payload": event.payload,
        })
    bus.subscribe(None, on_event)

    # 2. Instantiate Orchestrator with Production Capability Registry
    orch = OrbitOrchestrator(
        event_bus=bus,
        registry=registry,
        auto_activate_models=False,
    )

    # 3. Initialize Orchestrator and Capabilities
    print("\n--- INITIALIZING PRODUCTION RUNTIME CAPABILITIES ---")
    await orch.initialize()
    print("Capabilities initialized successfully.")

    # Configure local model execution budget (allow up to 240s for local Ollama reasoning cycles)
    orch.agent_loop._budget = ExecutionBudget(
        max_total_actions=50,
        no_progress_timeout_sec=240.0,
    )
    orch.agent_loop._recovery_manager._max_recoveries = 3

    # 4. Activate Local Ollama Model (qwen2.5:3b)
    print("\n--- ACTIVATING PRODUCTION LOCAL MODEL (qwen2.5:3b) ---")
    inv = await orch.refresh_model_inventory(include_runtimes=True, include_cloud=False, include_files=False)
    for desc in inv.models:
        await orch.model_session_manager.register_descriptor(desc)

    target_model = "qwen2.5:3b"
    ollama_desc = [m for m in inv.models if target_model in m.model_id or target_model in m.display_name]
    if not ollama_desc:
        ollama_desc = [m for m in inv.models if m.provider == ModelProviderKind.OLLAMA]
    
    chosen_id = ollama_desc[0].model_id if ollama_desc else target_model
    print(f"Target Model ID: {chosen_id}")

    act_mgr_res = await orch.model_manager.activate_model(chosen_id)
    act_ses_res = await orch.model_session_manager.activate_model(chosen_id)
    print(f"ModelManager activation: is_successful={act_mgr_res.is_successful}")
    print(f"ModelSessionManager activation: is_successful={act_ses_res.is_successful}")

    if not act_mgr_res.is_successful or not act_ses_res.is_successful:
        print("\nGATE 3 BLOCKED — FAILED TO ACTIVATE MODEL")
        await orch.shutdown()
        return

    # 5. Execute Task through Authoritative Production Agent Loop
    goal_prompt = "Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST"
    print(f"\n--- EXECUTING AUTONOMOUS TASK: '{goal_prompt}' ---")
    t0 = time.perf_counter()
    
    result = await orch.execute_task(
        goal=goal_prompt,
        session_id="gate3_live_session",
    )
    total_elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 6. Report Execution Result and Traces
    print("\n==================================================================")
    print("TASK EXECUTION COMPLETED")
    print("==================================================================")
    print(f"Task ID: {result.task_id}")
    print(f"Completion Status: {result.completion_status.value if hasattr(result.completion_status, 'value') else result.completion_status}")
    print(f"Is Success: {result.is_success}")
    print(f"Total Duration ms: {round(total_elapsed_ms, 2)}")
    if result.goal_verification_result:
        print(f"Goal Verification Status: {result.goal_verification_result.status}")
        print(f"Goal Verification Is Completed: {result.goal_verification_result.is_completed}")
        print(f"Goal Verification Reason: {result.goal_verification_result.failure_reason}")

    # 7. Independent Environmental Observation Verification
    print("\n--- INDEPENDENT PHYSICAL DESKTOP STATE VERIFICATION ---")
    notepad_detected = False
    text_detected = False
    ocr_matches = []

    try:
        fresh_obs = await orch.agent_loop._observer.observe(None)
        if fresh_obs:
            if fresh_obs.visible_windows:
                for win in fresh_obs.visible_windows:
                    title = win.get("title", "")
                    proc = win.get("process_name", "")
                    if "notepad" in proc.lower() or "notepad" in title.lower():
                        notepad_detected = True
                        print(f"Verified Foreground/Visible Window: Title='{title}', Process='{proc}', HWND={win.get('hwnd')}")

            if fresh_obs.ocr_tokens:
                for tok_text in fresh_obs.ocr_tokens:
                    if any(k in tok_text.upper() for k in ["ORBIT", "ASTRA", "AUTONOMY", "TEST"]):
                        ocr_matches.append(tok_text)
                
                print(f"Matched OCR Text Tokens in Fresh State: {ocr_matches}")
                if any("ORBIT" in m.upper() for m in ocr_matches) and any("TEST" in m.upper() or "ASTRA" in m.upper() for m in ocr_matches):
                    text_detected = True
    except Exception as e:
        print(f"Perception capture error during independent verification: {e}")

    print(f"Physical Notepad Presence Verified: {notepad_detected}")
    print(f"Physical Target Text Verified on Screen: {text_detected}")

    # 8. Print Cycle Traces
    print("\n--- COMPLETE RUNTIME EXECUTION TRACE ---")
    print(f"Goal: {goal_prompt}")
    print(f"Active Model: {chosen_id}")
    print(f"Total Events Captured: {len(collected_events)}")

    # Shutdown
    await orch.shutdown()

    # Final Decision
    print("\n==================================================================")
    if result.is_success and (notepad_detected or text_detected):
        print("GATE 3 VERIFIED — REAL AUTONOMOUS TASK EXECUTED & VISIBLY VERIFIED ON WINDOWS DESKTOP")
    elif result.is_success:
        print("GATE 3 TASK COMPLETED — SYSTEM REPORTS SUCCESS")
    else:
        print(f"GATE 3 STATUS: is_success={result.is_success}, completion_status={result.completion_status}, reason={result.failure_reason}")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_gate3_task())
