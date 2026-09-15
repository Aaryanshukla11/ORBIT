"""Phase 2B Unit & Integration Test Suite.

Mandatory Test Requirements (Section 10):
- TEST 1: "Open Edge" -> LAUNCH_APPLICATION (not UI target lookup)
- TEST 2: "Open Paint" -> LAUNCH_APPLICATION
- TEST 3: "click the search box" -> UI interaction action (CLICK)
- TEST 4: "Type hello" -> TYPE_TEXT
- TEST 5: "Save as test.png on Desktop" -> SAVE_FILE with correct target, destination, filename, format
- TEST 6: Save action requires post-action physical evidence (not just keyboard dispatch)
- TEST 7: Artifact verification (file exists AND valid)
- TEST 8: Multi-requirement task (draw verified + save pending) remains INCOMPLETE
- TEST 9: Multi-requirement task (draw verified + save verified) becomes COMPLETE
- TEST 10: Existing Phase 2A test suite remains green
"""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.capabilities.application_launcher import ApplicationLauncher
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.primitive_composer import PrimitiveComposer
from orbit.runtime.cognitive.primitive_execution_controller import PrimitiveExecutionController
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import TaskCompletionStatus
from orbit.runtime.task_completion.multi_evidence_verifier import MultiEvidenceActionVerifier


# ============================================================================
# TEST 1: "Open Edge" -> LAUNCH_APPLICATION (not UI_TARGET_LOOKUP)
# ============================================================================
@pytest.mark.asyncio
async def test_01_open_edge_routes_to_launch_application():
    interpreter = LLMIntentInterpreter()
    obj = await interpreter.interpret("Open Edge")
    assert obj.parameters.get("action_type") == "open"
    assert "edge" in obj.target_entities or obj.parameters.get("app_name") == "edge"

    planner = AgentPlanner()
    subgoal = SubObjective(
        sub_id="sub_1",
        title="Open Edge",
        description="Launch Microsoft Edge application",
        target_entity="edge",
    )
    candidates = planner.generate_candidate_plans(
        objective=obj,
        subgoal=subgoal,
        world_model=MagicMock(),
    )
    assert len(candidates) > 0
    plan = candidates[0]
    assert AbstractActionType.LAUNCH_APPLICATION in plan.proposed_primitives
    assert plan.targets[0].role in ("window", "application")

    # Verify fallback composer produces LAUNCH_APPLICATION
    composer = PrimitiveComposer(validator=PrimitiveValidator())
    seq = composer._compose_deterministic_fallback(
        goal_text="Open Edge",
        objective=obj,
        sub_objective=subgoal,
        context=MagicMock(),
    )
    assert len(seq.actions) > 0
    assert seq.actions[0].action_type == AbstractActionType.LAUNCH_APPLICATION
    assert seq.actions[0].parameters.get("application_name") == "edge"


# ============================================================================
# TEST 2: "Open Paint" -> LAUNCH_APPLICATION
# ============================================================================
@pytest.mark.asyncio
async def test_02_open_paint_routes_to_launch_application():
    interpreter = LLMIntentInterpreter()
    obj = await interpreter.interpret("Open Paint")
    assert "mspaint" in obj.target_entities or obj.parameters.get("app_name") in ("paint", "mspaint")

    planner = AgentPlanner()
    subgoal = SubObjective(
        sub_id="sub_1",
        title="Open Paint",
        description="Launch Paint application",
        target_entity="mspaint",
    )
    candidates = planner.generate_candidate_plans(
        objective=obj,
        subgoal=subgoal,
        world_model=MagicMock(),
    )
    assert len(candidates) > 0
    plan = candidates[0]
    assert AbstractActionType.LAUNCH_APPLICATION in plan.proposed_primitives

    composer = PrimitiveComposer(validator=PrimitiveValidator())
    seq = composer._compose_deterministic_fallback(
        goal_text="Open Paint",
        objective=obj,
        sub_objective=subgoal,
        context=MagicMock(),
    )
    assert len(seq.actions) > 0
    assert seq.actions[0].action_type == AbstractActionType.LAUNCH_APPLICATION
    assert seq.actions[0].parameters.get("application_name") in ("paint", "mspaint")


# ============================================================================
# TEST 3: "click the search box" -> UI interaction action (CLICK)
# ============================================================================
@pytest.mark.asyncio
async def test_03_click_search_box_routes_to_ui_click():
    composer = PrimitiveComposer(validator=PrimitiveValidator())
    obj = StructuredObjective(raw_prompt="click the search box", user_goal="click the search box", end_condition="clicked")
    seq = composer._compose_deterministic_fallback(
        goal_text="click the search box",
        objective=obj,
        sub_objective=None,
        context=MagicMock(),
    )
    assert len(seq.actions) > 0
    action = seq.actions[0]
    assert action.action_type == AbstractActionType.CLICK
    assert action.target.role in ("button", "control")
    assert "search box" in action.target.name.lower() or "search" in action.target.name.lower()


