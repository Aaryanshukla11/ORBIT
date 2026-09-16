"""Unit tests for SelfCorrectionReflectionEngine (Phase 3F)."""

import pytest
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionExecutionResult,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.context_checkpoint import ContextCheckpoint
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.reflection import (
    CorrectionPlan,
    FailureRootCause,
    SelfCorrectionReflectionEngine,
)


def test_reflection_engine_diagnoses_unexpected_modal():
    """Verify reflection engine attributes modal dialogs and synthesizes Escape backtrack."""
    engine = SelfCorrectionReflectionEngine()

    act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="Submit"))
    step = CognitiveStepResult(
        step_index=1,
        decision=CognitiveDecision(decision_summary="Clicked Submit", next_action=act),
        action_dispatched=act,
        execution_result=ActionExecutionOutcome(
            action_id=act.action_id,
            dispatch_success=False,
            expected_effect_observed=False,
            error_message="Click blocked by foreground window",
        ),
    )

    obs = CurrentStateObservation(
        observation_id="obs_modal",
        active_window_hwnd=999,
        active_window_title="Warning Dialog",
        visible_windows=[{"hwnd": 999, "title": "Warning Dialog", "class_name": "#32770"}],
    )

    obj = StructuredObjective(
        raw_prompt="Submit form",
        user_goal="Submit form",
        end_condition="form_submitted",
    )

    plan = engine.diagnose_and_reflect(
        objective=obj,
        failed_step=step,
        step_history=[step],
        current_observation=obs,
    )

    assert isinstance(plan, CorrectionPlan)
    assert plan.root_cause == FailureRootCause.UNEXPECTED_MODAL
    assert len(plan.backtrack_actions) >= 1
    assert plan.backtrack_actions[0].action_type == AbstractActionType.SEND_HOTKEY
    assert plan.backtrack_actions[0].parameters.get("hotkey") == "Escape"


def test_reflection_engine_diagnoses_target_not_located():
    """Verify reflection engine attributes target location failures."""
    engine = SelfCorrectionReflectionEngine()

    act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="Hidden Button"))
    step = CognitiveStepResult(
        step_index=0,
        decision=CognitiveDecision(decision_summary="Clicked button", next_action=act),
        action_dispatched=act,
        execution_result=ActionExecutionOutcome(
            action_id=act.action_id,
            dispatch_success=False,
            expected_effect_observed=False,
            error_message="Target not found in observation snapshot",
        ),
    )

    obs = CurrentStateObservation(observation_id="obs_empty")
    obj = StructuredObjective(raw_prompt="Click button", user_goal="Click button", end_condition="clicked")

    plan = engine.diagnose_and_reflect(
        objective=obj,
        failed_step=step,
        step_history=[step],
        current_observation=obs,
    )

    assert plan.root_cause == FailureRootCause.TARGET_NOT_LOCATED
    assert "Hidden Button" in plan.root_cause_explanation


def test_reflection_engine_diagnoses_unresponsive_ui_and_synthesizes_alternates():
    """Verify reflection engine generates alternate hotkey hypotheses when UI click fails."""
    engine = SelfCorrectionReflectionEngine()

    act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="Save Document"))
    step = CognitiveStepResult(
        step_index=2,
        decision=CognitiveDecision(decision_summary="Clicked save", next_action=act),
        action_dispatched=act,
        execution_result=ActionExecutionOutcome(
            action_id=act.action_id,
            dispatch_success=True,
            expected_effect_observed=False,
            error_message="Effect not observed",
        ),
    )

    obs = CurrentStateObservation(observation_id="obs_unresponsive", active_window_title="Editor")
    obj = StructuredObjective(raw_prompt="Save file", user_goal="Save file", end_condition="file_saved")

    plan = engine.diagnose_and_reflect(
        objective=obj,
        failed_step=step,
        step_history=[step],
        current_observation=obs,
    )

    assert plan.root_cause == FailureRootCause.UNRESPONSIVE_UI
    assert len(plan.alternate_actions) >= 1
    # First alternate should be keyboard shortcut Ctrl+S
    assert plan.alternate_actions[0].action_type == AbstractActionType.SEND_HOTKEY
    assert plan.alternate_actions[0].parameters.get("hotkey") == "Ctrl+S"


def test_reflection_engine_tracks_checkpoint_backtrack():
    """Verify reflection attaches the latest healthy checkpoint ID for rollback."""
    engine = SelfCorrectionReflectionEngine()

    ckpt = ContextCheckpoint(
        checkpoint_id="ckpt_milestone_1",
        step_index=1,
        milestone_title="Editor Opened",
        user_goal="Save",
        end_condition="done",
        observation_snapshot=CurrentStateObservation(observation_id="obs_ckpt"),
    )

    act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="Save"))
    step = CognitiveStepResult(
        step_index=2,
        decision=CognitiveDecision(decision_summary="Save", next_action=act),
        action_dispatched=act,
        execution_result=ActionExecutionOutcome(
            action_id=act.action_id,
            dispatch_success=False,
            expected_effect_observed=False,
        ),
    )

    obs = CurrentStateObservation(observation_id="obs_now")
    obj = StructuredObjective(raw_prompt="Save", user_goal="Save", end_condition="done")

    plan = engine.diagnose_and_reflect(
        objective=obj,
        failed_step=step,
        step_history=[step],
        current_observation=obs,
        available_checkpoints=[ckpt],
    )

    assert plan.target_checkpoint_id == "ckpt_milestone_1"
