"""Unit tests for Step 3: Canonical Desktop Perception Models and Provenance."""

from datetime import datetime, timezone
import pytest

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRToken,
    PerceivedElement,
    PerceptionEvidence,
    ScreenshotObservation,
    UIElementObservation,
    VisualRegion,
    VisualRegionType,
    WindowObservation,
)


def test_window_observation_model():
    """Verify WindowObservation correctly represents Win32 window metadata and bounds."""
    win = WindowObservation(
        hwnd=1024,
        title="Untitled - Notepad",
        window_class="Notepad",
        is_foreground=True,
        is_visible=True,
        is_minimized=False,
        is_maximized=False,
        window_bounds=BoundingBox(left=100, top=100, width=800, height=600),
        client_bounds=BoundingBox(left=108, top=130, width=784, height=562),
        process_id=4512,
        process_name="notepad.exe",
    )
    assert win.hwnd == 1024
    assert win.title == "Untitled - Notepad"
    assert win.is_foreground is True
    assert win.window_bounds.width == 800
    assert win.process_name == "notepad.exe"


def test_screenshot_observation_model():
    """Verify ScreenshotObservation holds visual dimensions and base64 reference."""
    ss = ScreenshotObservation(
        width=1920,
        height=1080,
        image_base64="data:image/jpeg;base64,mockbase64data",
        capture_method="DXGI",
    )
    assert ss.width == 1920
    assert ss.height == 1080
    assert ss.capture_method == "DXGI"
    assert ss.image_base64.startswith("data:image")


def test_ocr_token_model():
    """Verify OCRToken preserves token text, confidence, and screen bounding box."""
    tok = OCRToken(
        text="File",
        confidence=0.98,
        bounding_box=BoundingBox(left=110, top=135, width=30, height=18),
        source="WINDOWS_OCR",
    )
    assert tok.text == "File"
    assert tok.confidence == 0.98
    assert tok.bounding_box.left == 110


def test_ui_element_observation_model():
    """Verify UIElementObservation represents accessibility properties."""
    el = UIElementObservation(
        name="Text Editor",
        control_type="Document",
        automation_id="15",
        class_name="Edit",
        is_enabled=True,
        is_visible=True,
        has_keyboard_focus=True,
        bounding_box=BoundingBox(left=108, top=160, width=784, height=530),
        parent_context="Untitled - Notepad",
        hwnd=1024,
    )
    assert el.name == "Text Editor"
    assert el.control_type == "Document"
    assert el.has_keyboard_focus is True


def test_visual_region_model():
    """Verify VisualRegion captures canvas and window regions."""
    vreg = VisualRegion(
        region_type=VisualRegionType.CANVAS,
        bounds=BoundingBox(left=50, top=140, width=900, height=600),
        confidence=0.95,
        description="Paint Drawing Canvas Surface",
        source="GEOMETRIC_INFERENCE",
    )
    assert vreg.region_type == VisualRegionType.CANVAS
    assert vreg.confidence == 0.95


def test_perceived_element_and_evidence_provenance():
    """Verify PerceivedElement captures multi-source evidence and fused confidence."""
    evidence = PerceptionEvidence(
        evidence_sources=["UIA", "OCR"],
        confidence=0.99,
        matched_tokens=["Save"],
        matched_uia_role="Button",
    )
    elem = PerceivedElement(
        name="Save",
        role="button",
        context="Notepad",
        bounds=BoundingBox(left=200, top=140, width=60, height=25),
        evidence=evidence,
        confidence=0.99,
    )
    assert elem.name == "Save"
    assert elem.role == "button"
    assert "UIA" in elem.evidence.evidence_sources
    assert "OCR" in elem.evidence.evidence_sources
    assert elem.confidence == 0.99


def test_desktop_observation_canonical_snapshot():
    """Verify DesktopObservation represents an immutable, consistent desktop snapshot."""
    fg_win = WindowObservation(
        hwnd=1024,
        title="Untitled - Notepad",
        window_class="Notepad",
        is_foreground=True,
        is_visible=True,
        window_bounds=BoundingBox(left=100, top=100, width=800, height=600),
        client_bounds=BoundingBox(left=108, top=130, width=784, height=562),
    )
    obs = DesktopObservation(
        screen_width=1920,
        screen_height=1080,
        foreground_window=fg_win,
        visible_windows=[fg_win],
        is_consistent=True,
        capture_duration_ms=45.2,
    )
    assert obs.active_window_title == "Untitled - Notepad"
    assert obs.active_window_hwnd == 1024
    assert obs.target_app_exists is True
    assert obs.target_app_is_active is True
    assert obs.is_consistent is True
    assert obs.capture_duration_ms == 45.2
