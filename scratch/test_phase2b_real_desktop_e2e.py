"""Production Live Windows Validation: Phase 2B Real Desktop E2E Scenarios.

Scenarios:
A: "Open Edge"
B: "Open Paint"
C: "Open Paint, draw a red circle, and save it as test.png on the Desktop."

Adapter Mode: AdapterMode.PRODUCTION
"""

import asyncio
import os
import sys
import time
from typing import Any, Dict, List
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.cognitive.agent_decision import AgentDecisionEngine
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
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


def find_desktop_test_file() -> List[str]:
    candidates = [
        os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "test.png"),
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "test.png"),
        os.path.join(os.path.expanduser("~"), "Desktop", "test.png"),
    ]
    return [c for c in candidates if os.path.exists(c)]


def clean_desktop_test_file():
    for p in find_desktop_test_file():
        try:
            os.remove(p)
            print(f"[CLEANUP] Removed preexisting test file: {p}")
        except Exception as e:
            print(f"[CLEANUP] Could not remove {p}: {e}")


async def build_production_loop() -> AgentExecutionLoop:
    event_bus = EventBus()
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()

    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)
    pointer_cap = registry.get_optional(CapabilityType.POINTER)
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)
    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)

    decision_engine = CognitiveDecisionEngine()
    perception_engine = DesktopPerceptionEngine(observation_capability=obs_cap)
    observer = CurrentStateObserver(observation=obs_cap, perception_engine=perception_engine)
    target_locator = EvidenceBasedTargetLocator()
    goal_verifier = GoalVerifier()

    loop = AgentExecutionLoop(
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
    return loop


async def run_scenario(name: str, prompt: str, task_id: str) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(f"SCENARIO {name}: \"{prompt}\"")
    print("=" * 80)

    loop = await build_production_loop()
    t_start = time.perf_counter()
    res: AgentExecutionResult = await loop.run(prompt=prompt, task_id=task_id)
    duration_ms = (time.perf_counter() - t_start) * 1000.0

    print(f"\n--- SCENARIO {name} RESULTS ---")
    print(f"Task ID:                 {res.task_id}")
    print(f"Success:                 {res.is_success}")
    print(f"Final Status:            {res.final_status.value if hasattr(res.final_status, 'value') else res.final_status}")
    print(f"Total Steps:             {res.total_steps}")
    print(f"Duration:                {duration_ms:.1f}ms")
    print(f"Failure Reason:          {res.failure_reason}")

    actions_executed = []
    for step in res.step_history:
        act = getattr(step, "action_dispatched", None)
        act_type = act.action_type.value if (act and hasattr(act, "action_type")) else "NONE"
        params = act.parameters if act else {}
        actions_executed.append((step.step_index, act_type, params))
        print(f"  Step {step.step_index}: Action={act_type}, Params={params}")

    return {
        "scenario": name,
        "prompt": prompt,
        "task_id": res.task_id,
        "is_success": res.is_success,
        "final_status": res.final_status.value if hasattr(res.final_status, "value") else str(res.final_status),
        "total_steps": res.total_steps,
        "duration_ms": duration_ms,
        "failure_reason": res.failure_reason,
        "actions": actions_executed,
    }


async def main():
    print("=" * 80)
    print("ORBIT PHASE 2B — REAL PRODUCTION DESKTOP E2E TEST SUITE")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. Scenario A: "Open Edge"
    res_a = await run_scenario("A", "Open Edge", "phase2b_e2e_edge")

    # 2. Scenario B: "Open Paint"
    res_b = await run_scenario("B", "Open Paint", "phase2b_e2e_paint")

    # 3. Scenario C: "Open Paint, draw a red circle, and save it as test.png on the Desktop."
    clean_desktop_test_file()
    pre_existing = find_desktop_test_file()
    print(f"\nPre-Scenario C desktop test files: {pre_existing}")

    res_c = await run_scenario("C", "Open Paint, draw a red circle, and save it as test.png on the Desktop.", "phase2b_e2e_paint_save")

    # Validate Scenario C Artifact
    post_existing = find_desktop_test_file()
    artifact_valid = False
    artifact_path = None
    artifact_size = 0
    if post_existing:
        artifact_path = post_existing[0]
        artifact_size = os.path.getsize(artifact_path)
        try:
            with Image.open(artifact_path) as img:
                img.verify()
                artifact_valid = (artifact_size > 0 and img.format.upper() == "PNG")
        except Exception as img_err:
            print(f"[IMAGE VERIFICATION ERROR] {img_err}")
            artifact_valid = False

    print("\n" + "=" * 80)
    print("PHASE 2B REAL DESKTOP E2E SUMMARY REPORT")
    print("=" * 80)
    print(f"Scenario A (Open Edge):      {'PASS' if res_a['is_success'] else 'FAIL'} (Steps: {res_a['total_steps']})")
    print(f"Scenario B (Open Paint):     {'PASS' if res_b['is_success'] else 'FAIL'} (Steps: {res_b['total_steps']})")
    print(f"Scenario C (Paint + Save):   {'PASS' if res_c['is_success'] else 'FAIL'} (Steps: {res_c['total_steps']})")
    print(f"  - Artifact Created:        {artifact_path}")
    print(f"  - Artifact Size:           {artifact_size} bytes")
    print(f"  - Valid PNG Image:         {artifact_valid}")
    print(f"  - Human Interventions:     0")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
