"""Unit tests for Multi-Requirement Semantic Verification.

Invariant under test:
A task must never be marked COMPLETED merely because one part of the user's request
was successfully executed. Every mandatory semantic requirement extracted from the
original user goal must either be independently verified as satisfied or the task
must remain incomplete/failed.
"""

import os
import time
from unittest.mock import MagicMock
from PIL import Image
import pytest

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.capabilities.models import CapabilityCategory, GoalRequirementSet
from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import TaskCompletionStatus


def test_goal_requirements_extractor_decomposes_compound_goal_into_all_mandatory_parts():
    """Verify GoalRequirementExtractor properly extracts all parts of a compound goal."""
    extractor = GoalRequirementExtractor()
    obj = StructuredObjective(
        raw_prompt="Open Calculator and calculate 75 * 14, then write the result into Notepad",
        user_goal="Open Calculator and calculate 75 * 14, then write the result into Notepad",
        end_condition="notepad_contains_result",
    )
    req_set = extractor.extract_requirements(obj)

    assert req_set.target_domain == "compound_multi_stage"
    req_types = [r.requirement_type for r in req_set.requirements]
    assert "APPLICATION_LIFECYCLE" in req_types
    assert "DATA_EXTRACTION" in req_types
    assert "DATA_INPUT" in req_types
    assert "STATE_VERIFICATION" in req_types

    # Ensure both Calculator and Notepad lifecycles are represented
    app_reqs = [r for r in req_set.requirements if r.requirement_type == "APPLICATION_LIFECYCLE"]
    app_names = [r.parameters.get("application_name", "").lower() for r in app_reqs]
    assert "calculator" in app_names
    assert "notepad" in app_names

    # Check calculation requirement parameters
    calc_req = next(r for r in req_set.requirements if r.requirement_type == "DATA_EXTRACTION")
    assert calc_req.parameters.get("expected_result") == "1050"

    # Check text entry requirement parameters
    input_req = next(r for r in req_set.requirements if r.requirement_type == "DATA_INPUT")
    assert input_req.parameters.get("text") == "1050"
    assert input_req.parameters.get("text_source") == "calculation_result"


@pytest.mark.asyncio
async def test_compound_goal_calculation_and_notepad_fails_when_only_calculation_done():
    """Task MUST NOT complete when Calculator is done but Notepad has not been opened/typed."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_calc_only",
        active_window_title="Calculator",
        visible_windows=[{"title": "Calculator"}],
        ocr_tokens=["1050"],
    )

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_calc_notepad_partial_1",
        objective="Open Calculator and calculate 75 * 14, then write the result into Notepad",
        current_observation=obs,
    )

    # Invariant: Partial success must NEVER mark task as COMPLETED
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "notepad" in res.failure_reason.lower()

    unsatisfied = res.evidence.diagnostics.get("unsatisfied_requirements", [])
    satisfied = res.evidence.diagnostics.get("satisfied_requirements", [])
    assert "req_calculation" in satisfied
    assert any("notepad" in u for u in unsatisfied)
    assert "req_text_input" in unsatisfied


@pytest.mark.asyncio
async def test_compound_goal_calculation_and_notepad_fails_when_only_notepad_text_present_without_calculation():
    """Task MUST NOT complete if text is present but the required calculation tool never ran."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_notepad_only",
        active_window_title="Untitled - Notepad",
        visible_windows=[{"title": "Untitled - Notepad"}],
        ocr_tokens=["1050"],
    )

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_calc_notepad_partial_2",
        objective="Open Calculator and calculate 75 * 14, then write the result into Notepad",
        current_observation=obs,
    )

    # Invariant: Calculator lifecycle requirement is missing
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "calculator" in res.failure_reason.lower()


