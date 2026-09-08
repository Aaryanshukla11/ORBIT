"""Unit tests for the Cognitive Decision Engine with Layered Decision Hierarchy."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.models import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionResult,
    ActionOutcomeContract,
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    OutcomeStatus,
    SemanticTarget,
    StructuredObjective,
)
from orbit.runtime.models.models import ModelGenerateResponse


@pytest.mark.asyncio
async def test_decision_launch_app_when_not_running():
    engine = CognitiveDecisionEngine()
    objective = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Draw cube in Paint",
        end_condition="canvas_has_cube_drawing",
        target_entities=["mspaint", "canvas"],
        parameters={"app_name": "mspaint", "action_type": "draw", "shape": "cube"},
    )
    obs = CurrentStateObservation(
        active_window_title="Desktop",
        target_app_exists=False,
        target_app_is_active=False,
    )

    decision = await engine.decide_next_step(objective, obs, step_history=[], step_index=0)
    assert not decision.is_goal_satisfied
    assert not decision.escalated_to_llm  # Resolved by fast deterministic rule
    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.LAUNCH_APPLICATION
    assert decision.next_action.target is not None
    assert decision.next_action.target.name == "mspaint"
    assert "x" not in decision.next_action.parameters


@pytest.mark.asyncio
async def test_decision_focus_app_when_open_but_inactive():
    engine = CognitiveDecisionEngine()
    objective = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Draw cube in Paint",
        end_condition="canvas_has_cube_drawing",
        target_entities=["mspaint", "canvas"],
        parameters={"app_name": "mspaint", "action_type": "draw", "shape": "cube"},
    )
    obs = CurrentStateObservation(
        active_window_title="Calculator",
        target_app_exists=True,
        target_app_is_active=False,
    )

    decision = await engine.decide_next_step(objective, obs, step_history=[], step_index=1)
    assert not decision.is_goal_satisfied
    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.FOCUS_WINDOW
    assert decision.next_action.target is not None
    assert decision.next_action.target.name == "mspaint"


@pytest.mark.asyncio
async def test_decision_draw_strokes_when_active():
    engine = CognitiveDecisionEngine()
    objective = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Draw cube in Paint",
        end_condition="canvas_has_cube_drawing",
        target_entities=["mspaint", "canvas"],
        parameters={"app_name": "mspaint", "action_type": "draw", "shape": "cube"},
    )
    obs = CurrentStateObservation(
        active_window_title="Untitled - Paint",
        target_app_exists=True,
        target_app_is_active=True,
    )

    decision = await engine.decide_next_step(objective, obs, step_history=[], step_index=2)
    assert not decision.is_goal_satisfied
    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.DRAW_STROKES
    assert decision.next_action.parameters.get("shape") == "cube"
    assert decision.next_action.target is not None
    assert decision.next_action.target.role == "canvas"


@pytest.mark.asyncio
async def test_decision_complete_goal_after_drawing_succeeded():
    engine = CognitiveDecisionEngine()
    objective = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Draw cube in Paint",
        end_condition="canvas_has_cube_drawing",
        target_entities=["mspaint", "canvas"],
        parameters={"app_name": "mspaint", "action_type": "draw", "shape": "cube"},
    )
    obs = CurrentStateObservation(
        active_window_title="Untitled - Paint",
        target_app_exists=True,
        target_app_is_active=True,
        canvas_status="READY_FOR_DRAWING",
    )

    prev_step = CognitiveStepResult(
        step_index=0,
        decision=CognitiveDecision(
            decision_summary="Drawing cube",
            expected_state_transition="canvas_modified",
            is_goal_satisfied=False,
            step_index=0,
        ),
        action_dispatched=AbstractAction(
            action_type=AbstractActionType.DRAW_STROKES,
            parameters={"shape": "cube"},
        ),
        execution_result=ActionExecutionResult(
            dispatch_success=True,
            expected_effect_observed=True,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
        ),
        state_progress_detected=True,
    )

    decision = await engine.decide_next_step(objective, obs, step_history=[prev_step], step_index=1)
    assert decision.is_goal_satisfied
    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.COMPLETE_GOAL


@pytest.mark.asyncio
async def test_decision_escalates_to_llm_on_unexpected_state():
    mock_session_mgr = MagicMock()
    mock_session_mgr.get_active_context.return_value = MagicMock(model_id="mock-qwen-7b")
    mock_session_mgr.generate = AsyncMock(
        return_value=ModelGenerateResponse(
            model_id="mock-qwen-7b",
            content='''{
              "is_goal_satisfied": false,
              "decision_summary": "The Downloads folder is open, but the target file is not visible.",
              "decision_confidence": 0.95,
              "evidence_used": ["Active: Downloads window"],
              "expected_state_transition": "Search field becomes focused",
              "reason_summary": "Searching is required before the file can be opened.",
              "next_action": {
                 "action_type": "CLICK_ELEMENT",
                 "target": {
                    "name": "Search Downloads",
                    "role": "edit",
                    "context": "Downloads window"
                 },
                 "parameters": {},
                 "expected_effect": "Search field becomes focused"
              }
            }'''
        )
    )

    engine = CognitiveDecisionEngine(model_session_manager=mock_session_mgr)
    # Objective with complex / non-standard intent that triggers LLM escalation
    objective = StructuredObjective(
        raw_prompt="Find my downloaded quarterly invoice and open it",
        user_goal="Find and open quarterly invoice",
        end_condition="invoice_opened",
        target_entities=["explorer", "invoice"],
        parameters={"action_type": "custom_search"},
    )
    obs = CurrentStateObservation(
        active_window_title="Downloads",
        target_app_exists=True,
        target_app_is_active=True,
    )

    decision = await engine.decide_next_step(objective, obs, step_history=[], step_index=0)
    assert decision.escalated_to_llm is True
    assert decision.decision_summary == "The Downloads folder is open, but the target file is not visible."
    assert decision.next_action is not None
    assert decision.next_action.target is not None
    assert decision.next_action.target.name == "Search Downloads"
    assert decision.next_action.target.role == "edit"
