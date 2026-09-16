"""Unit tests for TrajectoryMemory and Loop Detection (Phase 2G.1)."""

import pytest
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.models import (
    ActionExecutionResult,
    CognitiveDecision,
    CognitiveStepResult,
    OutcomeStatus,
)
from orbit.runtime.cognitive.trajectory_memory import TrajectoryMemory


def _create_step(
    step_idx: int,
    action_type: AbstractActionType,
    target_name: str,
    params: dict = None,
    verified: bool = True,
    err_msg: str = None,
) -> CognitiveStepResult:
    action = AbstractAction(
        action_type=action_type,
        target=SemanticTarget(name=target_name, role="button"),
        parameters=params or {},
    )
    decision = CognitiveDecision(decision_summary="Test", is_goal_satisfied=False)
    exec_res = ActionExecutionResult(
        action_id=action.action_id,
        dispatch_success=verified,
        expected_effect_observed=verified,
        status=OutcomeStatus.EFFECT_VERIFIED if verified else OutcomeStatus.EFFECT_UNVERIFIED,
        error_message=err_msg,
    )
    return CognitiveStepResult(
        step_index=step_idx,
        decision=decision,
        action_dispatched=action,
        execution_result=exec_res,
        outcome_verified=verified,
    )


def test_trajectory_memory_records_steps_and_detects_repetition_loop():
    mem = TrajectoryMemory(loop_threshold=3)

    # Dispatch identical action 3 times consecutively
    for i in range(3):
        step = _create_step(i, AbstractActionType.CLICK, "SaveButton", verified=False, err_msg="Button disabled")
        mem.record_step(step, active_window_title="Notepad")

    is_loop, msg = mem.is_looping_detected()
    assert is_loop is True
    assert "Repetitive action loop detected" in msg
    assert "SaveButton" in msg

    guidance = mem.get_recovery_guidance()
    assert guidance is not None
    assert "LOOP WARNING" in guidance


def test_trajectory_memory_detects_oscillation():
    mem = TrajectoryMemory(oscillation_threshold=4)

    # Alternating A -> B -> A -> B
    step_a1 = _create_step(0, AbstractActionType.CLICK, "Tab1", verified=True)
    step_b1 = _create_step(1, AbstractActionType.CLICK, "Tab2", verified=True)
    step_a2 = _create_step(2, AbstractActionType.CLICK, "Tab1", verified=True)
    step_b2 = _create_step(3, AbstractActionType.CLICK, "Tab2", verified=True)

    mem.record_step(step_a1)
    mem.record_step(step_b1)
    mem.record_step(step_a2)
    mem.record_step(step_b2)

    is_loop, msg = mem.is_looping_detected()
    assert is_loop is True
    assert "Oscillation loop detected" in msg


def test_trajectory_memory_dead_end_identification():
    mem = TrajectoryMemory()

    step1 = _create_step(0, AbstractActionType.CLICK, "BrokenLink", verified=False, err_msg="404 Not Found")
    step2 = _create_step(1, AbstractActionType.CLICK, "BrokenLink", verified=False, err_msg="404 Not Found")

    mem.record_step(step1)
    mem.record_step(step2)

    proposed = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="BrokenLink", role="button"),
        parameters={},
    )
    is_dead, dead_reason = mem.is_known_dead_end(proposed)
    assert is_dead is True
    assert "Action is a known dead-end: failed 2 times" in dead_reason
