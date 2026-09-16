import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.cognitive.models import AbstractAction, AbstractActionType, StructuredObjective
from orbit.runtime.task_completion.multi_evidence_verifier import MultiEvidenceActionVerifier

async def test():
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()

    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)
    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)

    # Launch Paint
    await workspace_cap.launch_process("mspaint")
    await asyncio.sleep(2.0)

    perception_engine = DesktopPerceptionEngine(observation_capability=obs_cap)
    observer = CurrentStateObserver(observation=obs_cap, perception_engine=perception_engine)

    obj = StructuredObjective(raw_prompt="Open Paint", user_goal="Open Paint", end_condition="goal_completed", parameters={"app_name": "paint"})
    pre_obs = await observer.observe(obj)
    post_obs = await observer.observe(obj)

    print("Post obs target_app_exists:", post_obs.target_app_exists)
    print("Post obs target_app_is_active:", post_obs.target_app_is_active)
    print("Post obs active_title:", post_obs.active_window_title)
    print("Post obs visible windows:", [(w.get("hwnd"), w.get("title"), w.get("class_name")) for w in post_obs.visible_windows])

    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"app_name": "mspaint"},
        expected_effect="mspaint running",
    )
    verifier = MultiEvidenceActionVerifier()
    res = await verifier.verify_action_effect(action, pre_obs, post_obs)
    print("\nVerification result:")
    print("  is_verified:", res.is_verified)
    print("  reason:", res.verification_reason)

if __name__ == "__main__":
    asyncio.run(test())
