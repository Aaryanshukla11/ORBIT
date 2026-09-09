"""Unit tests for CapabilityMatcher."""

import pytest
from orbit.runtime.capabilities.matcher import CapabilityMatcher
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.cognitive.models import StructuredObjective


def test_matcher_basic_geometry():
    matcher = CapabilityMatcher()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Open Paint and draw a cube",
        end_condition="canvas_has_cube",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "cube"},
    )
    report = matcher.match_objective(obj)

    assert "LAUNCH_APPLICATION" in report.required_capability_ids
    assert "DRAW_BASIC_GEOMETRY" in report.required_capability_ids
    assert report.semantic_target_type == "geometric_primitive"
    assert report.is_fully_supported is True
    assert len(report.missing_capability_ids) == 0
    assert len(report.triggered_limitations) == 0


def test_matcher_detects_portrait_limitation_and_requires_image_gen():
    matcher = CapabilityMatcher()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "portrait_of_boy"},
    )
    report = matcher.match_objective(obj)

    assert report.semantic_target_type == "complex_artistic_visual"
    # Complex visual goal requires IMAGE_GENERATE_AND_INSERT
    assert "IMAGE_GENERATE_AND_INSERT" in report.required_capability_ids
    # By default, IMAGE_GENERATE_AND_INSERT is not available in registry
    assert "IMAGE_GENERATE_AND_INSERT" in report.missing_capability_ids
    assert report.is_fully_supported is False
