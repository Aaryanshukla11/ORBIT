"""Integration test for Multi-Modal Reasoning Context Pipeline (Phase 3A)."""

import asyncio
import json
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
from orbit.runtime.cognitive.multimodal_context_builder import (
    MultimodalContextBuilder,
    MultimodalContextPayload,
)
from orbit.runtime.perception.set_of_marks import SetOfMarksGenerator
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


class MultimodalVLMDecisionEngine:
    """Decision engine that builds and consumes multimodal vision-action contexts."""

    def __init__(self, context_builder: MultimodalContextBuilder) -> None:
        self.context_builder = context_builder
        self.payloads_generated: list[MultimodalContextPayload] = []

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: list,
        step_index: int,
        **kwargs,
    ) -> CognitiveDecision:
        # Build multimodal context with Set-of-Marks overlay
        raw_img = Image.new("RGB", (1280, 720), color="white")
        payload = self.context_builder.build_context(
            objective=objective,
            observation=observation,
            step_history=step_history,
            step_index=step_index,
            raw_image=raw_img,
        )
        self.payloads_generated.append(payload)

        # Convert to OpenAI messages to prove payload validity
        openai_msgs = payload.to_openai_messages()
        assert len(openai_msgs) >= 2

        if step_index == 0:
            # First step: Select save button via visual mark [1]
            return CognitiveDecision(
                decision_summary="Clicking Save Button via Set-of-Marks tag [1]",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=AbstractAction(
                    action_type=AbstractActionType.CLICK,
                    target=SemanticTarget(name="Save Button [1]"),
                    expected_effect="Save dialog opened",
                ),
            )

        # Second step: Goal satisfied
        return CognitiveDecision(
            decision_summary="Objective fully accomplished",
            is_goal_satisfied=True,
            decision_confidence=1.0,
            next_action=AbstractAction(
                action_type=AbstractActionType.COMPLETE_GOAL,
                target=SemanticTarget(name="Done"),
                expected_effect="Task finished",
            ),
        )


@pytest.mark.asyncio
async def test_multimodal_reasoning_closed_loop():
    """Verify that MultimodalContextBuilder drives decision reasoning and target execution."""
    builder = MultimodalContextBuilder()
    decision_engine = MultimodalVLMDecisionEngine(context_builder=builder)

    ws = MagicMock(spec=WorkspaceCapability)
    ws.launch_process = AsyncMock(return_value={"pid": 1010})
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    ptr = MagicMock(spec=PointerCapability)
    ptr.move_to = AsyncMock()
    ptr.click = AsyncMock()

    visual_grounder = VisualRegionGrounder()

    async def _mock_locate(target, observation, **kwargs):
        # Resolve target using latest SOM marks from builder payload
        if decision_engine.payloads_generated and decision_engine.payloads_generated[-1].som_result:
            som_res = decision_engine.payloads_generated[-1].som_result
            return visual_grounder.resolve_from_som(
                target=target,
                som_result=som_res,
                observation_id=observation.observation_id,
            )
        # Fallback target resolution
        bbox = TargetBoundingBox(left=100, top=50, right=200, bottom=90)
        safe_pt = SafeActionPoint(x=150, y=70, bounding_box=bbox, desktop_generation_id=1)
        res = ResolvedTarget(
            target_id="tgt_save",
            bounding_box=bbox,
            safe_point=safe_pt,
            confidence=0.9,
            evidence=TargetEvidence(source="VISUAL_SOM", identifier="mark_1", name="Save Button"),
            observation_id=observation.observation_id,
            desktop_generation_id=1,
        )
        return TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=res)

    target_locator = MagicMock()
    target_locator.locate_target = AsyncMock(side_effect=_mock_locate)

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(
        return_value=CurrentStateObservation(
            observation_id="obs_mm_1",
            active_window_hwnd=777,
            active_window_title="Document Editor",
            ocr_tokens=["Save"],
            raw_evidence={"ocr_tokens": [{"word": "Save", "left": 100, "top": 50, "width": 100, "height": 40}]},
        )
    )

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(
        return_value=ActionExecutionOutcome(
            action_id="act_save",
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

    result = await loop.run("Save the document in Editor")

    assert result.is_success is True
    assert len(decision_engine.payloads_generated) >= 1
    # Verify SOM was generated and attached in payload
    first_payload = decision_engine.payloads_generated[0]
    assert first_payload.som_image_base64 is not None
    assert "Save" in first_payload.user_text_prompt
    # Verify pointer click was dispatched
    ptr.click.assert_awaited()
