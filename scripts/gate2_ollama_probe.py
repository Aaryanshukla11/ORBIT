"""Gate 2: Ollama Local Model Verification Probe.

Tests:
Step 1: Check http://127.0.0.1:11434/api/tags and confirm installed model IDs.
Step 2: Real inference probe through ORBIT production ModelManager.
Step 3: Prove runtime wiring (User Goal -> LLMIntentInterpreter / Decomposer -> ModelSessionManager / ModelManager -> Ollama Provider -> Model Response -> Structured PlanDirective).
Step 4: Gate 2 decision evaluation.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request
import urllib.error

from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.models.models import ModelGenerateRequest
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.decomposer import HierarchicalGoalDecomposer


def probe_ollama_endpoint(endpoint: str = "http://127.0.0.1:11434") -> dict:
    """Step 1: Check http://127.0.0.1:11434/api/tags."""
    url = f"{endpoint}/api/tags"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            lat = (time.perf_counter() - t0) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name") or m.get("model") for m in data.get("models", [])]
            return {
                "success": True,
                "status_code": resp.status,
                "latency_ms": round(lat, 2),
                "installed_models": models,
                "raw_count": len(models),
            }
    except Exception as e:
        lat = (time.perf_counter() - t0) * 1000.0
        return {
            "success": False,
            "latency_ms": round(lat, 2),
            "error": str(e),
            "installed_models": [],
        }


async def probe_model_manager(target_model: str) -> dict:
    """Step 2: Real inference probe through ORBIT production ModelManager."""
    bus = EventBus()
    orch = OrbitOrchestrator(event_bus=bus)

    # 1. Discover models in ModelManager & ModelSessionManager
    t0 = time.perf_counter()
    inventory = await orch.refresh_model_inventory(include_runtimes=True, include_cloud=False, include_files=False)
    for desc in inventory.models:
        await orch.model_session_manager.register_descriptor(desc)
    disc_lat = (time.perf_counter() - t0) * 1000.0

    # 2. Activate target model through ModelManager and ModelSessionManager
    t1 = time.perf_counter()
    act_res = await orch.model_manager.activate_model(target_model)
    act_session_res = await orch.model_session_manager.activate_model(f"ollama:{target_model}")
    act_lat = (time.perf_counter() - t1) * 1000.0

    if not act_res.is_successful:
        return {
            "step": "activation",
            "success": False,
            "discovery_latency_ms": round(disc_lat, 2),
            "activation_latency_ms": round(act_lat, 2),
            "diagnostic": act_res.diagnostic_message,
        }

    # 3. Production ModelManager.generate probe
    t2 = time.perf_counter()
    try:
        resp = await orch.model_manager.generate(
            prompt="Reply with exactly: ORBIT_MODEL_READY",
            temperature=0.1,
            max_tokens=20,
        )
        gen_lat = (time.perf_counter() - t2) * 1000.0

        active_id = orch.model_manager.get_active_model_id()

        return {
            "step": "inference",
            "success": True,
            "discovery_latency_ms": round(disc_lat, 2),
            "activation_latency_ms": round(act_lat, 2),
            "inference_latency_ms": round(gen_lat, 2),
            "active_model_id": active_id,
            "response_content": resp.content.strip(),
            "model_id": resp.model_id,
            "total_duration_ms": resp.total_duration_ms,
            "orchestrator": orch,
        }
    except Exception as e:
        gen_lat = (time.perf_counter() - t2) * 1000.0
        return {
            "step": "inference",
            "success": False,
            "discovery_latency_ms": round(disc_lat, 2),
            "activation_latency_ms": round(act_lat, 2),
            "inference_latency_ms": round(gen_lat, 2),
            "error": str(e),
        }


async def probe_runtime_wiring(orch: OrbitOrchestrator) -> dict:
    """Step 3: Prove runtime wiring through real goal interpretation & decomposition path."""
    goal_prompt = "Open Notepad and type: ORBIT ASTRA-6 AUTONOMY TEST"

    # 1. LLM Intent Interpreter (Cognitive Layer)
    interpreter = LLMIntentInterpreter(model_session_manager=orch.model_session_manager)
    t0 = time.perf_counter()
    structured_obj = await interpreter.interpret(prompt=goal_prompt)
    interp_lat = (time.perf_counter() - t0) * 1000.0

    # 2. Hierarchical Goal Decomposer (Cognitive Layer)
    decomposer = HierarchicalGoalDecomposer(model_session_manager=orch.model_session_manager)
    t1 = time.perf_counter()
    decomposed_plan = await decomposer.decompose(objective=structured_obj)
    decomp_lat = (time.perf_counter() - t1) * 1000.0

    return {
        "success": True,
        "interpretation_latency_ms": round(interp_lat, 2),
        "decomposition_latency_ms": round(decomp_lat, 2),
        "user_goal": structured_obj.user_goal,
        "end_condition": structured_obj.end_condition,
        "target_entities": structured_obj.target_entities,
        "sub_objectives_count": len(decomposed_plan.sub_objectives),
        "sub_objectives": [
            {
                "title": so.title,
                "description": so.description,
                "target_entity": so.target_entity,
                "success_criteria": so.success_criteria,
            }
            for so in decomposed_plan.sub_objectives
        ],
        "reasoning": decomposed_plan.reasoning,
    }


async def main():
    print("==================================================================")
    print("GATE 2 — LOCAL OLLAMA VERIFICATION & RUNTIME PROBE")
    print("==================================================================")

    # STEP 1: Verify Ollama Daemon
    print("\n--- STEP 1: VERIFY OLLAMA DAEMON ---")
    step1_res = probe_ollama_endpoint()
    print(json.dumps(step1_res, indent=2))

    if not step1_res["success"] or not step1_res["installed_models"]:
        print("\nGATE 2 BLOCKED — LOCAL REASONING MODEL UNAVAILABLE")
        return

    installed = step1_res["installed_models"]
    target_model = None
    for m in installed:
        if "qwen2.5:3b" in m:
            target_model = m
            break
    if not target_model:
        for m in installed:
            if "qwen2.5" in m:
                target_model = m
                break
    if not target_model and installed:
        target_model = installed[0]

    print(f"\nSelected Target Model: {target_model}")

    # STEP 2: Real Inference Probe through ORBIT ModelManager
    print("\n--- STEP 2: REAL INFERENCE PROBE (ModelManager) ---")
    step2_res = await probe_model_manager(target_model)
    orch = step2_res.pop("orchestrator", None)
    print(json.dumps(step2_res, indent=2))

    if not step2_res.get("success"):
        print("\nGATE 2 BLOCKED — LOCAL REASONING MODEL UNAVAILABLE")
        return

    # STEP 3: Prove Runtime Wiring
    print("\n--- STEP 3: PROVE RUNTIME WIRING (Agent Loop Reasoning Path) ---")
    try:
        step3_res = await probe_runtime_wiring(orch)
        print(json.dumps(step3_res, indent=2))
    except Exception as e:
        print(f"Error in step 3 runtime wiring: {e}")
        import traceback
        traceback.print_exc()
        print("\nGATE 2 BLOCKED — LOCAL REASONING MODEL UNAVAILABLE")
        return

    # STEP 4: Decision
    print("\n==================================================================")
    print("GATE 2 VERIFIED — REAL LOCAL REASONING MODEL ONLINE")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(main())
