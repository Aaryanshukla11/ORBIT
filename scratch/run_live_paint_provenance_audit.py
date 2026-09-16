"""Live Desktop Paint E2E Provenance Audit Script using AgentExecutionLoop."""

import asyncio
from datetime import datetime, timezone
import json
import os
import sys
from PIL import Image

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.multi_evidence_verifier import MultiEvidenceActionVerifier


async def run_audit():
    print("=== STARTING LIVE PAINT E2E PROVENANCE AUDIT ===")
    user_profile = os.environ.get("USERPROFILE", "")
    target_path = os.path.join(user_profile, "OneDrive", "Desktop", "test.png")
    if not os.path.exists(os.path.dirname(target_path)):
        target_path = os.path.join(user_profile, "Desktop", "test.png")

    # 1. Pre-task Snapshot
    if os.path.exists(target_path):
        os.remove(target_path)
        print(f"[PRE-TASK] Removed pre-existing file: {target_path}")

    pre_task_time = datetime.now(timezone.utc)

    # 2. Initialize capabilities
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()

    pointer_cap = registry.get_optional(CapabilityType.POINTER)
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)
    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)
    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)

    observer = CurrentStateObserver(observation=obs_cap)
    decision_engine = CognitiveDecisionEngine()
    goal_verifier = GoalVerifier()

    loop = AgentExecutionLoop(
        observer=observer,
        decision_engine=decision_engine,
        workspace=workspace_cap,
        pointer=pointer_cap,
        keyboard=keyboard_cap,
        observation=obs_cap,
        goal_verifier=goal_verifier,
    )

    prompt = "Open Paint, draw a red circle, and save it as test.png on the Desktop."
    print(f"\n[RUNNING AGENT LOOP] Prompt: '{prompt}'")
    
    result = await loop.run(
        prompt=prompt,
        task_id="audit_paint_e2e",
    )

    print(f"\n[AGENT LOOP FINISHED]")
    print(f"  Is Success: {result.is_success}")
    print(f"  Final Status: {result.final_status}")
    print(f"  Total Steps: {result.total_steps}")

    # 3. Post-Task Filesystem Diff & Artifact Verification
    file_exists = os.path.exists(target_path)
    file_size = os.path.getsize(target_path) if file_exists else 0
    file_mtime = os.path.getmtime(target_path) if file_exists else 0

    valid_png = False
    img_size = None
    if file_exists and file_size > 0:
        try:
            with Image.open(target_path) as img:
                img.verify()
                img_size = img.size
            valid_png = True
        except Exception as e:
            print(f"PNG validation error: {e}")

    audit_report = {
        "target_file_path": target_path,
        "file_exists": file_exists,
        "file_size_bytes": file_size,
        "file_mtime": file_mtime,
        "file_mtime_utc": datetime.fromtimestamp(file_mtime, tz=timezone.utc).isoformat() if file_mtime else None,
        "pre_task_start_utc": pre_task_time.isoformat(),
        "is_newer_than_task_start": (file_mtime >= pre_task_time.timestamp() - 10) if file_mtime else False,
        "valid_png_header": valid_png,
        "image_dimensions": img_size,
        "loop_is_success": result.is_success,
        "total_steps": result.total_steps,
        "step_actions": [
            {
                "step": s.step_index,
                "action_type": s.action_dispatched.action_type.value if s.action_dispatched else "UNKNOWN",
                "verified": s.execution_result.expected_effect_observed if s.execution_result else False,
                "reason": s.execution_result.verification_reason if s.execution_result else "",
            }
            for s in result.step_history
        ],
    }

    print("\n=== AUDIT RESULTS ===")
    print(json.dumps(audit_report, indent=2))
    return audit_report


if __name__ == "__main__":
    asyncio.run(run_audit())
