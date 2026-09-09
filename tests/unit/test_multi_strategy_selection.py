"""Unit tests for Multi-Strategy Generation and Semantic Coverage Evaluation."""

import pytest
from unittest.mock import MagicMock

from orbit.runtime.capabilities.environment_discovery import EnvironmentCapabilityDiscovery
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
from orbit.runtime.capabilities.strategy_selector import StrategySelector
from orbit.runtime.cognitive.models import StructuredObjective


def test_multi_strategy_generation_for_portrait():
    registry = CapabilityRegistry()
    discovery = EnvironmentCapabilityDiscovery()
    selector = StrategySelector(registry=registry, environment_discovery=discovery)

    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw"},
    )
    result = selector.select_strategy(obj)

    # Must generate multiple candidate strategies (e.g. geometric, generative, browser, local app)
    assert len(result.candidate_strategies) >= 3
    strat_ids = {s.strategy_id for s in result.candidate_strategies}
    assert "STRAT_GEOMETRIC_PRIMITIVES" in strat_ids
    assert "STRAT_IMAGE_GEN_AND_INSERT" in strat_ids

    # Strategy 1 (geometric primitive) must be disqualified due to semantic coverage failure
    geom_strat = next(s for s in result.candidate_strategies if s.strategy_id == "STRAT_GEOMETRIC_PRIMITIVES")
    assert geom_strat.semantic_goal_coverage < 0.10
    assert "Semantic adequacy failure" in (geom_strat.rejection_reason or "")

    # Because generative model is not available by default, no strategy is executable
    assert result.is_executable is False
    assert result.selected_strategy is None
    assert "No viable strategy could achieve" in result.selection_reasoning


def test_alternative_strategy_selection_when_generative_model_enabled():
    registry = CapabilityRegistry()
    # Mock environment with active generative image model
    mock_msm = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.capabilities = ["text_generation", "image_generation"]
    mock_msm.get_active_context.return_value = mock_ctx
    mock_msm.get_registered_providers.return_value = []

    discovery = EnvironmentCapabilityDiscovery(model_session_manager=mock_msm)
    selector = StrategySelector(registry=registry, environment_discovery=discovery)

    obj = StructuredObjective(
        raw_prompt="Open Paint and draw a portrait of a boy",
        user_goal="Open Paint and draw a portrait of a boy",
        end_condition="canvas_has_boy_portrait",
        parameters={"app_name": "Paint", "action_type": "draw"},
    )
    result = selector.select_strategy(obj)

    # Generative AI strategy must be selected!
    assert result.is_executable is True
    assert result.selected_strategy is not None
    assert result.selected_strategy.strategy_id == "STRAT_IMAGE_GEN_AND_INSERT"
    assert result.selected_strategy.semantic_goal_coverage >= 0.90
    assert result.selected_strategy.estimated_success_probability >= 0.90
    assert len(result.selected_strategy.stages) >= 3


def test_strategy_selection_for_basic_cube():
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
    assert result.selected_strategy.semantic_goal_coverage >= 0.90
    assert result.selected_strategy.estimated_success_probability >= 0.85
