"""Unit tests for MultiAppWindowOrchestrator (Phase 3C)."""

import pytest
from orbit.adapters.observation.snapshot import BoundingBox
from orbit.runtime.agent.contracts import AbstractActionType
from orbit.runtime.cognitive.models import CurrentStateObservation
from orbit.runtime.cognitive.window_orchestrator import (
    AppWindowState,
    MultiAppWindowOrchestrator,
    WindowLayout,
)


def test_window_orchestrator_updates_tracked_windows():
    """Verify orchestrator tracks visible windows and focuses active window."""
    orchestrator = MultiAppWindowOrchestrator()

    obs = CurrentStateObservation(
        observation_id="obs_wins",
        active_window_hwnd=101,
        active_window_title="Notepad Document",
        visible_windows=[
            {"hwnd": 101, "title": "Notepad Document", "process_name": "notepad.exe", "bounds": {"left": 0, "top": 0, "width": 800, "height": 600}},
            {"hwnd": 202, "title": "Calculator", "process_name": "calc.exe", "bounds": {"left": 800, "top": 0, "width": 400, "height": 500}},
        ],
    )

    orchestrator.update_from_observation(obs)

    win_notepad = orchestrator.find_window_by_query("notepad")
    assert win_notepad is not None
    assert win_notepad.hwnd == 101
    assert win_notepad.is_focused is True

    win_calc = orchestrator.find_window_by_query("calc")
    assert win_calc is not None
    assert win_calc.hwnd == 202
    assert win_calc.is_focused is False


def test_window_orchestrator_tile_geometry_calculation():
    """Verify coordinate bounding box calculations for multi-window layouts."""
    orchestrator = MultiAppWindowOrchestrator(screen_dimensions=(1920, 1080))

    # Fullscreen
    full_box, _ = orchestrator.calculate_tile_geometry(WindowLayout.FULLSCREEN)
    assert full_box.left == 0
    assert full_box.top == 0
    assert full_box.width == 1920
    assert full_box.height == 1080

    # Side by side (Split Left 50% + Split Right 50%)
    left_box, right_box = orchestrator.calculate_tile_geometry(WindowLayout.SIDE_BY_SIDE)
    assert left_box.left == 0
    assert left_box.width == 960
    assert right_box is not None
    assert right_box.left == 960
    assert right_box.width == 960


def test_window_orchestrator_synthesizes_focus_action():
    """Verify focus action synthesis generates valid canonical AbstractAction."""
    orchestrator = MultiAppWindowOrchestrator()

    obs = CurrentStateObservation(
        observation_id="obs_focus",
        active_window_hwnd=101,
        visible_windows=[
            {"hwnd": 303, "title": "Google Chrome", "process_name": "chrome.exe"},
        ],
    )
    orchestrator.update_from_observation(obs)

    focus_act = orchestrator.synthesize_focus_action("chrome")
    assert focus_act is not None
    assert focus_act.action_type == AbstractActionType.FOCUS_WINDOW
    assert focus_act.parameters.get("hwnd") == 303
    assert focus_act.parameters.get("application_name") == "chrome.exe"

    # Query for nonexistent window
    missing_act = orchestrator.synthesize_focus_action("nonexistent_app")
    assert missing_act is None


def test_window_orchestrator_clipboard_pipeline():
    """Verify clipboard storage and paste action synthesis."""
    orchestrator = MultiAppWindowOrchestrator()

    orchestrator.set_clipboard("Extracted tabular data 123.45")
    assert orchestrator.get_clipboard() == "Extracted tabular data 123.45"

    paste_act = orchestrator.synthesize_paste_action()
    assert paste_act.action_type == AbstractActionType.SEND_HOTKEY
    assert paste_act.parameters.get("hotkey") == "Ctrl+V"
    assert paste_act.parameters.get("clipboard_payload") == "Extracted tabular data 123.45"
