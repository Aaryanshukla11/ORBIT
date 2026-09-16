"""Unit tests for SemanticDiffEngine (Phase 3D)."""

from PIL import Image, ImageDraw
import pytest

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.models import CurrentStateObservation
from orbit.runtime.verification.semantic_diff_engine import (
    SemanticDiffEngine,
    SemanticStateDiff,
)


def test_semantic_diff_engine_detects_pixel_changes():
    """Verify engine detects visual pixel deltas and computes changed bounding regions."""
    engine = SemanticDiffEngine(pixel_change_threshold=0.001)

    img1 = Image.new("RGB", (400, 300), color="white")
    img2 = img1.copy()

    # Draw a blue rectangle on img2
    draw = ImageDraw.Draw(img2)
    draw.rectangle([(50, 50), (150, 150)], fill="blue")

    act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="Canvas"))
    pre_obs = CurrentStateObservation(observation_id="pre_1")
    post_obs = CurrentStateObservation(observation_id="post_1")

    diff = engine.compute_diff(
        action=act,
        pre_obs=pre_obs,
        post_obs=post_obs,
        pre_image=img1,
        post_image=img2,
    )

    assert isinstance(diff, SemanticStateDiff)
    assert diff.is_visual_changed is True
    assert diff.visual_change_ratio > 0.0
    assert len(diff.changed_regions) >= 1
    box = diff.changed_regions[0]
    assert box.left == 50
    assert box.top == 50
    assert box.width == 101
    assert box.height == 101


def test_semantic_diff_engine_detects_ocr_text_delta():
    """Verify engine extracts added and removed OCR tokens."""
    engine = SemanticDiffEngine()

    act = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "Astra6 Agent"},
    )

    pre_obs = CurrentStateObservation(
        observation_id="pre_ocr",
        ocr_tokens=["Document", "Untitled"],
    )
    post_obs = CurrentStateObservation(
        observation_id="post_ocr",
        ocr_tokens=["Document", "Untitled", "Astra6", "Agent"],
    )

    diff = engine.compute_diff(action=act, pre_obs=pre_obs, post_obs=post_obs)

    assert "Astra6" in diff.text_added
    assert "Agent" in diff.text_added
    assert len(diff.text_removed) == 0
    assert diff.confidence_score >= 0.90
    assert "verified in OCR text delta" in diff.verification_rationale


def test_semantic_diff_engine_detects_focus_and_dialog_events():
    """Verify engine detects foreground window switches and modal dialog appearance."""
    engine = SemanticDiffEngine()

    act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="Save As"))

    pre_obs = CurrentStateObservation(
        observation_id="pre_dlg",
        active_window_hwnd=100,
        active_window_title="Editor",
        visible_windows=[{"hwnd": 100, "title": "Editor", "class_name": "Notepad"}],
    )
    post_obs = CurrentStateObservation(
        observation_id="post_dlg",
        active_window_hwnd=200,
        active_window_title="Save As Modal",
        visible_windows=[
            {"hwnd": 100, "title": "Editor", "class_name": "Notepad"},
            {"hwnd": 200, "title": "Save As Modal", "class_name": "#32770"},
        ],
    )

    diff = engine.compute_diff(action=act, pre_obs=pre_obs, post_obs=post_obs)

    assert diff.focus_changed is True
    assert diff.pre_hwnd == 100
    assert diff.post_hwnd == 200
    assert diff.dialog_opened is True
    assert diff.dialog_closed is False
    assert diff.confidence_score >= 0.90
