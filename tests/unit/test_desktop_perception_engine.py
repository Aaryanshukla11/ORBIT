"""Unit tests for DesktopPerceptionEngine and partial failure resilience."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.models.common import BoundingBox
from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRToken,
    ScreenshotObservation,
    UIElementObservation,
    VisualRegion,
    VisualRegionType,
    WindowObservation,
)
from orbit.runtime.perception.observer import DesktopObserver


@pytest.mark.asyncio
async def test_desktop_perception_engine_full_observation():
    """Verify DesktopPerceptionEngine captures and fuses multi-modal observation."""
    mock_observer = MagicMock(spec=DesktopObserver)

    fg_win = WindowObservation(
        hwnd=2048,
        title="Calculator",
        window_class="ApplicationFrameWindow",
        is_foreground=True,
        is_visible=True,
        window_bounds=BoundingBox(left=300, top=200, width=400, height=500),
        client_bounds=BoundingBox(left=300, top=230, width=400, height=470),
        process_name="calculator.exe",
    )
    uia_btn = UIElementObservation(
        name="Seven",
        control_type="Button",
        automation_id="num7Button",
        bounding_box=BoundingBox(left=320, top=350, width=50, height=40),
    )
    ocr_tok = OCRToken(
        text="7",
        confidence=0.99,
        bounding_box=BoundingBox(left=330, top=360, width=30, height=20),
        source="WINDOWS_OCR",
    )

    mock_raw = DesktopObservation(
        screen_width=1920,
        screen_height=1080,
        foreground_window=fg_win,
        visible_windows=[fg_win],
        screenshot_reference=ScreenshotObservation(width=1920, height=1080),
        uia_elements=[uia_btn],
        ocr_tokens=[ocr_tok],
        is_consistent=True,
    )

    mock_observer.observe_desktop = AsyncMock(return_value=mock_raw)
    engine = DesktopPerceptionEngine(desktop_observer=mock_observer)

    obs = await engine.observe()
    assert obs.foreground_window.title == "Calculator"
    assert len(obs.perceived_elements) > 0

    # Verify fusion of Button "Seven" and OCR "7"
    btn_elem = obs.perceived_elements[0]
    assert btn_elem.name == "Seven"
    assert btn_elem.role == "button"
    assert "UIA" in btn_elem.evidence.evidence_sources
    assert "OCR" in btn_elem.evidence.evidence_sources
    assert btn_elem.confidence >= 0.95

    # Verify LLM Context Summary
    assert "Calculator" in obs.desktop_summary
    assert "Button" in obs.desktop_summary


@pytest.mark.asyncio
async def test_desktop_perception_engine_partial_failures():
    """Verify DesktopPerceptionEngine is resilient when OCR or UIA fail."""
    mock_observer = MagicMock(spec=DesktopObserver)

    fg_win = WindowObservation(
        hwnd=5001,
        title="CustomApp",
        window_class="CustomClass",
        is_foreground=True,
        is_visible=True,
        window_bounds=BoundingBox(left=100, top=100, width=500, height=400),
        client_bounds=BoundingBox(left=100, top=100, width=500, height=400),
    )

    # Empty UIA and empty OCR (e.g. non-accessible or headless environment)
    mock_raw = DesktopObservation(
        screen_width=1920,
        screen_height=1080,
        foreground_window=fg_win,
        visible_windows=[fg_win],
        screenshot_reference=ScreenshotObservation(width=1920, height=1080),
        uia_elements=[],
        ocr_tokens=[],
        is_consistent=True,
    )

    mock_observer.observe_desktop = AsyncMock(return_value=mock_raw)
    engine = DesktopPerceptionEngine(desktop_observer=mock_observer)

    obs = await engine.observe()
    assert obs.foreground_window.title == "CustomApp"
    assert obs.desktop_summary is not None
    assert "CustomApp" in obs.desktop_summary
