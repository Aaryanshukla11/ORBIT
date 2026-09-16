"""Integration test for Multi-Application Window Orchestration (Phase 3C)."""

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
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CurrentStateObservation,
    ExecutionBudget,
    StructuredObjective,
)
from orbit.runtime.cognitive.window_orchestrator import MultiAppWindowOrchestrator
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


class MultiAppCrossWorkflowEngine:
    """Decision engine that coordinates data transfer across Chrome and Notepad."""

    def __init__(self, orchestrator: MultiAppWindowOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: list,
        step_index: int,
        **kwargs,
    ) -> CognitiveDecision:
        self.orchestrator.update_from_observation(observation)

        if step_index == 0:
            # Step 0: In Chrome, extract data and copy
            self.orchestrator.set_clipboard("Sales Report: Total $45,000")
            return CognitiveDecision(
                decision_summary="Extracted sales figure from Chrome to clipboard",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=AbstractAction(
                    action_type=AbstractActionType.SEND_HOTKEY,
                    parameters={"hotkey": "Ctrl+C"},
                    expected_effect="Text copied to clipboard",
                ),
            )

        elif step_index == 1:
            # Step 1: Switch focus to Notepad
            focus_act = self.orchestrator.synthesize_focus_action("notepad")
            assert focus_act is not None
            return CognitiveDecision(
                decision_summary="Focusing Notepad to paste sales figure",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=focus_act,
            )

        elif step_index == 2:
            # Step 2: Paste clipboard data into Notepad
            paste_act = self.orchestrator.synthesize_paste_action(target=SemanticTarget(name="Notepad Edit Area"))
            return CognitiveDecision(
                decision_summary="Pasting sales figure into Notepad",
                is_goal_satisfied=False,
                decision_confidence=0.95,
                next_action=paste_act,
            )

        # Step 3: Complete Goal
        return CognitiveDecision(
            decision_summary="Sales data successfully transferred from Chrome to Notepad",
            is_goal_satisfied=True,
            decision_confidence=1.0,
            next_action=AbstractAction(
                action_type=AbstractActionType.COMPLETE_GOAL,
                target=SemanticTarget(name="Done"),
                expected_effect="Cross-app task completed",
            ),
        )


@pytest.mark.asyncio
async def test_cross_app_window_orchestration_closed_loop():
    """Verify end-to-end multi-app workflow: extract from Chrome -> focus Notepad -> paste."""
    orchestrator = MultiAppWindowOrchestrator()
    decision_engine = MultiAppCrossWorkflowEngine(orchestrator=orchestrator)

    ws = MagicMock(spec=WorkspaceCapability)
    ws.set_focus_window = AsyncMock(return_value=True)

    kb = MagicMock(spec=KeyboardCapability)
    kb.press_key = AsyncMock()
    kb.release_key = AsyncMock()
    ptr = MagicMock(spec=PointerCapability)
    ptr.click = AsyncMock()

    target_locator = MagicMock()
    target_locator.locate_target = AsyncMock(return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED))

    call_count = [0]
    def _create_obs(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 1:
            # Initially in Chrome
            return CurrentStateObservation(
                observation_id="obs_chrome",
                active_window_hwnd=111,
                active_window_title="Sales Dashboard - Google Chrome",
                visible_windows=[
                    {"hwnd": 111, "title": "Sales Dashboard - Google Chrome", "process_name": "chrome.exe"},
                    {"hwnd": 222, "title": "Untitled - Notepad", "process_name": "notepad.exe"},
                ],
            )
        # After focus: Notepad is active
        return CurrentStateObservation(
            observation_id=f"obs_notepad_{call_count[0]}",
            active_window_hwnd=222,
            active_window_title="Untitled - Notepad",
            ocr_tokens=["Sales", "Report:", "Total", "$45,000"],
            visible_windows=[
                {"hwnd": 111, "title": "Sales Dashboard - Google Chrome", "process_name": "chrome.exe"},
                {"hwnd": 222, "title": "Untitled - Notepad", "process_name": "notepad.exe"},
            ],
        )

    obs_mock = MagicMock()
    obs_mock.observe = AsyncMock(side_effect=_create_obs)

    trans_verifier = MagicMock()
    trans_verifier.verify_action_outcome = AsyncMock(
        return_value=ActionExecutionOutcome(
            action_id="act_trans",
            dispatch_success=True,
            expected_effect_observed=True,
            goal_satisfied=False,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
        )
    )

    async def _mock_verify_goal(task_id, objective, current_observation, step_history, **kwargs):
        if len(step_history) >= 3:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=TaskCompletionEvidence(application_name="notepad", application_is_open=True),
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
        budget=ExecutionBudget(max_total_actions=8, timeout_seconds=10.0),
    )

    result = await loop.run("Transfer sales report figure from Chrome to Notepad")

    assert result.is_success is True
    # Verify focus was called for Notepad HWND 222
    ws.set_focus_window.assert_awaited()
    # Verify clipboard content
    assert orchestrator.get_clipboard() == "Sales Report: Total $45,000"
