"""Unit tests for Phase 5: Goal verification invariants (Guardrail 8)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.engine import CognitiveDecisionEngine
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.task_completion.models import TaskCompletionStatus


@pytest.mark.asyncio
async def test_complete_goal_signal_is_rejected_if_goal_verifier_fails():
    """Guardrail 8: COMPLETE_GOAL is a signal, not success. GoalVerifier must independently verify."""
    # Mock Observer
    obs = CurrentStateObservation(observation_id="obs_1", active_window_title="Desktop")
    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(return_value=obs)

    # Mock DecisionEngine to immediately emit COMPLETE_GOAL
    engine_mock = MagicMock(spec=CognitiveDecisionEngine)
    decision = CognitiveDecision(
        step_index=0,
        decision_summary="I think I am done",
        is_goal_satisfied=True,
        next_action=AbstractAction(
            action_type=AbstractActionType.COMPLETE_GOAL,
            parameters={"summary": "Done"},
            outcome_contract=ActionOutcomeContract(expected_state_transition="done"),
        ),
    )
    engine_mock.decide_next_step = AsyncMock(return_value=decision)

    # Mock GoalVerifier to return False (unverified)
    gv_mock = MagicMock(spec=GoalVerifier)
    gv_mock.verify_goal_achievement = AsyncMock(
        return_value=MagicMock(is_satisfied=False, is_completed=False, status=TaskCompletionStatus.FAILED)
    )

    loop = AgentExecutionLoop(
        observer=obs_mock,
        decision_engine=engine_mock,
        goal_verifier=gv_mock,
        budget=ExecutionBudget(max_total_actions=2),
    )

    # Run loop
    res: AgentExecutionResult = await loop.run("test task")

    # It must NOT report success merely because model proposed COMPLETE_GOAL
    assert res.is_success is False
    assert res.final_status != TaskCompletionStatus.COMPLETED
    assert gv_mock.verify_goal_achievement.await_count >= 1
