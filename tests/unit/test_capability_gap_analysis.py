"""Unit tests for CapabilityGapReport and structured gap analysis."""

import pytest
from orbit.runtime.capabilities.feasibility import FeasibilityAnalyzer
from orbit.runtime.capabilities.models import FeasibilityStatus
from orbit.runtime.cognitive.models import StructuredObjective


def test_capability_gap_report_generated_for_unexecutable_goal():
    analyzer = FeasibilityAnalyzer()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a realistic portrait of a boy",
        user_goal="Open Paint and draw a realistic portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw"},
    )
    assessment = analyzer.evaluate_feasibility(obj)

    assert assessment.is_feasible is False
    assert assessment.status == FeasibilityStatus.INSUFFICIENT_CAPABILITY
    assert assessment.capability_gap is not None

    gap = assessment.capability_gap
    assert gap.requested_goal == "Open Paint and draw a realistic portrait of a boy"
    assert len(gap.attempted_strategies) >= 3
    assert len(gap.missing_capabilities) > 0
    assert "IMAGE_GENERATE_AND_INSERT" in gap.missing_capabilities
    assert len(gap.unmet_requirements) > 0
    assert len(gap.recommended_prerequisites) > 0
    assert "image-generation model" in gap.recommended_prerequisites[0].lower() or "image generation" in gap.recommended_prerequisites[0].lower()


def test_feasible_goal_has_no_capability_gap():
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
    assert assessment.capability_gap is None
