"""Unit tests for the LLM Intent Interpreter in the Cognitive Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.cognitive.interpreter import LLMIntentInterpreter
from orbit.runtime.cognitive.models import StructuredObjective
from orbit.runtime.models.models import ModelGenerateResponse


@pytest.mark.asyncio
async def test_interpret_heuristic_drawing_cube():
    interpreter = LLMIntentInterpreter()
    obj = await interpreter.interpret("Open Paint and draw a cube")

    assert isinstance(obj, StructuredObjective)
    assert "cube" in obj.end_condition
    assert "mspaint" in obj.target_entities or "canvas" in obj.target_entities
    assert obj.parameters.get("action_type") == "draw"
    assert obj.parameters.get("shape") == "cube"
    assert obj.parameters.get("app_name") == "mspaint"


@pytest.mark.asyncio
async def test_interpret_heuristic_typing_notepad():
    interpreter = LLMIntentInterpreter()
    obj = await interpreter.interpret('Open Notepad and type "Hello World"')

    assert isinstance(obj, StructuredObjective)
    assert obj.parameters.get("action_type") == "type"
    assert obj.parameters.get("text") == "Hello World"
    assert "notepad" in obj.target_entities


@pytest.mark.asyncio
async def test_interpret_heuristic_with_constraints():
    interpreter = LLMIntentInterpreter()
    obj = await interpreter.interpret("Open Notepad and type test, do not close the window")

    assert isinstance(obj, StructuredObjective)
    assert len(obj.constraints) > 0
    assert any("not close" in c for c in obj.constraints)


@pytest.mark.asyncio
async def test_interpret_with_active_llm():
    mock_session_mgr = MagicMock()
    mock_session_mgr.get_active_context.return_value = MagicMock(model_id="mock-qwen-7b")
    mock_session_mgr.generate = AsyncMock(
        return_value=ModelGenerateResponse(
            model_id="mock-qwen-7b",
            content='''{
              "user_goal": "Draw a 3D cube in Microsoft Paint",
              "end_condition": "canvas_has_cube_drawing",
              "target_entities": ["mspaint", "canvas"],
              "constraints": ["fail_closed_if_blank"],
              "parameters": {
                 "app_name": "mspaint",
                 "action_type": "draw",
                 "shape": "cube"
              }
            }'''
        )
    )

    interpreter = LLMIntentInterpreter(model_session_manager=mock_session_mgr)
    obj = await interpreter.interpret("Draw a cube in Paint")

    assert obj.user_goal == "Draw a 3D cube in Microsoft Paint"
    assert obj.end_condition == "canvas_has_cube_drawing"
    assert "mspaint" in obj.target_entities
    assert "fail_closed_if_blank" in obj.constraints
    assert obj.parameters["shape"] == "cube"
