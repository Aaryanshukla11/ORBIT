"""Production Live Windows Validation: Calculator Multi-Step Autonomous Task (Step 5).

Executes:
"Open Calculator and calculate 123 multiplied by 456."

Verifies REAL desktop closed-loop execution:
1. Live Initial Desktop Observation
2. Model Decision & Routing (Vision/LLM)
3. Physical Application Launch (calc.exe / Windows Calculator)
4. Fresh Post-Action Observation & Immediate Verification
5. Multi-Step Semantic Interaction & Calculation Input
6. Fresh State Observation & Verification
7. Independent GoalVerifier Evaluation & Task Completion
"""

import asyncio
import os
import sys
import time

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
from orbit.runtime.model_runtime.router import ModelRouter
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models import ModelManager
from orbit.runtime.models.models import CloudProviderKind
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.task_completion.goal_verifier import GoalVerifier


async def run_real_calculator_validation():
    print("=" * 70)
    print("ORBIT STEP 5 — PRODUCTION CLOSED-LOOP REALITY VALIDATION: CALCULATOR")
    print("=" * 70)
    print("Prompt: 'Open Calculator and calculate 123 multiplied by 456.'")
    print("Timestamp:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("-" * 70)

    event_bus = EventBus()
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))

    # Start registered capability adapters
    await registry.initialize_all()
    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)
    pointer_cap = registry.get_optional(CapabilityType.POINTER)
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)
    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)

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
    for m in inv.models[:5]:
        print(f"  - [{m.provider.value}] {m.model_id} (Capabilities={[c.value for c in m.capabilities]})")

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
            max_total_actions=15,
            max_repeated_actions_without_progress=3,
            max_recoveries_per_transition=2,
            no_progress_timeout_sec=240.0,
        ),
    )

    print("\n[STARTING PRODUCTION AGENT EXECUTION LOOP]")
    t_start = time.perf_counter()
    res: AgentExecutionResult = await loop.run(
        prompt="Open Calculator and calculate 123 multiplied by 456.",
        task_id="real_calc_val_01",
    )
    t_elapsed = time.perf_counter() - t_start

    print("\n" + "=" * 70)
    print("REAL TASK EXECUTION OUTCOME REPORT")
    print("=" * 70)
    print(f"Task ID:          {res.task_id}")
    print(f"User Goal:        {res.objective.user_goal}")
    print(f"Success:          {res.is_success}")
    print(f"Final Status:     {res.final_status.value}")
    print(f"Total Steps:      {res.total_steps}")
    print(f"Elapsed Time:     {t_elapsed:.2f}s ({res.elapsed_duration_ms:.1f}ms)")
    if res.failure_reason:
        print(f"Failure Reason:   {res.failure_reason} (Code: {res.failure_code})")

    print("\n" + "-" * 70)
    print(f"CHRONOLOGICAL STATE TRANSITIONS ({len(res.state_transitions)} total):")
    print("-" * 70)
    for tr in res.state_transitions:
        print(f"  [{tr.state_before.value} -> {tr.state_after.value}] (cycle={tr.cycle_number}, obs={tr.observation_id}, dur={tr.duration_ms:.1f}ms)")

    print("\n" + "-" * 70)
    print(f"STRUCTURED CYCLE EXECUTION TRACES ({len(res.cycle_traces)} total):")
    print("-" * 70)
    for ct in res.cycle_traces:
        print(format_cycle_trace_block(ct))
        print()

    await registry.shutdown_all()
    await model_mgr.shutdown()
    await session_mgr.shutdown()

    return res


if __name__ == "__main__":
    asyncio.run(run_real_calculator_validation())
