"""Production Live Windows Validation: Notepad Multi-Step Autonomous Task (Step 5).

Executes:
"Open Notepad and type ORBIT Vision Test 123"

Verifies REAL desktop closed-loop execution without mocks:
1. Live Initial Desktop Observation (Win32 + UIA + OCR + DXGI)
2. Model Decision & Routing (Vision/LLM via ModelRouter)
3. Physical Launch of Notepad (ShellExecuteW / user32)
4. Fresh Post-Action Observation & Immediate Verification (Notepad window confirmed)
5. Second Cycle Model Decision (Reasoning with fresh Notepad observation)
6. Physical Text Input via Keyboard Capability ("ORBIT Vision Test 123")
7. Fresh Post-Action Observation (OCR / UIA token verification)
8. Independent GoalVerifier Evaluation & Task Completion
9. Complete Multi-Cycle Diagnostic Trace Output
"""

import asyncio
import os
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

# Ensure src is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cognitive.agent_decision import AgentDecisionEngine
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.models import ExecutionBudget, format_cycle_trace_block
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.model_providers import CloudModelProvider, LMStudioProvider, OllamaProvider
from orbit.runtime.model_runtime.router import ModelRouter, RoutingPolicy
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models import ModelManager
from orbit.runtime.models.models import CloudProviderKind
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.task_completion.goal_verifier import GoalVerifier