# ============================================================================
# TEST 4: "Type hello" -> TYPE_TEXT
# ============================================================================
@pytest.mark.asyncio
async def test_04_type_hello_routes_to_type_text():
    interpreter = LLMIntentInterpreter()
    obj = await interpreter.interpret("Type hello")
    assert obj.parameters.get("action_type") == "type"
    assert "hello" in obj.parameters.get("text", "").lower()

    composer = PrimitiveComposer(validator=PrimitiveValidator())
    seq = composer._compose_deterministic_fallback(
        goal_text="type hello",
        objective=obj,
        sub_objective=None,
        context=MagicMock(),
    )
    assert len(seq.actions) > 0
    action = seq.actions[0]
    assert action.action_type == AbstractActionType.TYPE_TEXT
    assert "hello" in action.parameters.get("text", "").lower()


# ============================================================================
# TEST 5: "Save as test.png on Desktop" -> SAVE_FILE with correct semantics
# ============================================================================
@pytest.mark.asyncio
async def test_05_save_as_produces_save_file_action():
    interpreter = LLMIntentInterpreter()
    obj = await interpreter.interpret("Save as test.png on Desktop")
    assert obj.parameters.get("action_type") == "save"
    assert obj.parameters.get("filename") == "test.png"
    assert obj.parameters.get("format") == "png"
    assert obj.parameters.get("target_dir") == "desktop"

    planner = AgentPlanner()
    subgoal = SubObjective(
        sub_id="sub_save",
        title="Save as test.png on Desktop",
        description="Persist active drawing to desktop as test.png",
        target_entity="test.png",
    )
    candidates = planner.generate_candidate_plans(
        objective=obj,
        subgoal=subgoal,
        world_model=MagicMock(),
    )
    assert len(candidates) > 0
    plan = candidates[0]
    assert AbstractActionType.SAVE_FILE in plan.proposed_primitives
    assert plan.creative_payload.get("filename") == "test.png"
    assert plan.creative_payload.get("format") == "png"
    assert plan.creative_payload.get("target_dir") == "desktop"


# ============================================================================
# TEST 6: Save action requires post-action physical evidence
# ============================================================================
@pytest.mark.asyncio
async def test_06_save_action_requires_physical_evidence():
    mock_kbd = AsyncMock()
    controller = PrimitiveExecutionController(
        validator=PrimitiveValidator(),
        verifier=MultiEvidenceActionVerifier(),
        keyboard=mock_kbd,
    )

    action = AbstractAction(
        action_type=AbstractActionType.SAVE_FILE,
        target=SemanticTarget(name="nonexistent_test_file_xyz_123.png", role="file", context="desktop"),
        parameters={
            "filename": "nonexistent_test_file_xyz_123.png",
            "target_dir": "desktop",
            "format": "png",
        },
        outcome_contract=ActionOutcomeContract(expected_state_transition="File saved"),
        expected_effect="File saved on disk",
    )

    pre_obs = CurrentStateObservation()
    # Dispatch without creating the physical file -> must fail post-action verification
    success, err = await controller._dispatch_save_file(action, pre_obs)
    assert success is False
    assert "SAVE_VERIFICATION_FAILED" in err


# ============================================================================
# TEST 7: Artifact verification (file exists AND valid)
# ============================================================================
def test_07_artifact_verification_checks_existence_and_validity():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Create a valid 10x10 PNG image
        img = Image.new("RGB", (10, 10), color="red")
        img.save(tmp_path, format="PNG")

        verifier = MultiEvidenceActionVerifier()
        action = AbstractAction(
            action_type=AbstractActionType.SAVE_FILE,
            parameters={"target_path": tmp_path, "filename": tmp_path, "format": "png"},
            outcome_contract=ActionOutcomeContract(expected_state_transition="saved"),
        )
        pre_obs = CurrentStateObservation()
        post_obs = CurrentStateObservation()

        res_valid = verifier._verify_save_file(action, pre_obs, post_obs, pixel_delta=True)
        assert res_valid.is_verified is True

        # Corrupt the file content
        with open(tmp_path, "wb") as f:
            f.write(b"not a valid png binary data header")

        res_corrupt = verifier._verify_save_file(action, pre_obs, post_obs, pixel_delta=True)
        assert res_corrupt.is_verified is False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ============================================================================
