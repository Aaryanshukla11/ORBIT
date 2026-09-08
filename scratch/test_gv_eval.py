import asyncio
from orbit.runtime.cognitive.models import StructuredObjective, CognitiveStepResult, CognitiveDecision
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, ActionExecutionResult, OutcomeStatus
from orbit.runtime.task_completion.goal_verifier import GoalVerifier
from orbit.runtime.cognitive.models import CurrentStateObservation

async def test_gv():
    gv = GoalVerifier()
    obj = StructuredObjective(
        raw_prompt="Open Notepad and type ORBIT Vision Test 123",
        user_goal="Open Notepad and type ORBIT Vision Test 123",
        end_condition="text_typed_in_notepad",
        target_entities=["notepad"],
    )
    obs = CurrentStateObservation(
        active_window_title="Untitled - Notepad",
        visible_windows=[{"title": "Untitled - Notepad", "hwnd": 1234}],
        ocr_tokens=["ORBIT", "Vision", "Test", "123"],
    )
    step = CognitiveStepResult(
        step_index=1,
        decision=CognitiveDecision(
            decision_summary="Type text",
            decision_confidence=1.0,
            evidence_used=["notepad"],
        ),
        action_dispatched=AbstractAction(
            action_type=AbstractActionType.TYPE_TEXT,
            parameters={"text": "ORBIT Vision Test 123"},
        ),
        execution_result=ActionExecutionResult(
            dispatch_success=True,
            expected_effect_observed=True,
            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
        ),
    )
    res = await gv.verify_goal_achievement(
        task_id="t1",
        objective=obj,
        current_observation=obs,
        step_history=[step],
    )
    print("GoalVerifier result:", res.is_completed, res.status)

asyncio.run(test_gv())
