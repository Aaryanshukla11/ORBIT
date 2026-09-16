"""Integration test for Human Steering & Takeover Safety Invariants (Phase 3E)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from orbit.contracts.capabilities import KeyboardCapability, PointerCapability, WorkspaceCapability
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.human_steering import HumanTakeoverSteeringManager
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.targeting.models import TargetResolutionResult, TargetResolutionStatus
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)


class SteeringAwareDecisionEngine:
    """Decision engine that adapts plan when user injects steering prompts."""

    def __init__(self, steering_manager: HumanTakeoverSteeringManager) -> None:
        self.steering_manager = steering_manager
        self.plan_steered: bool = False

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: list,
        step_index: int,
        **kwargs,
    ) -> CognitiveDecision:
        # Check if user injected steering guidance
        steer = self.steering_manager.consume_steering_prompt()
        if steer:
            self.plan_steered = True
            return CognitiveDecision(
                decision_summary=f"Adapting to user steering: '{steer}' -> Proposing safe Archive action",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=AbstractAction(
                    action_type=AbstractActionType.CLICK,
                    target=SemanticTarget(name="Archive Files"),
                    expected_effect="Files archived safely",
                ),
            )

        if step_index == 0:
            # Initially proposes high-risk action
            return CognitiveDecision(
                decision_summary="Proposing deletion of temporary cache",
                is_goal_satisfied=False,
                decision_confidence=0.8,
                next_action=AbstractAction(
                    action_type=AbstractActionType.CLICK,
                    target=SemanticTarget(name="Permanently Delete Cache"),
                    expected_effect="Cache deleted",
                ),
            )

        # Step 2: Goal completed
        return CognitiveDecision(
            decision_summary="Archival complete, task finished.",
            is_goal_satisfied=True,
            decision_confidence=1.0,
            next_action=AbstractAction(
                action_type=AbstractActionType.COMPLETE_GOAL,
                target=SemanticTarget(name="Done"),
                expected_effect="Task finished",
            ),
        )


@pytest.mark.asyncio
async def test_human_steering_safety_intervention_closed_loop():
    """Verify that dangerous action triggers safety halt, user steers to safe action, and agent adapts."""
    steering_manager = HumanTakeoverSteeringManager(strict_approval_mode=True)
    decision_engine = SteeringAwareDecisionEngine(steering_manager=steering_manager)

    ws = MagicMock(spec=WorkspaceCapability)
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    ptr = MagicMock(spec=PointerCapability)
    ptr.click = AsyncMock()

    target_locator = MagicMock()
    target_locator.locate_target = AsyncMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED))

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(
        return_value=CurrentStateObservation(
            observation_id="obs_steer",
            active_window_hwnd=444,
            active_window_title="Data Cleaner",
            ocr_tokens=["Data", "Cleaner", "Archive", "Files"],
        )
    )

    # Transition verifier enforces approval policy
    async def _mock_trans_verify(action, **kwargs):
        needs_appr, req = steering_manager.requires_approval(action)
        if needs_appr and not req.is_approved:
            # Dangerous action halted by safety policy!
            # User intervenes with steering prompt instead of approving
            steering_manager.inject_steering_prompt("Do not delete files, archive them instead")
            return ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=False,
                expected_effect_observed=False,
                goal_satisfied=False,
                outcome_status=OutcomeStatus.DISPATCH_FAILED,
                error_message="Action requires explicit human approval; halted by safety policy.",
            )
        # Safe action succeeds
        return ActionExecutionOutcome(
            action_id=action.action_id,
            dispatch_success=True,
            expected_effect_observed=True,
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
        )

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(side_effect=_mock_trans_verify)

    async def _mock_verify_goal(task_id, objective, current_observation, step_history, **kwargs):
        if decision_engine.plan_steered and len(step_history) >= 2:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(application_name="cleaner", application_is_open=True),
            )
        return GoalVerificationResult(status=TaskCompletionStatus.PARTIALLY_COMPLETED, is_completed=False)

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(side_effect=_mock_verify_goal)

    loop = AgentExecutionLoop(
        decision_engine=decision_engine,
        workspace=ws,
        keyboard=kb,
        pointer=ptr,
        target_locator=target_locator,
        goal_verifier=goal_verifier,
        observer=obs_mock,
        transition_verifier=trans_verifier,
        budget=ExecutionBudget(max_total_actions=5, timeout_seconds=10.0),
    )

    result = await loop.run("Clean temporary cache data")

    assert result.is_success is True
    assert decision_engine.plan_steered is True
