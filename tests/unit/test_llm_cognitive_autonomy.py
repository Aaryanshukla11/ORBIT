"""Unit test suite for ORBIT LLM-Powered Autonomous Reasoning & Complex Task Autonomy."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.models.models import (
    ModelChatMessage,
    ModelChatResponse,
    ModelGenerateResponse,
    ModelRole,
)
from orbit.runtime.planning.llm_synthesizer import LLMPlanSynthesizer
from orbit.runtime.planning.models import PlanActionType, PlanStatus
from orbit.runtime.planning.planner import TaskPlanningEngine
from orbit.runtime.task_understanding.engine import TaskUnderstandingEngine
from orbit.runtime.task_understanding.llm_decomposer import LLMTaskDecomposer
from orbit.runtime.task_understanding.models import TaskGoal, TaskUnderstandingStatus


@pytest.fixture
def mock_msm():
    """Mock ModelSessionManager for testing LLM decomposition and plan synthesis."""
    msm = MagicMock()
    msm.is_model_active.return_value = True
    msm.active_model_id = "test-qwen2.5"
    return msm


@pytest.mark.asyncio
async def test_llm_task_decomposer_parses_compound_instructions(mock_msm):
    """Test LLMTaskDecomposer extracts ordered sub-intents from a compound desktop goal."""
    decomposer = LLMTaskDecomposer(model_session_manager=mock_msm)

    # Simulated LLM response with clean JSON decomposition
    mock_msm.chat = AsyncMock(return_value=ModelChatResponse(
        content='''
        {
          "thought": "The user wants to open Calculator, calculate 120 * 45, open Notepad, and type the summary.",
          "intents": [
            {
              "goal": "OPEN_APPLICATION",
              "target_name": "Calculator",
              "target_role": "window",
              "content": null,
              "is_generative": false
            },
            {
              "goal": "CALCULATE",
              "target_name": "Calculator",
              "target_role": "button",
              "content": "120 * 45",
              "is_generative": false
            },
            {
              "goal": "OPEN_APPLICATION",
              "target_name": "Notepad",
              "target_role": "window",
              "content": null,
              "is_generative": false
            },
            {
              "goal": "WRITE_TEXT",
              "target_name": "Notepad",
              "target_role": "edit",
              "content": "Result of calculation is 5,400",
              "is_generative": false
            }
          ]
        }
        ''',
        model_id="test-qwen2.5",
    ))

    result = await decomposer.decompose("open calculator, compute 120 * 45, then open notepad and write the result")

    assert result is not None
    assert result.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(result.intents) == 4

    goals = [i.goal for i in result.intents]
    assert goals == [TaskGoal.OPEN_APPLICATION, TaskGoal.CALCULATE, TaskGoal.OPEN_APPLICATION, TaskGoal.WRITE_TEXT]


    # Verify target references
    assert result.intents[0].target.identifier == "Calculator"
    assert result.intents[1].constraints.content == "120 * 45"
    assert result.intents[2].target.identifier == "Notepad"
    assert result.intents[3].constraints.content == "Result of calculation is 5,400"


@pytest.mark.asyncio
async def test_llm_plan_synthesizer_builds_validated_dag_steps(mock_msm):
    """Test LLMPlanSynthesizer builds dependency-aware PlanStep DAG from LLM JSON."""
    synthesizer = LLMPlanSynthesizer(model_session_manager=mock_msm)

    mock_msm.chat = AsyncMock(return_value=ModelChatResponse(
        content='''
        {
          "thought": "Synthesizing full multi-app workflow with dependencies",
          "steps": [
            {
              "step_id": "step_1",
              "action_type": "ENSURE_APPLICATION_OPEN",
              "description": "Ensure Calculator is open",
              "target_app": "Calculator",
              "target_role": "window",
              "content": null,
              "dependencies": []
            },
            {
              "step_id": "step_2",
              "action_type": "ACTIVATE_CONTROL",
              "description": "Perform calculation in Calculator",
              "target_app": "Calculator",
              "target_role": "button",
              "content": "25 * 4 =",
              "dependencies": ["step_1"]
            },
            {
              "step_id": "step_3",
              "action_type": "ENSURE_APPLICATION_OPEN",
              "description": "Ensure Notepad is open",
              "target_app": "Notepad",
              "target_role": "window",
              "content": null,
              "dependencies": ["step_2"]
            },
            {
              "step_id": "step_4",
              "action_type": "ENTER_TEXT",
              "description": "Type calculation result into Notepad",
              "target_app": "Notepad",
              "target_role": "edit",
              "content": "Total: 100",
              "dependencies": ["step_3"]
            }
          ]
        }
        ''',
        model_id="test-qwen2.5",
    ))

    engine = TaskUnderstandingEngine()
    dummy_understanding = engine.understand("Calculate 25 * 4 and paste result to notepad")

    steps = await synthesizer.synthesize_plan(dummy_understanding)

    assert steps is not None
    assert len(steps) == 4

    # Verify action types
    assert steps[0].action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert steps[1].action_type == PlanActionType.ACTIVATE_CONTROL
    assert steps[2].action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert steps[3].action_type == PlanActionType.ENTER_TEXT

    # Verify zero screen coordinates invariant
    for s in steps:
        assert not hasattr(s, "x")
        assert not hasattr(s, "y")
        assert s.deferred_grounding is not None

    # Verify dependencies form a sequence
    assert steps[1].dependencies == [steps[0].step_id]
    assert steps[2].dependencies == [steps[1].step_id]
    assert steps[3].dependencies == [steps[2].step_id]


@pytest.mark.asyncio
async def test_planner_async_fallback_to_llm_synthesis(mock_msm):
    """Test TaskPlanningEngine.plan_task_async falls back to LLM synthesis when deterministic plan is unsupported."""
    synthesizer = LLMPlanSynthesizer(model_session_manager=mock_msm)
    planner = TaskPlanningEngine(llm_synthesizer=synthesizer)

    mock_msm.chat = AsyncMock(return_value=ModelChatResponse(
        content='''
        {
          "thought": "Multi-step complex synthesis",
          "steps": [
            {
              "step_id": "s1",
              "action_type": "ENSURE_APPLICATION_OPEN",
              "description": "Launch App",
              "target_app": "Browser",
              "target_role": "window",
              "dependencies": []
            },
            {
              "step_id": "s2",
              "action_type": "SEARCH_QUERY",
              "description": "Search stocks",
              "target_app": "Browser",
              "target_role": "edit",
              "content": "NVDA stock price",
              "dependencies": ["s1"]
            }
          ]
        }
        ''',
        model_id="test-qwen2.5",
    ))

    # An unsupported/complex raw task prompt
    plan = await planner.plan_task_async("Fetch latest stock price for NVDA and save it")

    assert plan is not None
    assert plan.status == PlanStatus.VALID
    assert len(plan.steps) == 2
    assert plan.steps[0].action_type == PlanActionType.ENSURE_APPLICATION_OPEN
    assert plan.steps[1].action_type == PlanActionType.SEARCH_QUERY


@pytest.mark.asyncio
async def test_understanding_async_cognitive_fallback(mock_msm):
    """Test TaskUnderstandingEngine.understand_async seamlessly uses LLM when regex returns unsupported."""
    decomposer = LLMTaskDecomposer(model_session_manager=mock_msm)
    understanding_engine = TaskUnderstandingEngine(llm_decomposer=decomposer)

    mock_msm.chat = AsyncMock(return_value=ModelChatResponse(
        content='''
        {
          "thought": "Natural language query decomposition",
          "intents": [
            {
              "goal": "OPEN_APPLICATION",
              "target_name": "Spotify",
              "target_role": "window",
              "content": null,
              "is_generative": false
            },
            {
              "goal": "SEARCH",
              "target_name": "Spotify",
              "target_role": "edit",
              "content": "Chill Jazz",
              "is_generative": false
            }
          ]
        }
        ''',
        model_id="test-qwen2.5",
    ))

    # A complex/unsupported prompt for regex
    res = await understanding_engine.understand_async("Can you please put on some Chill Jazz music in Spotify?")

    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 2
    assert res.intents[0].goal == TaskGoal.OPEN_APPLICATION
    assert res.intents[0].target.identifier == "Spotify"
    assert res.intents[1].goal == TaskGoal.SEARCH
    assert res.intents[1].constraints.content == "Chill Jazz"

