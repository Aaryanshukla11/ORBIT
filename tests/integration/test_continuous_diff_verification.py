"""Integration test for Continuous Action Verification with Semantic Diff Engine (Phase 3D)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from PIL import Image

from orbit.contracts.capabilities import KeyboardCapability, PointerCapability, WorkspaceCapability
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetResolutionResult,
    TargetResolutionStatus,
)
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)
from orbit.runtime.verification.semantic_diff_engine import SemanticDiffEngine


class ContinuousDiffMockEngine:
    """Decision engine driven by continuous action verification."""

    def __init__(self) -> None:
        self.step = 0

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: list,
        step_index: int,
        **kwargs,
    ) -> CognitiveDecision:
        self.step = step_index
        if step_index == 0:
            return CognitiveDecision(
                decision_summary="Typing code snippet into editor",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=AbstractAction(
                    action_type=AbstractActionType.TYPE_TEXT,
                    target=SemanticTarget(name="Editor Canvas"),
                    parameters={"text": "print('Astra 6 Continuous Diff')"},
                    expected_effect="Code typed into editor",
                ),
            )
        return CognitiveDecision(
            decision_summary="Code confirmed via semantic diff. Finishing.",
            is_goal_satisfied=True,
            decision_confidence=1.0,
            next_action=AbstractAction(
                action_type=AbstractActionType.COMPLETE_GOAL,
                target=SemanticTarget(name="Done"),
                expected_effect="Task finished",
            ),
        )


@pytest.mark.asyncio
async def test_continuous_diff_verification_closed_loop():
    """Verify that SemanticDiffEngine dynamically verifies action outcomes in closed loop."""
    diff_engine = SemanticDiffEngine()
    decision_engine = ContinuousDiffMockEngine()

    ws = MagicMock(spec=WorkspaceCapability)
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    kb.type_text = AsyncMock()
    ptr = MagicMock(spec=PointerCapability)

    target_locator = MagicMock()
    target_locator.locate_target = AsyncMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED))

    call_count = [0]
    def _create_obs(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 1:
            # Pre-state: blank editor
            return CurrentStateObservation(
                observation_id="obs_pre_diff",
                active_window_hwnd=999,
                active_window_title="Script.py - Code Editor",
                ocr_tokens=["File", "Edit", "Selection"],
            )
        # Post-state: typed code observed
        return CurrentStateObservation(
            observation_id="obs_post_diff",
            active_window_hwnd=999,
            active_window_title="Script.py - Code Editor",
            ocr_tokens=["File", "Edit", "Selection", "print('Astra", "6", "Continuous", "Diff')"],
        )

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(side_effect=_create_obs)

    # Transition verifier powered by SemanticDiffEngine
    async def _mock_trans_verify(action, pre_state, post_state, **kwargs):
        diff = diff_engine.compute_diff(action=action, pre_obs=pre_state, post_obs=post_state)
        is_verified = diff.confidence_score >= 0.80
        return ActionExecutionOutcome(
            action_id=action.action_id,
            dispatch_success=True,
            expected_effect_observed=is_verified,
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED if is_verified else OutcomeStatus.EFFECT_UNVERIFIED,
            diagnostic_feedback=diff.verification_rationale,
        )

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(side_effect=_mock_trans_verify)

    async def _mock_verify_goal(task_id, objective, current_observation, step_history, **kwargs):
        if len(step_history) >= 1:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(application_name="editor", application_is_open=True),
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

    result = await loop.run("Type Astra 6 code into editor")

    assert result.is_success is True
    # Verify typing was called
    kb.type_text.assert_awaited()
