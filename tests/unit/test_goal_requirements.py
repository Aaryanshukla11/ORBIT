"""Unit tests for GoalRequirementExtractor and GoalRequirementSet."""

import pytest
from orbit.runtime.capabilities.models import CapabilityCategory, GoalRequirementSet
from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
from orbit.runtime.cognitive.models import StructuredObjective


def test_extract_requirements_primitive_geometry():
    extractor = GoalRequirementExtractor()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Open Paint and draw a cube",
        end_condition="canvas_has_cube",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "cube"},
    )
    req_set = extractor.extract_requirements(obj)

    assert req_set.target_domain == "creative_drawing"
    assert req_set.required_fidelity == "PRIMITIVE"

    req_types = [r.requirement_type for r in req_set.requirements]
    assert "APPLICATION_LIFECYCLE" in req_types
    assert "CONTENT_CREATION" in req_types
    assert "STATE_VERIFICATION" in req_types

    content_req = next(r for r in req_set.requirements if r.requirement_type == "CONTENT_CREATION")
    assert content_req.parameters.get("required_fidelity") == "PRIMITIVE"
    assert content_req.parameters.get("visual_type") == "geometric_primitive"
    assert content_req.parameters.get("shape") == "cube"


def test_extract_requirements_high_fidelity_portrait():
    extractor = GoalRequirementExtractor()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "portrait_of_boy"},
    )
    req_set = extractor.extract_requirements(obj)

    assert req_set.target_domain == "creative_drawing"
    assert req_set.required_fidelity == "HIGH_FIDELITY_SEMANTIC"

    content_req = next(r for r in req_set.requirements if r.requirement_type == "CONTENT_CREATION")
    assert content_req.parameters.get("required_fidelity") == "HIGH_FIDELITY_SEMANTIC"
    assert content_req.parameters.get("visual_type") == "portrait"
    assert content_req.parameters.get("semantic_subject") == "portrait" or content_req.parameters.get("semantic_subject") == "boy"
    assert "fidelity_level:recognizable_semantic_representation" in content_req.success_criteria


def test_extract_requirements_text_entry():
    extractor = GoalRequirementExtractor()
    obj = StructuredObjective(
        raw_prompt="Open Notepad and type 'ORBIT Vision Test 123'",
        user_goal="Open Notepad and type 'ORBIT Vision Test 123'",
        end_condition="notepad_has_text",
        parameters={"app_name": "Notepad", "action_type": "type", "text": "ORBIT Vision Test 123"},
    )
    req_set = extractor.extract_requirements(obj)

    assert req_set.target_domain == "document_editing"
    req_types = [r.requirement_type for r in req_set.requirements]
    assert "APPLICATION_LIFECYCLE" in req_types
    assert "DATA_INPUT" in req_types

    input_req = next(r for r in req_set.requirements if r.requirement_type == "DATA_INPUT")
    assert input_req.parameters.get("text") == "ORBIT Vision Test 123"
