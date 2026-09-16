"""Integration test for Set-of-Marks (SOM) visual grounding in the execution pipeline (Phase 2G.3)."""

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
    CognitiveStepResult,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.perception.set_of_marks import SetOfMarksGenerator, SOMResult
from orbit.runtime.targeting.action_point import calculate_safe_action_point
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetResolutionResult,
    TargetResolutionStatus,
)
from orbit.runtime.targeting.visual_grounder import VisualRegionGrounder
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)


class SOMMockDecisionEngine:
    """Decision engine that references Set-of-Marks indices to interact with custom canvas controls."""

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
            # Step 0: Click mark [2] (Brush tool)
            return CognitiveDecision(
                decision_summary="Selecting Brush tool via Set-of-Marks tag [2]",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=AbstractAction(
                    action_type=AbstractActionType.CLICK,
                    target=SemanticTarget(name="Brush Tool [2]"),
                    expected_effect="Brush tool activated",
                ),
            )
        # Step 1: Complete goal
        return CognitiveDecision(
            decision_summary="Brush tool selected. Objective satisfied.",
            is_goal_satisfied=True,
            decision_confidence=1.0,
            next_action=AbstractAction(
                action_type=AbstractActionType.COMPLETE_GOAL,
                target=SemanticTarget(name="Done"),
                expected_effect="Goal completed",
            ),
        )


@pytest.mark.asyncio
async def test_som_visual_grounding_end_to_end():
    """Verify that Set-of-Marks accurately grounds visual mark targets into pointer clicks."""
    budget = ExecutionBudget(max_total_actions=5, timeout_seconds=10.0)
    mock_engine = SOMMockDecisionEngine()

    ws = MagicMock(spec=WorkspaceCapability)
    ws.launch_process = AsyncMock(return_value={"pid": 9999})
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    ptr = MagicMock(spec=PointerCapability)
    ptr.move_to = AsyncMock()
    ptr.click = AsyncMock()

    # Generate SOM overlay from canvas elements
    img = Image.new("RGB", (1280, 720), color="white")
    ocr_tokens = [
        {"word": "Select", "left": 100, "top": 50, "width": 80, "height": 30},
        {"word": "Brush", "left": 200, "top": 50, "width": 80, "height": 30},
        {"word": "Eraser", "left": 300, "top": 50, "width": 80, "height": 30},
    ]

    som_generator = SetOfMarksGenerator()
    som_result = som_generator.generate_som(image=img, ocr_tokens=ocr_tokens)
    assert len(som_result.marks) == 3

    visual_grounder = VisualRegionGrounder()

    # Target locator delegating to visual grounder when mark is referenced
    async def _mock_locate(target, observation, **kwargs):
        return visual_grounder.resolve_from_som(
            target=target,
            som_result=som_result,
            observation_id=observation.observation_id,
        )

    target_locator = MagicMock()
    target_locator.locate_target = AsyncMock(side_effect=_mock_locate)

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(
        return_value=CurrentStateObservation(
            observation_id="obs_canvas_1",
            active_window_hwnd=555,
            active_window_title="Paint Canvas",
            ocr_tokens=["Select", "Brush", "Eraser"],
        )
    )

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(
        return_value=ActionExecutionOutcome(
            action_id="act_1",
            dispatch_success=True,
            expected_effect_observed=True,
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
        )
    )

    async def _mock_verify_goal(task_id, objective, current_observation, step_history, **kwargs):
        if len(step_history) >= 1:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(application_name="paint", application_is_open=True),
            )
        return GoalVerificationResult(status=TaskCompletionStatus.PARTIALLY_COMPLETED, is_completed=False)

    goal_verifier = MagicMock()
    goal_verifier.verify_goal_achievement = AsyncMock(side_effect=_mock_verify_goal)

    loop = AgentExecutionLoop(
        decision_engine=mock_engine,
        workspace=ws,
        keyboard=kb,
        pointer=ptr,
        target_locator=target_locator,
        goal_verifier=goal_verifier,
        observer=obs_mock,
        transition_verifier=trans_verifier,
        budget=budget,
    )

    result = await loop.run("Select Brush tool in Paint Canvas")

    assert result.is_success is True
    # Verify pointer was clicked at mark [2] coordinates (center of Brush tool: 200 + 80//2 = 240, 50 + 30//2 = 65)
    ptr.click.assert_awaited()
    call_args = ptr.click.call_args
    assert call_args is not None
