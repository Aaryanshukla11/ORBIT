import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapteC:\Users\Aaryan shukla\OneDrive\Desktop\test.png
rMode, CapabilityType
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.task_completion.goal_verifier import GoalVerifier


async def test():
    registry = create_capability_registry(config=RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION))
    await registry.initialize_all()

    obs_cap = registry.get_optional(CapabilityType.OBSERVATION)
    pointer_cap = registry.get_optional(CapabilityType.POINTER)
    keyboard_cap = registry.get_optional(CapabilityType.KEYBOARD)
    workspace_cap = registry.get_optional(CapabilityType.WORKSPACE)

    from orbit.runtime.cognitive.primitive_execution_controller import PrimitiveExecutionController
    from orbit.runtime.cognitive.models import AbstractAction, AbstractActionType, CurrentStateObservation, StructuredObjective
    from orbit.runtime.task_completion.multi_evidence_verifier import MultiEvidenceActionVerifier

    verifier = MultiEvidenceActionVerifier()
    controller = PrimitiveExecutionController(
        verifier=verifier,
        pointer=pointer_cap,
        keyboard=keyboard_cap,
        workspace=workspace_cap,
    )

    desktop_path = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "test.png")
    if os.path.exists(desktop_path):
        os.remove(desktop_path)

    # Launch Paint
    await workspace_cap.launch_process("mspaint")
    await asyncio.sleep(2.0)

    # Draw strokes
    draw_act = AbstractAction(
        action_type=AbstractActionType.DRAW_STROKES,
        parameters={"shape": "circle", "app_name": "mspaint"},
        expected_effect="Draw circle on canvas",
    )
    obs = CurrentStateObservation(observation_id="test_obs")
    obj = StructuredObjective(raw_prompt="test", user_goal="test", end_condition="goal_completed")
    res_draw = await controller.execute_primitive(draw_act, obs, obj)
    print("Draw result:", res_draw.execution_outcome.dispatch_success)

    # Save File
    save_act = AbstractAction(
        action_type=AbstractActionType.SAVE_FILE,
        parameters={"filename": "test.png", "target_dir": "desktop", "format": "png", "app_name": "mspaint"},
        expected_effect="Save file to desktop",
    )
    res_save = await controller.execute_primitive(save_act, obs, obj)
    print("Save result:", res_save.execution_outcome.dispatch_success, res_save.execution_outcome.error_message)
    print("File exists on disk:", os.path.exists(desktop_path))

if __name__ == "__main__":
    asyncio.run(test())
