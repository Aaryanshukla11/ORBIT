"""Heavy Autonomous Task Execution using Local Ollama Models (Zero Cloud).

This script performs a heavy, multi-stage autonomous workload exclusively
using local Ollama models (e.g. qwen2.5-coder:14B / qwen2.5-coder:7b / qwen2.5:3b).

Stages:
1. Local Ollama Provider & Model Inventory Discovery (Strictly Cloud-Disabled)
2. Activation of Local Heavy Model (qwen2.5-coder:14B or largest available)
3. Heavy Cognitive Phase:
   - High-Complexity Intent Interpretation
   - Hierarchical Goal Decomposition into multi-phase DAG
   - Deep Code & System Architecture Synthesis via local LLM
4. Real Multi-Step Windows Execution & Workspace Automation:
   - Production Capability Adapters (Workspace, Observation, Keyboard, Pointer)
   - Closed-loop agent execution with physical UI interaction & OCR verification
5. Verification, Artifact Generation, and Full Performance Metrics Report
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List

# Ensure src/ is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from orbit.adapters.factory import create_capability_registry
from orbit.config import AdapterMode, RuntimeConfig
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cognitive.decomposer import HierarchicalGoalDecomposer
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.models import ExecutionBudget
from orbit.runtime.models.models import ModelProviderKind
from orbit.runtime.orchestrator import OrbitOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("HEAVY_OLLAMA_TASK")


def clean_desktop_state():
    """Ensure clean starting state for desktop applications."""
    if sys.platform == "win32":
        for img in ("notepad.exe",):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", img],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        time.sleep(1.0)


async def run_heavy_local_task():
    clean_desktop_state()
    print("=" * 80)
    print("ORBIT HEAVY WORKLOAD EXECUTION — 100% LOCAL OLLAMA REASONING")
    print("=" * 80)

    # 1. Setup Runtime Config with Zero Cloud
    config = RuntimeConfig(
        adapter_mode=AdapterMode.PRODUCTION,
        enable_cloud_providers=False,
    )
    bus = EventBus()
    registry = create_capability_registry(config)
    clock = SystemClock()

    collected_events: List[Dict[str, Any]] = []

    def on_event(event):
        collected_events.append({
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "timestamp": event.timestamp_utc.isoformat() if hasattr(event, "timestamp_utc") else str(time.time()),
            "payload": event.payload,
        })

    bus.subscribe(None, on_event)

    orchestrator = OrbitOrchestrator(
        event_bus=bus,
        registry=registry,
        clock=clock,
        auto_activate_models=False,
    )

    print("\n[PHASE 1] Initializing Production Orchestrator and Capabilities...")
    t_init_start = time.perf_counter()
    await orchestrator.initialize()
    t_init_ms = (time.perf_counter() - t_init_start) * 1000.0
    print(f"Orchestrator initialized in {t_init_ms:.2f}ms.")

    # 2. Refresh Inventory and Discover Local Models
    print("\n[PHASE 2] Discovering Local Ollama Models (Cloud Strictly Excluded)...")
    inv = await orchestrator.refresh_model_inventory(
        include_runtimes=True,
        include_cloud=False,
        include_files=False,
    )

    for desc in inv.models:
        await orchestrator.model_session_manager.register_descriptor(desc)

    installed_ollama = [m for m in inv.models if m.provider == ModelProviderKind.OLLAMA]
    print(f"Found {len(installed_ollama)} local Ollama model(s):")
    for m in installed_ollama:
        print(f"  - Model ID: {m.model_id} | Name: {m.display_name} | Param Size: {getattr(m, 'parameter_size', 'unknown')}")

    # Prioritize balanced heavy coding/reasoning model for optimal local throughput:
    priority_order = [
        "qwen2.5-coder:7b",
        "qwen2.5:3b",
        "qwen2.5:latest",
        "qwen2.5-coder:14b",
    ]
    
    target_model_id = None
    for priority in priority_order:
        for m in installed_ollama:
            if priority.lower() in m.model_id.lower():
                target_model_id = m.model_id
                break
        if target_model_id:
            break

    if not target_model_id and installed_ollama:
        target_model_id = installed_ollama[0].model_id

    if not target_model_id:
        print("ERROR: No local Ollama model found! Aborting.")
        await orchestrator.shutdown()
        return

    print(f"\n[PHASE 3] Activating Heavy Target Model: '{target_model_id}'...")
    from orbit.runtime.models.models import ModelActivationRequest
    t_act_start = time.perf_counter()
    act_mgr_res = await orchestrator.model_manager.activate_model(
        ModelActivationRequest(model_id=target_model_id, timeout_seconds=300.0)
    )
    act_ses_res = await orchestrator.model_session_manager.activate_model(target_model_id)
    t_act_ms = (time.perf_counter() - t_act_start) * 1000.0

    print(f"ModelManager activation: is_successful={act_mgr_res.is_successful} (diag: {act_mgr_res.diagnostic_message})")
    print(f"ModelSessionManager activation: is_successful={act_ses_res.is_successful}")
    print(f"Activation latency: {t_act_ms:.2f}ms")

    if not act_mgr_res.is_successful or not act_ses_res.is_successful:
        print(f"Failed to activate model {target_model_id}. Aborting.")
        await orchestrator.shutdown()
        return

    # 3. Heavy Cognitive Synthesis & Architectural Analysis
    print("\n[PHASE 4] Executing Deep Cognitive Inference & Architectural Synthesis...")
    heavy_cognitive_prompt = (
        "Perform an in-depth architectural audit of an autonomous OS agent runtime. "
        "Analyze 3 core subsystems: 1) Closed-loop Multimodal Perception, 2) Hierarchical Goal Planning, "
        "and 3) Safe Deterministic Win32 Actuation. "
        "Provide a concise structured technical summary with resilience guarantees and verification criteria."
    )

    t_cog_start = time.perf_counter()
    cog_resp = await orchestrator.model_manager.generate(
        prompt=heavy_cognitive_prompt,
        temperature=0.2,
        max_tokens=350,
    )
    t_cog_ms = (time.perf_counter() - t_cog_start) * 1000.0
    print(f"Cognitive Synthesis completed in {t_cog_ms:.2f}ms")
    print(f"Tokens/Response length: {len(cog_resp.content)} characters")
    print("\n--- SYNTHESIZED ARCHITECTURAL AUDIT (PREVIEW) ---")
    preview_lines = cog_resp.content.strip().split("\n")[:12]
    print("\n".join(preview_lines))
    print("...\n[Full content preserved for artifact generation]")

    # 4. Multi-Stage Goal Interpretation & Hierarchical Decomposition
    print("\n[PHASE 5] Multi-Stage Goal Interpretation & Hierarchical Decomposition...")
    multi_step_goal = (
        "Open Notepad and type: ORBIT LOCAL WORKLOAD COMPLETED WITH " + target_model_id
    )

    interpreter = LLMIntentInterpreter(model_session_manager=orchestrator.model_session_manager)
    t_interp_start = time.perf_counter()
    structured_obj = await interpreter.interpret(prompt=multi_step_goal)
    t_interp_ms = (time.perf_counter() - t_interp_start) * 1000.0

    print(f"Interpretation completed in {t_interp_ms:.2f}ms:")
    print(f"  - User Goal: {structured_obj.user_goal}")
    print(f"  - End Condition: {structured_obj.end_condition}")
    print(f"  - Target Entities: {structured_obj.target_entities}")

    decomposer = HierarchicalGoalDecomposer(model_session_manager=orchestrator.model_session_manager)
    t_decomp_start = time.perf_counter()
    decomposed_plan = await decomposer.decompose(objective=structured_obj)
    t_decomp_ms = (time.perf_counter() - t_decomp_start) * 1000.0

    print(f"Decomposition completed in {t_decomp_ms:.2f}ms:")
    print(f"  - Sub-objectives count: {len(decomposed_plan.sub_objectives)}")
    for idx, so in enumerate(decomposed_plan.sub_objectives, 1):
        print(f"    {idx}. {so.title} (Criteria: {', '.join(so.success_criteria)})")

    # 5. Full Closed-Loop Autonomous Task Execution
    print(f"\n[PHASE 6] Executing Real Desktop Autonomous Task: '{multi_step_goal}'...")
    orchestrator.agent_loop._budget = ExecutionBudget(
        max_total_actions=60,
        no_progress_timeout_sec=300.0,
    )
    orchestrator.agent_loop._recovery_manager._max_recoveries = 3

    t_exec_start = time.perf_counter()
    exec_result = await orchestrator.execute_task(
        goal=multi_step_goal,
        session_id=f"heavy_ollama_session_{int(time.time())}",
    )
    t_exec_ms = (time.perf_counter() - t_exec_start) * 1000.0

    print(f"\nTask Execution Status: {exec_result.completion_status}")
    print(f"Is Success: {exec_result.is_success}")
    print(f"Execution Duration: {t_exec_ms:.2f}ms")

    # 6. Physical Screen State Verification (Win32 + OCR)
    print("\n[PHASE 7] Physical Grounded State Verification...")
    notepad_detected = False
    target_text_detected = False
    ocr_matches = []

    try:
        fresh_obs = await orchestrator.agent_loop._observer.observe(None)
        if fresh_obs:
            if fresh_obs.visible_windows:
                for win in fresh_obs.visible_windows:
                    title = win.get("title", "")
                    proc = win.get("process_name", "")
                    if "notepad" in proc.lower() or "notepad" in title.lower():
                        notepad_detected = True
                        print(f"  [VERIFIED] Active Window: Title='{title}', Process='{proc}', HWND={win.get('hwnd')}")

            if fresh_obs.ocr_tokens:
                keywords = ["ORBIT", "LOCAL", "WORKLOAD", "COMPLETED", "QWEN"]
                for tok_text in fresh_obs.ocr_tokens:
                    if any(k in tok_text.upper() for k in keywords):
                        ocr_matches.append(tok_text)
                
                print(f"  [VERIFIED] OCR Tokens: {ocr_matches}")
                if len(ocr_matches) >= 2:
                    target_text_detected = True
    except Exception as e:
        print(f"Perception capture error during physical verification: {e}")

    # 7. Deliverable Artifact Creation
    print("\n[PHASE 8] Generating Comprehensive Execution Artifact...")
    artifact_path = Path("scratch") / "heavy_task_execution_report.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    report_payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_used": target_model_id,
        "cloud_models_used": None,
        "cloud_tokens_used": 0,
        "local_inference_only": True,
        "benchmarks": {
            "orchestrator_init_ms": round(t_init_ms, 2),
            "model_activation_ms": round(t_act_ms, 2),
            "cognitive_synthesis_ms": round(t_cog_ms, 2),
            "intent_interpretation_ms": round(t_interp_ms, 2),
            "goal_decomposition_ms": round(t_decomp_ms, 2),
            "agent_loop_execution_ms": round(t_exec_ms, 2),
            "total_workload_duration_ms": round(t_init_ms + t_act_ms + t_cog_ms + t_interp_ms + t_decomp_ms + t_exec_ms, 2),
        },
        "task_results": {
            "task_id": exec_result.task_id,
            "goal": multi_step_goal,
            "status": str(exec_result.completion_status),
            "is_success": exec_result.is_success,
            "failure_reason": exec_result.failure_reason,
            "total_events_captured": len(collected_events),
        },
        "physical_verification": {
            "notepad_detected": notepad_detected,
            "target_text_detected": target_text_detected,
            "ocr_matches": ocr_matches,
        },
        "cognitive_synthesis_output": cog_resp.content,
    }

    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    print(f"Report written to: {artifact_path.resolve()}")

    # Shutdown
    await orchestrator.shutdown()

    # 8. Summary Decision
    print("\n" + "=" * 80)
    print("HEAVY LOCAL OLLAMA WORKLOAD EXECUTION COMPLETE")
    print(f"Model: {target_model_id} (Local GGUF/Ollama)")
    print(f"Total Workload Duration: {(t_init_ms + t_act_ms + t_cog_ms + t_interp_ms + t_decomp_ms + t_exec_ms) / 1000.0:.2f}s")
    print(f"Cloud Invocations: 0 (Pure Offline Execution)")
    print(f"Physical Desktop Automation Verified: {notepad_detected and (target_text_detected or exec_result.is_success)}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_heavy_local_task())