@pytest.mark.asyncio
async def test_compound_goal_calculation_and_notepad_completes_when_both_satisfied():
    """Task is marked COMPLETED only when ALL mandatory semantic requirements are verified."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_both_satisfied",
        active_window_title="Untitled - Notepad",
        visible_windows=[{"title": "Calculator"}, {"title": "Untitled - Notepad"}],
        ocr_tokens=["1050"],
    )

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_calc_notepad_full",
        objective="Open Calculator and calculate 75 * 14, then write the result into Notepad",
        current_observation=obs,
    )

    assert res.is_completed is True
    assert res.status == TaskCompletionStatus.COMPLETED
    assert res.failure_reason == ""
    assert len(res.evidence.diagnostics.get("unsatisfied_requirements", [])) == 0


@pytest.mark.asyncio
async def test_compound_goal_paint_cube_and_notepad_fails_when_notepad_missing():
    """Task MUST NOT complete when Paint cube drawing succeeds but secondary Notepad action failed."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_paint_cube_only",
        active_window_title="Untitled - Paint",
        visible_windows=[{"title": "Untitled - Paint"}],
        canvas_status="DRAWING_COMPLETED",
    )
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "cube"},
            )
        )
    ]

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_paint_notepad_partial",
        objective="Open Paint and draw a cube, then open Notepad and write 'Cube Done'",
        current_observation=obs,
        step_history=step_hist,
    )

    # Cube drawing was satisfied, but Notepad and text entry were not!
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "notepad" in res.failure_reason.lower() or "cube done" in res.failure_reason.lower()


