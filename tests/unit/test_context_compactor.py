"""Unit tests for ContextCompactor and token budget bounding (Phase 2G.1)."""

import pytest
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.context_compactor import ContextCompactor
from orbit.runtime.cognitive.models import (
    ActionExecutionResult,
    CognitiveDecision,
    CognitiveStepResult,
    OutcomeStatus,
)


def _create_dummy_step(step_idx: int, action_type: AbstractActionType, target_name: str, verified: bool = True) -> CognitiveStepResult:
    action = AbstractAction(
        action_type=action_type,
        target=SemanticTarget(name=target_name, role="button"),
        parameters={"value": f"val_{step_idx}"},
    )
    decision = CognitiveDecision(
        decision_summary=f"Step {step_idx} decision",
        is_goal_satisfied=False,
    )
    exec_res = ActionExecutionResult(
        action_id=action.action_id,
        dispatch_success=verified,
        expected_effect_observed=verified,
        status=OutcomeStatus.EFFECT_VERIFIED if verified else OutcomeStatus.EFFECT_UNVERIFIED,
        error_message=None if verified else "Failed verification",
    )
    return CognitiveStepResult(
        step_index=step_idx,
        decision=decision,
        action_dispatched=action,
        execution_result=exec_res,
        outcome_verified=verified,
    )


def test_compact_history_short():
    compactor = ContextCompactor(max_detailed_steps=4)
    history = [
        _create_dummy_step(0, AbstractActionType.LAUNCH_APPLICATION, "Notepad"),
        _create_dummy_step(1, AbstractActionType.FOCUS_WINDOW, "Notepad"),
    ]

    res = compactor.compact_history(history, current_step=2)
    assert res.total_steps == 2
    assert res.compacted_steps_count == 0
    assert res.detailed_steps_count == 2
    assert "LAUNCH_APPLICATION('Notepad'" in res.summary_text
    assert "FOCUS_WINDOW('Notepad'" in res.summary_text


def test_compact_history_long_compresses_older_steps():
    compactor = ContextCompactor(max_detailed_steps=3, max_characters=2000)
    history = [
        _create_dummy_step(0, AbstractActionType.LAUNCH_APPLICATION, "Notepad"),
        _create_dummy_step(1, AbstractActionType.FOCUS_WINDOW, "Notepad"),
        _create_dummy_step(2, AbstractActionType.TYPE_TEXT, "Editor"),
        _create_dummy_step(3, AbstractActionType.TYPE_TEXT, "Editor"),
        _create_dummy_step(4, AbstractActionType.TYPE_TEXT, "Editor"),
        _create_dummy_step(5, AbstractActionType.CLICK, "SaveButton"),
        _create_dummy_step(6, AbstractActionType.TYPE_TEXT, "FilenameInput"),
        _create_dummy_step(7, AbstractActionType.CLICK, "ConfirmSave"),
    ]

    res = compactor.compact_history(
        history,
        current_step=8,
        active_subgoals_summary="- Subgoal 1: Finished\n- Subgoal 2: In Progress",
        key_facts={"active_doc": "report.txt"},
    )

    assert res.total_steps == 8
    assert res.compacted_steps_count == 5  # Steps 0-4 compacted
    assert res.detailed_steps_count == 3   # Steps 5-7 detailed
    assert "PRIOR EXECUTION PHASES (Steps 0 to 4)" in res.summary_text
    assert "RECENT ACTIONS (Steps 5 to 7)" in res.summary_text
    assert "CLICK('ConfirmSave'" in res.summary_text
    assert "active_doc='report.txt'" in res.summary_text


def test_context_compactor_enforces_max_char_limit():
    compactor = ContextCompactor(max_detailed_steps=2, max_characters=300)
    history = [_create_dummy_step(i, AbstractActionType.TYPE_TEXT, f"Target_{i}") for i in range(15)]

    res = compactor.compact_history(history, current_step=15)
    assert len(res.summary_text) <= 300
    assert res.char_count <= 300
