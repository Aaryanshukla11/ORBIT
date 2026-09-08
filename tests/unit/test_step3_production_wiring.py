"""Unit & Production Wiring Tests for Step 3 Multimodal Perception Integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.models.common import BoundingBox
from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.cognitive.observer import CurrentStateObserver
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRToken,
    PerceivedElement,
    ScreenshotObservation,
    UIElementObservation,
    WindowObservation,
)
from orbit.runtime.perception.observer import DesktopObserver
from orbit.runtime.targeting import EvidenceBasedTargetLocator, TargetIntent, TargetStrategy


@pytest.mark.asyncio
async def test_canonical_desktop_observation_attached_to_current_state_observation():
    """Verify that CurrentStateObserver attaches full canonical DesktopObservation."""
    observer = CurrentStateObserver()
    objective = StructuredObjective(
        raw_prompt="Open Notepad and type test",
        user_goal="Open Notepad",
        end_condition="notepad_is_open",
        target_entities=["notepad"],
        parameters={"app_name": "notepad"},
    )

    obs = await observer.observe(objective)
    assert isinstance(obs, CurrentStateObservation)
    assert obs.desktop_observation is not None
    assert isinstance(obs.desktop_observation, DesktopObservation)
    assert obs.observation_id == obs.desktop_observation.observation_id
    assert obs.uia_status in ("SUCCESS", "EMPTY", "UNAVAILABLE", "FAILED")
    assert obs.ocr_status in ("SUCCESS", "EMPTY", "UNAVAILABLE", "FAILED")
    assert obs.screenshot_status in ("SUCCESS", "FALLBACK", "FAILED")
    assert obs.screen_summary != ""


@pytest.mark.asyncio
async def test_fresh_observation_invariant_in_action_cycle():
    """Verify that pre-action observation ID != post-action observation ID."""
    mock_observer = MagicMock(spec=CurrentStateObserver)
    obs1 = CurrentStateObservation(
        observation_id="obs_pre_111",
        active_window_hwnd=1001,
        active_window_title="Desktop",
        target_app_exists=False,
    )
    obs2 = CurrentStateObservation(
        observation_id="obs_post_222",
        active_window_hwnd=2002,
        active_window_title="Notepad",
        target_app_exists=True,
        target_app_is_active=True,
        visible_windows=[{"hwnd": 2002, "title": "Notepad", "process_name": "notepad.exe"}],
    )
    obs3 = CurrentStateObservation(
        observation_id="obs_final_333",
        active_window_hwnd=2002,
        active_window_title="Notepad",
        target_app_exists=True,
        target_app_is_active=True,
        visible_windows=[{"hwnd": 2002, "title": "Notepad", "process_name": "notepad.exe"}],
    )
    mock_observer.observe = AsyncMock(return_value=obs2)
    mock_observer._matches_app = MagicMock(return_value=True)

    loop = AgentExecutionLoop(observer=mock_observer)
    objective = StructuredObjective(
        raw_prompt="Open Notepad",
        user_goal="Open Notepad",
        end_condition="notepad_is_open",
        target_entities=["notepad"],
    )

    action = AbstractAction(
        action_type=AbstractActionType.LAUNCH_APPLICATION,
        parameters={"application_name": "notepad"},
        outcome_contract=ActionOutcomeContract(
            expected_state_transition="Notepad launched",
            verification_strategy=VerificationStrategy.WIN32_WINDOW,
        ),
    )

    exec_res, post_obs = await loop._execute_and_verify_action(action, obs1, objective)
    assert exec_res.dispatch_success is True
    assert exec_res.expected_effect_observed is True
    assert obs1.observation_id != post_obs.observation_id
    assert post_obs.observation_id == "obs_post_222"


@pytest.mark.asyncio
async def test_explicit_modality_status_representation():
    """Verify distinct representation of SUCCESS, EMPTY, UNAVAILABLE, FAILED across UIA & OCR."""
    mock_win_obs = MagicMock()
    mock_win_obs.observe_windows.return_value = (None, [])

    mock_ss_obs = MagicMock()
    mock_ss_obs.capture = AsyncMock(
        return_value=ScreenshotObservation(width=1920, height=1080, raw_bytes=b"dummy")
    )

    # 1. Test UIA empty vs failed vs unavailable
    mock_uia_empty = MagicMock()
    mock_uia_empty.observe_elements.return_value = (None, [])

    desktop_observer = DesktopObserver(
        window_observer=mock_win_obs,
        screenshot_observer=mock_ss_obs,
        uia_observer=mock_uia_empty,
    )

    obs_empty = await desktop_observer.observe_desktop(include_uia=True, include_ocr=False)
    assert obs_empty.uia_status == "EMPTY"
    assert obs_empty.ocr_status == "UNAVAILABLE"

    # 2. Test UIA failed
    mock_uia_failed = MagicMock()
    mock_uia_failed.observe_elements.side_effect = RuntimeError("COM connection failed")

    desktop_observer_failed = DesktopObserver(
        window_observer=mock_win_obs,
        screenshot_observer=mock_ss_obs,
        uia_observer=mock_uia_failed,
    )
    obs_failed = await desktop_observer_failed.observe_desktop(include_uia=True, include_ocr=False)
    assert obs_failed.uia_status == "FAILED"


def test_target_locator_grounding_from_desktop_observation():
    """Verify EvidenceBasedTargetLocator resolves targets directly from DesktopObservation."""
    locator = EvidenceBasedTargetLocator()

    target_uia = UIElementObservation(
        element_id="uia_save_btn",
        name="Save",
        control_type="Button",
        bounding_box=BoundingBox(left=100, top=200, width=80, height=30),
    )
    window_obs = WindowObservation(
        hwnd=5555,
        title="Notepad - Untitled",
        window_class="Notepad",
        window_bounds=BoundingBox(left=50, top=50, width=800, height=600),
        client_bounds=BoundingBox(left=50, top=80, width=800, height=570),
        is_foreground=True,
        is_visible=True,
    )

    desktop_obs = DesktopObservation(
        observation_id="obs_grounding_test",
        screen_width=1920,
        screen_height=1080,
        foreground_window=window_obs,
        visible_windows=[window_obs],
        uia_elements=[target_uia],
    )

    # 1. Resolve SemanticTarget via accessibility strategy
    sem_target = SemanticTarget(name="Save", role="button")
    res = locator.locate_target(sem_target, desktop_obs)

    assert res.status.value == "RESOLVED"
    assert res.target is not None
    assert 138 <= res.target.safe_point.x <= 142
    assert 210 <= res.target.safe_point.y <= 220

    # 2. Resolve Window via window strategy
    win_intent = TargetIntent(name="Notepad", strategy=TargetStrategy.WINDOW_TITLE)
    res_win = locator.locate_target(win_intent, desktop_obs)
    assert res_win.status.value == "RESOLVED"
    assert res_win.target is not None
