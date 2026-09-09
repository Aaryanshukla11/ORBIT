"""Unit tests for FeasibilityAnalyzer."""

import pytest
from orbit.runtime.capabilities.feasibility import FeasibilityAnalyzer
from orbit.runtime.capabilities.models import FeasibilityStatus
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.cognitive.models import StructuredObjective


def test_feasibility_analyzer_permits_cube():
    analyzer = FeasibilityAnalyzer()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Open Paint and draw a cube",
        end_condition="canvas_has_cube",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "cube"},
    )
    assessment = analyzer.evaluate_feasibility(obj)

    assert assessment.is_feasible is True
    assert assessment.status == FeasibilityStatus.FEASIBLE
    assert assessment.matched_strategy is not None
    assert assessment.matched_strategy.strategy_id == "STRAT_GEOMETRIC_PRIMITIVES"


def test_feasibility_analyzer_rejects_portrait_of_boy_without_image_gen():
    analyzer = FeasibilityAnalyzer()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "portrait_of_boy"},
    )
    assessment = analyzer.evaluate_feasibility(obj)

    assert assessment.is_feasible is False
    assert assessment.status == FeasibilityStatus.INSUFFICIENT_CAPABILITY
    assert assessment.matched_strategy is None
    assert "IMAGE_GENERATE_AND_INSERT" in assessment.missing_capabilities
    assert "NOT FEASIBLY EXECUTABLE" in assessment.explanation
    assert len(assessment.suggested_alternatives) > 0


def test_feasibility_analyzer_permits_text_entry():
    analyzer = FeasibilityAnalyzer()
    obj = StructuredObjective(
        raw_prompt="Open Notepad and type 'Hello World'",
        user_goal="Open Notepad and type 'Hello World'",
        end_condition="notepad_has_text",
        parameters={"app_name": "Notepad", "action_type": "type", "text": "Hello World"},
    )
    assessment = analyzer.evaluate_feasibility(obj)

    assert assessment.is_feasible is True
    assert assessment.status == FeasibilityStatus.FEASIBLE
    assert "TYPE_TEXT" in assessment.available_capabilities
