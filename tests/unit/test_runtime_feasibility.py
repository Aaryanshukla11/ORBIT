"""Unit tests for RuntimeFeasibilityEvaluator."""

import pytest
from orbit.runtime.cognitive.models import CurrentStateObservation, SubObjective
from orbit.runtime.cognitive.runtime_feasibility import (
    RuntimeFeasibilityEvaluator,
    RuntimeFeasibilityResult,
)
from orbit.runtime.environment.registry import (
    EnvironmentProviderRegistry,
    get_default_environment_registry,
)
from orbit.runtime.world_model.model import AgentWorldModel


@pytest.mark.asyncio
async def test_feasible_subgoal():
    evaluator = RuntimeFeasibilityEvaluator(check_network=False)
    wm = AgentWorldModel()
    sub = SubObjective(
        title="Type report into editor",
        description="Write text into open document",
    )
    res = await evaluator.evaluate(sub, wm)
    assert res.is_feasible is True
    assert res.blocking_reason is None


@pytest.mark.asyncio
async def test_locked_desktop_blocks():
    evaluator = RuntimeFeasibilityEvaluator(check_network=False)
    wm = AgentWorldModel(is_desktop_locked=True)
    sub = SubObjective(title="Do anything")
    res = await evaluator.evaluate(sub, wm)
    assert res.is_feasible is False
    assert "Desktop is locked" in res.blocking_reason
    assert "unlocked_desktop" in res.missing_resources


@pytest.mark.asyncio
async def test_login_detection_blocks():
    evaluator = RuntimeFeasibilityEvaluator(check_network=False)
    wm = AgentWorldModel(active_window_title="Sign in to your Microsoft Account")
    sub = SubObjective(title="Navigate internal portal")
    res = await evaluator.evaluate(sub, wm)
    assert res.is_feasible is False
    assert "credentials" in res.blocking_reason.lower()
    assert "user_credentials" in res.missing_resources


@pytest.mark.asyncio
async def test_captcha_detection_blocks():
    evaluator = RuntimeFeasibilityEvaluator(check_network=False)
    wm = AgentWorldModel()
    obs = CurrentStateObservation(
        ocr_tokens=["Please", "verify", "you", "are", "human", "CAPTCHA"],
    )
    sub = SubObjective(title="Submit form")
    res = await evaluator.evaluate(sub, wm, observation=obs)
    assert res.is_feasible is False
    assert "CAPTCHA" in res.blocking_reason
    assert "human_verification" in res.missing_resources


@pytest.mark.asyncio
async def test_provider_registry_check():
    evaluator = RuntimeFeasibilityEvaluator(check_network=False)
    wm = AgentWorldModel()
    empty_registry = EnvironmentProviderRegistry()

    sub = SubObjective(title="Create spreadsheet with comparison")
    # With empty registry, spreadsheet should be flagged
    res = await evaluator.evaluate(sub, wm, provider_registry=empty_registry)
    assert res.is_feasible is False
    assert "spreadsheet provider" in res.blocking_reason.lower()

    # With default registry containing CSV fallback, should be feasible
    default_reg = get_default_environment_registry()
    res_ok = await evaluator.evaluate(sub, wm, provider_registry=default_reg)
    assert res_ok.is_feasible is True