async def run_real_notepad_validation():
    print("=" * 80)
    print("ORBIT STEP 5 — AUTHORITATIVE PRODUCTION CLOSED-LOOP VALIDATION: NOTEPAD")
    print("=" * 80)
    print("Prompt: 'Open Notepad and type ORBIT Vision Test 123'")
    print("Timestamp:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("-" * 80)

    # 0. Safety Pre-Cleanup: Ensure clean baseline desktop (close existing notepad if any)
    print("[SAFETY PRE-CLEANUP] Closing any existing Notepad processes for clean baseline...")
    try:
        subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
        await asyncio.sleep(0.5)
        # Clear any accumulated tab session restore files
        local_state = os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState")
        for sub_dir in ["TabState", "WindowState"]:
            p = os.path.join(local_state, sub_dir)
            if os.path.isdir(p):
                for f in os.listdir(p):
                    try:
                        os.remove(os.path.join(p, f))
                    except Exception:
                        pass
        print("[SAFETY PRE-CLEANUP] Baseline desktop and Notepad session state clean.")
    except Exception as ex:
        print(f"[SAFETY PRE-CLEANUP] Notice: {ex}")

    # 1. Initialize Real Capabilities & EventBus
    event_bus = EventBus()
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))

    # Start registered capability adapters
    await registry.initialize_all()
    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)
    pointer_cap = registry.get_optional(CapabilityType.POINTER)
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)
    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)

    # 2. Initialize Model Runtime Stack & Print Model Availability
    print("\n" + "=" * 80)
    print("A. MODEL AVAILABILITY & RUNTIME REGISTRATION AUDIT")
    print("=" * 80)
    cloud_provs = [
        CloudModelProvider(cloud_kind=CloudProviderKind.OPENAI),
        CloudModelProvider(cloud_kind=CloudProviderKind.ANTHROPIC),
        CloudModelProvider(cloud_kind=CloudProviderKind.GEMINI),
    ]
    ollama_prov = OllamaProvider()
    lmstudio_prov = LMStudioProvider()
    model_mgr = ModelManager(
        providers=[ollama_prov, lmstudio_prov],
        cloud_providers=cloud_provs,
        event_bus=event_bus,
    )
    inv = await model_mgr.refresh_inventory()
    print(f"Total Discovered Models in Inventory: {len(inv.models)}")
    for m in inv.models:
        caps_str = ", ".join(c.value for c in m.capabilities)
        prov_str = m.provider.value if hasattr(m.provider, "value") else str(m.provider)
        is_local_prov = prov_str.upper() in ("OLLAMA", "LM_STUDIO", "LOCAL_FILE") or "LOCAL" in prov_str.upper()
        prov_ep = getattr(ollama_prov, "endpoint", "N/A") if is_local_prov else "Cloud/SDK"
        print(f"  * Model ID: {m.model_id:<32} | Provider: {m.provider.value:<10} | Caps: [{caps_str}] | Endpoint: {prov_ep}")

    session_mgr = ModelSessionManager(
        registry=model_mgr.registry,
        providers=model_mgr.providers + cloud_provs,
        event_bus=event_bus,
    )
    for m in inv.models:
        await session_mgr.register_descriptor(m)

    router = ModelRouter(session_manager=session_mgr)
    decision_engine = AgentDecisionEngine(router=router, model_session_manager=session_mgr)
    perception_engine = DesktopPerceptionEngine(observation_capability=obs_cap)
    observer = CurrentStateObserver(observation=obs_cap, perception_engine=perception_engine)
    target_locator = EvidenceBasedTargetLocator()
    goal_verifier = GoalVerifier()

    # Pre-test model resolution check
    try:
        resolved_rt = await router.resolve_runtime(RoutingPolicy())
        prov_val = resolved_rt.descriptor.provider.value if hasattr(resolved_rt.descriptor.provider, "value") else str(resolved_rt.descriptor.provider)
        is_local = (
            prov_val.upper() in ("OLLAMA", "LM_STUDIO", "LOCAL_FILE")
            or "LOCAL" in prov_val.upper()
            or resolved_rt.runtime_kind.value.upper().startswith("LOCAL")
            or "127.0.0.1" in str(getattr(resolved_rt.provider, "endpoint", ""))
            or "localhost" in str(getattr(resolved_rt.provider, "endpoint", ""))
        )
        print(f"\n[MODEL ROUTER RESOLUTION]")
        print(f"  Selected Primary Runtime: {resolved_rt.model_id}")
        print(f"  Provider:                 {resolved_rt.descriptor.provider.value}")
        print(f"  Local / Cloud:            {'LOCAL' if is_local else 'CLOUD'}")
        print(f"  Endpoint:                 {getattr(resolved_rt.provider, 'endpoint', 'N/A')}")
    except Exception as r_err:
        print(f"[MODEL ROUTER RESOLUTION ERROR] {r_err}")

    # 3. Instantiate Authoritative Production AgentExecutionLoop with Strict Safety Budget
    loop = AgentExecutionLoop(
        router=router,
        model_session_manager=session_mgr,
        observer=observer,
        decision_engine=decision_engine,
        target_locator=target_locator,
        workspace=workspace_cap,
        pointer=pointer_cap,
        keyboard=keyboard_cap,
        observation=obs_cap,
        goal_verifier=goal_verifier,
        event_bus=event_bus,
        budget=ExecutionBudget(
            max_total_actions=6,
            max_repeated_actions_without_progress=2,
            max_recoveries_per_transition=2,
            no_progress_timeout_sec=90.0,
        ),
    )

    # 4. Execute Natural Language Task on Real Desktop
    print("\n" + "=" * 80)
    print("STARTING CONTROLLED CLOSED-LOOP PRODUCTION TASK EXECUTION")
    print("=" * 80)
    t_start = time.perf_counter()
    res: AgentExecutionResult = await loop.run(
        prompt="Open Notepad and type ORBIT Vision Test 123",
        task_id="real_notepad_prod_01",
    )
    t_elapsed = time.perf_counter() - t_start

    print("\n" + "=" * 80)
    print("FINAL REAL TASK EXECUTION OUTCOME REPORT")
    print("=" * 80)
    print(f"Task ID:          {res.task_id}")
    print(f"User Goal:        {res.objective.user_goal}")
    print(f"Success:          {res.is_success}")
    print(f"Final Status:     {res.final_status.value}")
    print(f"Total Steps:      {res.total_steps}")
    print(f"Elapsed Time:     {t_elapsed:.2f}s ({res.elapsed_duration_ms:.1f}ms)")
    if res.failure_reason:
        print(f"Failure Reason:   {res.failure_reason} (Code: {res.failure_code})")

    print("\n" + "-" * 80)
    print(f"CHRONOLOGICAL STATE TRANSITIONS ({len(res.state_transitions)} total):")
    print("-" * 80)
    for tr in res.state_transitions:
        print(f"  [{tr.state_before.value} -> {tr.state_after.value}] (cycle={tr.cycle_number}, obs={tr.observation_id}, dur={tr.duration_ms:.1f}ms)")

    print("\n" + "-" * 80)
    print(f"STRUCTURED CYCLE EXECUTION TRACES & AUDIT ({len(res.cycle_traces)} total):")
    print("-" * 80)
    for ct in res.cycle_traces:
        print(format_cycle_trace_block(ct))
        print("-" * 50)
        if ct.raw_model_response:
            print(f"RAW MODEL RESPONSE (Cycle {ct.cycle_number}):\n{ct.raw_model_response.strip()}")
            print("-" * 50)
        print()

    # Shutdown adapters
    await registry.shutdown_all()
    await model_mgr.shutdown()
    await session_mgr.shutdown()

    return res


if __name__ == "__main__":
    asyncio.run(run_real_notepad_validation())