@pytest.mark.asyncio
async def test_compound_goal_paint_cube_and_notepad_completes_when_all_satisfied():
    """Task completes when Paint drawing AND Notepad entry are both independently verified."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_paint_and_notepad_full",
        active_window_title="Untitled - Notepad",
        visible_windows=[{"title": "Untitled - Paint"}, {"title": "Untitled - Notepad"}],
        canvas_status="DRAWING_COMPLETED",
        ocr_tokens=["Cube", "Done"],
    )
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "cube"},
            )
        )
    ]

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_paint_notepad_all_ok",
        objective="Open Paint and draw a cube, then open Notepad and write 'Cube Done'",
        current_observation=obs,
        step_history=step_hist,
    )

    assert res.is_completed is True
    assert res.status == TaskCompletionStatus.COMPLETED
@pytest.mark.asyncio
async def test_regression_test_1_single_requirement_open_notepad_satisfied():
    """Test 1 — Single requirement: 'Open Notepad' satisfied -> FINAL = COMPLETE."""
    goal_verifier = GoalVerifier()
    obs = CurrentStateObservation(
        observation_id="obs_notepad_single",
        active_window_title="Untitled - Notepad",
        visible_windows=[{"title": "Untitled - Notepad"}],
    )
    res = await goal_verifier.verify_goal_achievement(
        task_id="task_test_1_single_req",
        objective="Open Notepad",
        current_observation=obs,
    )
    assert res.is_completed is True
    assert res.status == TaskCompletionStatus.COMPLETED
    assert res.failure_reason == ""


@pytest.mark.asyncio
async def test_regression_test_2_multiple_requirements_one_incomplete():
    """Test 2 — Multiple requirements, one incomplete: Req A = SATISFIED, Req B = PENDING -> FINAL = NOT COMPLETE."""
    goal_verifier = GoalVerifier()
    # Paint is open and strokes are drawn (Req A satisfied), but save to test.png is pending (Req B incomplete)
    obs = CurrentStateObservation(
        observation_id="obs_paint_only",
        active_window_title="Untitled - Paint",
        visible_windows=[{"title": "Untitled - Paint"}],
        canvas_status="DRAWING_COMPLETED",
    )
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "circle"},
            )
        )
    ]
    res = await goal_verifier.verify_goal_achievement(
        task_id="task_test_2_incomplete",
        objective="Open Paint, draw a red circle, and save it as non_existent_file_12345.png on the Desktop",
        current_observation=obs,
        step_history=step_hist,
    )
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "non_existent_file_12345.png" in res.failure_reason or "req_file_management" in res.evidence.diagnostics["unsatisfied_requirements"]


@pytest.mark.asyncio
async def test_regression_test_3_multiple_requirements_all_satisfied(tmp_path):
    """Test 3 — Multiple requirements, all satisfied: Req A = SATISFIED, Req B = SATISFIED -> FINAL = COMPLETE."""
    goal_verifier = GoalVerifier()
    # Create valid target file in tmp_path
    target_file = tmp_path / "saved_test.png"
    # Write a valid minimal PNG
    from PIL import Image
    im = Image.new("RGB", (10, 10), color="red")
    im.save(str(target_file))

    obs = CurrentStateObservation(
        observation_id="obs_paint_and_file_all_sat",
        active_window_title="Untitled - Paint",
        visible_windows=[{"title": "Untitled - Paint"}],
        canvas_status="DRAWING_COMPLETED",
    )
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "circle"},
            )
        )
    ]
    res = await goal_verifier.verify_goal_achievement(
        task_id="task_test_3_all_sat",
        objective=StructuredObjective(
            raw_prompt=f"Open Paint, draw a circle, and save it as {target_file}",
            user_goal=f"Open Paint, draw a circle, and save it as {target_file}",
            end_condition="goal_completed",
            parameters={"file_path": str(target_file)},
        ),
        current_observation=obs,
        step_history=step_hist,
    )
    assert res.is_completed is True
    assert res.status == TaskCompletionStatus.COMPLETED
    assert res.failure_reason == ""
    assert "req_file_management" in res.evidence.diagnostics["satisfied_requirements"]


@pytest.mark.asyncio
async def test_regression_test_4_one_requirement_failed():
    """Test 4 — One requirement failed: Req A = SATISFIED, Req B = FAILED -> FINAL = NOT COMPLETE."""
    goal_verifier = GoalVerifier()
    # Calculator lifecycle is satisfied, but calculation arithmetic result mismatch / missing
    obs = CurrentStateObservation(
        observation_id="obs_calc_fail",
        active_window_title="Calculator",
        visible_windows=[{"title": "Calculator"}],
        ocr_tokens=["999999"],  # Does not match 75 * 14 = 1050
    )
    res = await goal_verifier.verify_goal_achievement(
        task_id="task_test_4_one_failed",
        objective="Open Calculator and calculate 75 * 14",
        current_observation=obs,
    )
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "1050" in res.failure_reason or "req_calculation" in res.evidence.diagnostics["unsatisfied_requirements"]


@pytest.mark.asyncio
async def test_regression_test_5_latest_action_success_must_not_imply_goal_success():
    """Test 5 — Explicit reproduction of the Phase 1.6 bug:
    DRAW_STROKES = VERIFIED, SAVE_FILE = PENDING -> FINAL = NOT COMPLETE.
    Action verification != Goal verification.
    """
    goal_verifier = GoalVerifier()
    # Step history records DRAW_STROKES action dispatched and effect verified
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "circle"},
            ),
            execution_result=MagicMock(
                dispatch_success=True,
                expected_effect_observed=True,
                is_success=True,
            ),
        )
    ]
    obs = CurrentStateObservation(
        observation_id="obs_paint_strokes_rendered",
        active_window_title="Untitled - Paint",
        visible_windows=[{"title": "Untitled - Paint"}],
        canvas_status="DRAWING_COMPLETED",
    )
    res = await goal_verifier.verify_goal_achievement(
        task_id="task_test_5_reproduce_bug",
        objective="Open Paint, draw a red circle, and save it as test_paint_artifact_not_saved.png on the Desktop",
        current_observation=obs,
        step_history=step_hist,
    )
    # INVARIANT: Latest action success must NEVER declare goal success while file save requirement is unsatisfied!
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "req_file_management" in res.evidence.diagnostics["unsatisfied_requirements"]
    assert "req_content_visual" in res.evidence.diagnostics["satisfied_requirements"]


@pytest.mark.asyncio
async def test_regression_test_6_later_requirement_completion(tmp_path):
    """Test 6 — Later requirement completion:
    Step 1: DRAW = SATISFIED, SAVE = PENDING -> NOT COMPLETE
    Step 2: SAVE = SATISFIED (file created) -> COMPLETE
    """
    goal_verifier = GoalVerifier()
    target_file = tmp_path / "test_progressive.png"

    obs = CurrentStateObservation(
        observation_id="obs_progressive",
        active_window_title="Untitled - Paint",
        visible_windows=[{"title": "Untitled - Paint"}],
        canvas_status="DRAWING_COMPLETED",
    )
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "circle"},
            )
        )
    ]

    # Step 1: File does not exist yet
    res_step1 = await goal_verifier.verify_goal_achievement(
        task_id="task_test_6_prog_1",
        objective=StructuredObjective(
            raw_prompt=f"Open Paint, draw a red circle, and save it as {target_file}",
            user_goal=f"Open Paint, draw a red circle, and save it as {target_file}",
            end_condition="goal_completed",
            parameters={"file_path": str(target_file)},
        ),
        current_observation=obs,
        step_history=step_hist,
    )
    assert res_step1.is_completed is False

    # Step 2: File is physically saved to disk
    from PIL import Image
    im = Image.new("RGB", (20, 20), color="red")
    im.save(str(target_file))

    res_step2 = await goal_verifier.verify_goal_achievement(
        task_id="task_test_6_prog_2",
        objective=StructuredObjective(
            raw_prompt=f"Open Paint, draw a red circle, and save it as {target_file}",
            user_goal=f"Open Paint, draw a red circle, and save it as {target_file}",
            end_condition="goal_completed",
            parameters={"file_path": str(target_file)},
        ),
        current_observation=obs,
        step_history=step_hist,
    )
    assert res_step2.is_completed is True
    assert res_step2.status == TaskCompletionStatus.COMPLETED


@pytest.mark.asyncio
async def test_regression_test_7_verification_missing_evidence_absent():
    """Test 7 — Requirement exists but evidence is absent -> NOT COMPLETE."""
    goal_verifier = GoalVerifier()
    # Empty observation, no windows, no OCR, no canvas
    obs = CurrentStateObservation(
        observation_id="obs_empty_desktop",
        active_window_title="Program Manager",
        visible_windows=[],
        ocr_tokens=[],
    )
    res = await goal_verifier.verify_goal_achievement(
        task_id="task_test_7_missing_evidence",
        objective="Open Notepad and type 'Secret Code 42'",
        current_observation=obs,
    )
    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert len(res.evidence.diagnostics["satisfied_requirements"]) == 0
    assert len(res.evidence.diagnostics["unsatisfied_requirements"]) > 0


@pytest.mark.asyncio
async def test_regression_test_8_existing_dependency_semantics(tmp_path):
    """Test 8 — Multi-stage compound dependencies:
    Calculator -> Notepad -> File Save
    All dependent stages must be independently verified in final state.
    """
    goal_verifier = GoalVerifier()
    saved_calc_file = tmp_path / "calc_output.txt"
    saved_calc_file.write_text("Result: 56000", encoding="utf-8")

    obs = CurrentStateObservation(
        observation_id="obs_multi_dep",
        active_window_title="Untitled - Notepad",
        visible_windows=[{"title": "Calculator"}, {"title": "Untitled - Notepad"}],
        ocr_tokens=["56000"],
    )
    step_hist = [
        MagicMock(
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.TYPE_TEXT,
                parameters={"text": "56000"},
            ),
            execution_result=MagicMock(is_success=True, expected_effect_observed=True),
        )
    ]

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_test_8_dependent",
        objective=StructuredObjective(
            raw_prompt=f"Open Calculator, calculate 200 * 280, write result into Notepad, and save to {saved_calc_file}",
            user_goal=f"Open Calculator, calculate 200 * 280, write result into Notepad, and save to {saved_calc_file}",
            end_condition="goal_completed",
            parameters={"file_path": str(saved_calc_file)},
        ),
        current_observation=obs,
        step_history=step_hist,
    )
    assert res.is_completed is True
    assert res.status == TaskCompletionStatus.COMPLETED
    assert "req_file_management" in res.evidence.diagnostics["satisfied_requirements"]


@pytest.mark.asyncio
async def test_provenance_verification_rejects_preexisting_file_without_task_provenance(tmp_path):
    """Artifact evidence on disk must have provenance within task execution timeframe.
    A file modified hours before task start cannot count as completed for a fresh run.
    """
    goal_verifier = GoalVerifier()
    target_file = tmp_path / "preexisting_output.png"

    # Create image file with timestamp in the past
    img = Image.new("RGB", (100, 100), color="red")
    img.save(target_file)
    old_mtime = time.time() - 3600  # 1 hour ago
    os.utime(target_file, (old_mtime, old_mtime))

    obs = CurrentStateObservation(
        observation_id="obs_provenance_test",
        active_window_title="Untitled - Paint",
        visible_windows=[{"title": "Untitled - Paint"}],
        canvas_status="DRAWING_COMPLETED",
    )
    task_start_time = time.time()
    step_hist = [
        MagicMock(
            timestamp=task_start_time,
            action_dispatched=AbstractAction(
                action_type=AbstractActionType.DRAW_STROKES,
                parameters={"shape": "circle"},
            ),
        )
    ]

    res = await goal_verifier.verify_goal_achievement(
        task_id="task_provenance_check",
        objective=StructuredObjective(
            raw_prompt=f"Open Paint, draw a red circle, and save it as {target_file}",
            user_goal=f"Open Paint, draw a red circle, and save it as {target_file}",
            end_condition="goal_completed",
            parameters={"file_path": str(target_file)},
        ),
        current_observation=obs,
        step_history=step_hist,
    )

    assert res.is_completed is False
    assert res.status == TaskCompletionStatus.FAILED
    assert "req_file_management" in res.evidence.diagnostics["unsatisfied_requirements"]
    assert "provenance" in res.failure_reason.lower()

