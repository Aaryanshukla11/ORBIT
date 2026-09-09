"""Unit tests for CompositeCapability and CapabilityCompositionEngine."""

import pytest
from orbit.runtime.capabilities.composition import CapabilityCompositionEngine, CompositeCapability
from orbit.runtime.capabilities.models import CapabilityCategory, CapabilitySource, StrategyStage
from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
from orbit.runtime.cognitive.models import StructuredObjective


def test_composite_capability_viability_logic():
    composite = CompositeCapability(
        capability_id="COMPOSITE_TEST",
        name="Test Composite Workflow",
        description="Test description",
        category=CapabilityCategory.CREATIVE_VISUAL,
        source=CapabilitySource.COMPOSITE,
        composed_from=["CAP_A", "CAP_B|CAP_C", "CAP_D"],
        composition_stages=[
            StrategyStage(
                stage_index=0,
                name="STAGE_1",
                capability_id="CAP_A",
                description="desc",
                expected_outcome="outcome",
            )
        ],
    )

    # Missing CAP_D
    available_1 = {"CAP_A", "CAP_B"}
    assert composite.is_viable_with(available_1) is False
    assert "CAP_D" in composite.get_missing_constituents(available_1)

    # All available with alternative CAP_C
    available_2 = {"CAP_A", "CAP_C", "CAP_D"}
    assert composite.is_viable_with(available_2) is True
    assert len(composite.get_missing_constituents(available_2)) == 0


def test_composition_engine_finds_composites_for_requirements():
    engine = CapabilityCompositionEngine()
    extractor = GoalRequirementExtractor()

    # Creative drawing objective
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw"},
    )
    req_set = extractor.extract_requirements(obj)

    composites = engine.find_compositions_for_requirements(req_set, available_cap_ids={"LAUNCH_APPLICATION"})
    assert len(composites) >= 1
    comp_ids = {c.capability_id for c in composites}
    assert "COMPOSITE_IMAGE_GEN_AND_INSERT" in comp_ids
    # Primitive drawing should be excluded because req_set requires HIGH_FIDELITY_SEMANTIC
    assert "COMPOSITE_GEOMETRIC_DRAWING" not in comp_ids
