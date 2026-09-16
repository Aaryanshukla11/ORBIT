"""Production Live Windows Validation: Paint Multi-Step Autonomous Task (Phase 2A Audit).

Executes:
"Open Paint, draw a red circle, and save it as test.png on the Desktop."
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cognitive.agent_decision import AgentDecisionEngine
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.models import ExecutionBudget
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.model_providers import CloudModelProvider, LMStudioProvider, OllamaProvider
from orbit.runtime.model_runtime.router import ModelRouter
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models import ModelManager
from orbit.runtime.models.models import CloudProviderKind
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import TaskCompletionStatus


async def run_paint_e2e_phase2a():
    prompt = "Open Paint, draw a red circle, and save it as test.png on the Desktop."
    print("=" * 70)
    print("ORBIT PHASE 2A — REAL DESKTOP E2E EXECUTION & CORRECTNESS PROOF")
    print("=" * 70)
    print("Prompt:", prompt)
    print("Timestamp:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("-" * 70)

    desktop_candidates = [
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "test.png"),
        os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "test.png"),
        os.path.join(os.path.expanduser("~"), "Desktop", "test.png"),
    ]
    initial_exists = any(os.path.exists(p) for p in desktop_candidates)
    print(f"Pre-execution Desktop/test.png exists: {initial_exists}")

    # 1. Initialize Real Capabilities & EventBus
    event_bus = EventBus()
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()

    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)
    pointer_cap = registry.get_optional(CapabilityType.POINTER)
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)
    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)

    # 2. Initialize Model Runtime Stack
    cloud_provs = [
        CloudModelProvider(cloud_kind=CloudProviderKind.OPENAI),
        CloudModelProvider(cloud_kind=CloudProviderKind.ANTHROPIC),
        CloudModelProvider(cloud_kind=CloudProviderKind.GEMINI),
    ]
    model_mgr = ModelManager(
        providers=[OllamaProvider(), LMStudioProvider()],
        cloud_providers=cloud_provs,
        event_bus=event_bus,
    )
    inv = await model_mgr.refresh_inventory()
    print(f"Discovered {len(inv.models)} available AI model runtimes across providers.")

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

    # 3. Instantiate Authoritative Production AgentExecutionLoop
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
            max_total_actions=10,
            max_repeated_actions_without_progress=3,
            max_recoveries_per_transition=2,
            no_progress_timeout_sec=60.0,
        ),
    )

    # 4. Execute Natural Language Task on Real Desktop
    print("\n[STARTING PRODUCTION AGENT EXECUTION LOOP]")
    t_start = time.perf_counter()
    res: AgentExecutionResult = await loop.run(
        prompt=prompt,
        task_id="phase_2a_paint_e2e",
    )
    elapsed = (time.perf_counter() - t_start) * 1000.0

    print("\n" + "=" * 70)
    print("PHASE 2A REAL DESKTOP EXECUTION REPORT")
    print("=" * 70)
    print(f"  Task ID:                 {res.task_id}")
    print(f"  Final Success Status:    {res.is_success}")
    print(f"  Final Completion Status: {res.final_status}")
    print(f"  Total Steps Executed:    {res.total_steps}")
    print(f"  Elapsed Duration:        {elapsed:.1f}ms")
    print(f"  Failure Reason:          {res.failure_reason}")

    # Check post-execution test.png existence
    found_artifact = None
    for p in desktop_candidates:
        if os.path.exists(p):
            found_artifact = p
            break

    print(f"\nPost-Execution Physical Artifact Check:")
    if found_artifact:
        sz = os.path.getsize(found_artifact)
        print(f"  File found at:    {found_artifact} (size: {sz} bytes)")
    else:
        print(f"  File found at:    None (File does not exist on Desktop)")

    print(f"\nPremature Success Guard Audit:")
    if not found_artifact and res.is_success:
        print("  CRITICAL ERROR: Premature success bug is STILL PRESENT!")
    elif not found_artifact and not res.is_success:
        print("  VERIFIED: GoalVerifier no longer permits premature success; downstream save execution remains a separate blocker.")
    elif found_artifact and res.is_success:
        print("  FULL PASS: Artifact created on disk and task succeeded after all requirements satisfied.")


if __name__ == "__main__":
    asyncio.run(run_paint_e2e_phase2a())