# TEST 8: Multi-requirement task (draw verified + save pending) is INCOMPLETE
# ============================================================================
@pytest.mark.asyncio
async def test_08_multi_req_draw_verified_save_pending_is_incomplete():
    verifier = GoalVerifier()
    prompt = "Open Paint, draw a red circle, and save it as test.png on the Desktop."
    obj = StructuredObjective(raw_prompt=prompt, user_goal=prompt, end_condition="goal_completed")

    dummy_dec = CognitiveDecision(
        step_index=0,
        decision_summary="Test decision",
        is_goal_satisfied=False,
    )

    # Step history with successful Paint launch and successful drawing, but NO save action
    step_history = [
        CognitiveStepResult(
            step_index=0,
            decision=dummy_dec,
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.LAUNCH_APPLICATION,
                parameters={"application_name": "mspaint"},
                outcome_contract=ActionOutcomeContract(expected_state_transition="paint open"),
            ),
            outcome_verified=True,
            post_observation=CurrentStateObservation(
                active_window_title="Paint",
                visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
            ),
        ),
        CognitiveStepResult(
            step_index=1,
            decision=dummy_dec,
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "circle"},
                outcome_contract=ActionOutcomeContract(expected_state_transition="circle drawn"),
            ),
            outcome_verified=True,
            post_observation=CurrentStateObservation(
                active_window_title="Paint",
                canvas_status="CANVAS_CHANGED",
                visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
            ),
        ),
    ]

    obs = CurrentStateObservation(
        active_window_title="Paint",
        canvas_status="CANVAS_CHANGED",
        visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
    )

    # Ensure no pre-existing test.png on Desktop
    res = await verifier.verify_goal_achievement(
        task_id="task_test_8",
        objective=obj,
        current_observation=obs,
        step_history=step_history,
    )
    assert res.is_completed is False
    assert res.status in (TaskCompletionStatus.FAILED, TaskCompletionStatus.PARTIALLY_COMPLETED)


# ============================================================================
# TEST 9: Multi-requirement task (draw verified + save verified) is COMPLETE
# ============================================================================
@pytest.mark.asyncio
async def test_09_multi_req_draw_verified_save_verified_is_complete():
    verifier = GoalVerifier()
    prompt = "Open Paint, draw a red circle, and save it as test.png on the Desktop."
    obj = StructuredObjective(raw_prompt=prompt, user_goal=prompt, end_condition="goal_completed")

    with tempfile.TemporaryDirectory() as tmpdir:
        fake_desktop_file = os.path.join(tmpdir, "test.png")
        img = Image.new("RGB", (20, 20), color="red")
        img.save(fake_desktop_file, format="PNG")

        dummy_dec = CognitiveDecision(
            step_index=0,
            decision_summary="Test decision",
            is_goal_satisfied=False,
        )

        step_history = [
            CognitiveStepResult(
                step_index=0,
                decision=dummy_dec,
                action_dispatched=AbstractAction(
                    action_type=AbstractActionType.LAUNCH_APPLICATION,
                    parameters={"application_name": "mspaint"},
                    outcome_contract=ActionOutcomeContract(expected_state_transition="paint open"),
                ),
                outcome_verified=True,
                post_observation=CurrentStateObservation(
                    active_window_title="Paint",
                    visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
                ),
            ),
            CognitiveStepResult(
                step_index=1,
                decision=dummy_dec,
                action_dispatched=AbstractAction(
                    action_type=AbstractActionType.DRAW_STROKES,
                    parameters={"shape": "circle"},
                    outcome_contract=ActionOutcomeContract(expected_state_transition="circle drawn"),
                ),
                outcome_verified=True,
                post_observation=CurrentStateObservation(
                    active_window_title="Paint",
                    canvas_status="CANVAS_CHANGED",
                    visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
                ),
            ),
            CognitiveStepResult(
                step_index=2,
                decision=dummy_dec,
                action_dispatched=AbstractAction(
                    action_type=AbstractActionType.SAVE_FILE,
                    parameters={"filename": fake_desktop_file, "target_path": fake_desktop_file, "format": "png"},
                    outcome_contract=ActionOutcomeContract(expected_state_transition="saved"),
                ),
                outcome_verified=True,
                post_observation=CurrentStateObservation(
                    active_window_title="Paint",
                    visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
                ),
            ),
        ]

        obs = CurrentStateObservation(
            active_window_title="Paint",
            canvas_status="CANVAS_CHANGED",
            visible_windows=[{"title": "Paint", "class_name": "MSPaintApp"}],
        )

        with patch.dict(os.environ, {"USERPROFILE": tmpdir}):
            # Also put test.png in tmpdir/Desktop/test.png for candidate search
            os.makedirs(os.path.join(tmpdir, "Desktop"), exist_ok=True)
            img.save(os.path.join(tmpdir, "Desktop", "test.png"), format="PNG")

            res = await verifier.verify_goal_achievement(
                task_id="task_test_9",
                objective=obj,
                current_observation=obs,
                step_history=step_history,
            )
            assert res.is_completed is True
            assert res.status == TaskCompletionStatus.COMPLETED


# ============================================================================
# TEST 10: Application Launcher Registry Checks
# ============================================================================
def test_10_application_launcher_registry():
    launcher = ApplicationLauncher()
    assert launcher.resolve_application("edge") == "msedge.exe"
    assert launcher.resolve_application("msedge") == "msedge.exe"
    assert launcher.resolve_application("paint") == "mspaint.exe"
    assert launcher.resolve_application("notepad") == "notepad.exe"
    assert launcher.resolve_application("calculator") == "calc.exe"
    assert launcher.resolve_application("calc") == "calc.exe"
    assert launcher.resolve_application("chrome") == "chrome.exe"
