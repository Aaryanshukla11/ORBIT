"""Unit tests for multi-modal perception evidence fusion."""

import pytest

from orbit.models.common import BoundingBox
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRToken,
    UIElementObservation,
    VisualRegion,
    VisualRegionType,
    WindowObservation,
)


def test_perception_fusion_combines_uia_ocr_and_visual():
    """Verify that overlapping OCR tokens, UIA controls, and visual regions are fused accurately."""
    engine = DesktopPerceptionEngine()

    fg = WindowObservation(
        hwnd=3000,
        title="Notepad",
        window_class="Notepad",
        is_foreground=True,
        is_visible=True,
        window_bounds=BoundingBox(left=100, top=100, width=800, height=600),
        client_bounds=BoundingBox(left=108, top=130, width=784, height=562),
    )

    uia_save = UIElementObservation(
        name="Save",
        control_type="Button",
        automation_id="save_btn",
        bounding_box=BoundingBox(left=150, top=140, width=60, height=25),
    )

    ocr_save = OCRToken(
        text="Save",
        confidence=0.98,
        bounding_box=BoundingBox(left=155, top=145, width=40, height=15),
        source="WINDOWS_OCR",
    )

    standalone_ocr = OCRToken(
        text="Unsaved Document",
        confidence=0.95,
        bounding_box=BoundingBox(left=300, top=145, width=120, height=15),
        source="WINDOWS_OCR",
    )

    vreg_canvas = VisualRegion(
        region_type=VisualRegionType.CANVAS,
        bounds=BoundingBox(left=108, top=180, width=784, height=500),
        confidence=0.90,
        description="Notepad Text Document Canvas",
        source="WIN32",
    )

    obs = DesktopObservation(
        screen_width=1920,
        screen_height=1080,
        foreground_window=fg,
        visible_windows=[fg],
        uia_elements=[uia_save],
        ocr_tokens=[ocr_save, standalone_ocr],
        visual_regions=[vreg_canvas],
    )

    fused = engine._fuse_evidence(obs)
    assert len(fused) == 3

    # 1. Fused Save Button (UIA + OCR)
    save_elem = next(e for e in fused if e.name == "Save")
    assert save_elem.role == "button"
    assert "UIA" in save_elem.evidence.evidence_sources
    assert "OCR" in save_elem.evidence.evidence_sources
    assert save_elem.confidence >= 0.95

    # 2. Standalone OCR Element
    text_elem = next(e for e in fused if "Unsaved Document" in e.name)
    assert text_elem.role == "text"
    assert "OCR" in text_elem.evidence.evidence_sources

    # 3. Canvas Visual Region
    canvas_elem = next(e for e in fused if "Canvas" in e.name)
    assert canvas_elem.role == "canvas"
    assert "WIN32" in canvas_elem.evidence.evidence_sources
