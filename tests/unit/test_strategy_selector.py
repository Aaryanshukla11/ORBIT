"""Unit tests for StrategySelector."""

import pytest
from orbit.runtime.capabilities.models import Capability
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.capabilities.strategy_selector import StrategySelector
from orbit.runtime.cognitive.models import StructuredObjective


def test_strategy_selector_picks_geometric_for_cube():
    selector = StrategySelector()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a cube",
        user_goal="Open Paint and draw a cube",
        end_condition="canvas_has_cube",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "cube"},
    )
    result = selector.select_strategy(obj)

    assert result.is_executable is True
    assert result.selected_strategy is not None
    assert result.selected_strategy.strategy_id == "STRAT_GEOMETRIC_PRIMITIVES"
    assert result.selected_strategy.estimated_success_probability >= 0.85


def test_strategy_selector_rejects_portrait_when_image_gen_unavailable():
    # Default registry has IMAGE_GENERATE_AND_INSERT as is_available=False
    selector = StrategySelector()
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "portrait_of_boy"},
    )
    result = selector.select_strategy(obj)

    assert result.is_executable is False
    assert result.selected_strategy is None
    assert "No viable strategy could achieve" in result.selection_reasoning or "Semantic adequacy failure" in result.selection_reasoning


def test_strategy_selector_picks_image_gen_when_available():
    registry = CapabilityRegistry()
    # Enable image generation capability
    img_cap = registry.get("IMAGE_GENERATE_AND_INSERT")
    assert img_cap is not None
    img_cap.is_available = True

    selector = StrategySelector(registry=registry)
    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw", "shape": "portrait_of_boy"},
    )
    result = selector.select_strategy(obj)

    assert result.is_executable is True
    assert result.selected_strategy is not None
    assert result.selected_strategy.strategy_id == "STRAT_IMAGE_GEN_AND_INSERT"
    assert result.selected_strategy.estimated_success_probability > 0.90
