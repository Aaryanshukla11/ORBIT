"""Unit tests for Multi-Requirement Semantic Verification.

Invariant under test:
A task must never be marked COMPLETED merely because one part of the user's request
was successfully executed. Every mandatory semantic requirement extracted from the
original user goal must either be independently verified as satisfied or the task
must remain incomplete/failed.
"""

import pytest
from unittest.mock import MagicMock

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
    assert res.failure_reason == ""
