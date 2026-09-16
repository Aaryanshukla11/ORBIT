"""Unit tests for ModalDialogDetector and DialogTrapHandler (Phase 2G.2)."""

import pytest
from orbit.runtime.agent.contracts import AbstractActionType
from orbit.runtime.cognitive.dialog_handler import (
    DetectedDialog,
    DialogIntent,
    DialogResolutionStrategy,
    DialogTrapHandler,
    ModalDialogDetector,
)
from orbit.runtime.cognitive.models import CurrentStateObservation
from orbit.runtime.cognitive.recovery import AgentRecoveryManager, RecoveryStrategy
from orbit.runtime.agent.contracts import AbstractAction, ActionExecutionResult, OutcomeStatus


def test_modal_dialog_detector_identifies_save_collision():
    detector = ModalDialogDetector()
    obs = CurrentStateObservation(
        active_window_hwnd=12345,
        active_window_title="Confirm Save As",
        active_window_class="#32770",
        ocr_tokens=["report.txt", "already exists.", "Do you want to replace it?", "Yes", "No"],
        visible_windows=[{"hwnd": 12345, "title": "Confirm Save As", "class_name": "#32770"}],
    )

    dlg = detector.detect_dialog(obs)
    assert dlg is not None
    assert dlg.hwnd == 12345
    assert dlg.intent == DialogIntent.FILE_COLLISION
    assert dlg.is_modal is True
    assert "Yes" in dlg.interactive_buttons


def test_modal_dialog_detector_identifies_confirm_discard():
    detector = ModalDialogDetector()
    obs = CurrentStateObservation(
        active_window_hwnd=67890,
        active_window_title="Notepad",
        active_window_class="#32770",
        ocr_tokens=["Do you want to save changes to Untitled?", "Save", "Don't Save", "Cancel"],
        visible_windows=[{"hwnd": 67890, "title": "Notepad", "class_name": "#32770"}],
    )

    dlg = detector.detect_dialog(obs)
    assert dlg is not None
    assert dlg.intent == DialogIntent.CONFIRM_DISCARD
    assert "Don't Save" in dlg.interactive_buttons


def test_modal_dialog_detector_identifies_error_alert():
    detector = ModalDialogDetector()
    obs = CurrentStateObservation(
        active_window_hwnd=99999,
        active_window_title="File Error",
        active_window_class="#32770",
        ocr_tokens=["Access denied", "Cannot write to directory", "OK"],
        visible_windows=[{"hwnd": 99999, "title": "File Error", "class_name": "#32770"}],
    )

    dlg = detector.detect_dialog(obs)
    assert dlg is not None
    assert dlg.intent == DialogIntent.ERROR_ALERT


def test_dialog_trap_handler_synthesizes_collision_action():
    handler = DialogTrapHandler()
    dlg = DetectedDialog(
        hwnd=12345,
        title="Confirm Save As",
        class_name="#32770",
        intent=DialogIntent.FILE_COLLISION,
        interactive_buttons=["Yes", "No"],
    )

    act = handler.resolve_dialog(dlg, preferred_strategy=DialogResolutionStrategy.CONFIRM_REPLACE)
    assert act.action_type == AbstractActionType.CLICK
    assert act.target.name == "Yes"
    assert act.parameters.get("hotkey_fallback") == "Alt+Y"


def test_dialog_trap_handler_synthesizes_discard_action():
    handler = DialogTrapHandler()
    dlg = DetectedDialog(
        hwnd=67890,
        title="Notepad",
        class_name="#32770",
        intent=DialogIntent.CONFIRM_DISCARD,
        interactive_buttons=["Save", "Don't Save", "Cancel"],
    )

    act = handler.resolve_dialog(dlg, preferred_strategy=DialogResolutionStrategy.DISCARD_AND_CLOSE)
    assert act.action_type == AbstractActionType.CLICK
    assert act.target.name == "Don't Save"


def test_agent_recovery_manager_diagnoses_and_synthesizes_dialog_recovery():
    recovery_mgr = AgentRecoveryManager()
    pre_obs = CurrentStateObservation(active_window_title="Notepad", active_window_hwnd=111)
    post_obs = CurrentStateObservation(
        active_window_hwnd=222,
        active_window_title="Confirm Save As",
        active_window_class="#32770",
        ocr_tokens=["already exists. Do you want to replace it?"],
        visible_windows=[{"hwnd": 222, "title": "Confirm Save As", "class_name": "#32770"}],
    )
    failed_act = AbstractAction(action_type=AbstractActionType.TYPE_TEXT, parameters={"text": "file.txt\n"})
    exec_res = ActionExecutionResult(
        action_id=failed_act.action_id,
        dispatch_success=True,
        expected_effect_observed=False,
        status=OutcomeStatus.EFFECT_UNVERIFIED,
    )

    strat, diagnosis = recovery_mgr.diagnose_failure(failed_act, pre_obs, post_obs, exec_res)
    assert strat == RecoveryStrategy.OVERWRITE_FILE_COLLISION
    assert "File collision overwrite dialog detected" in diagnosis

    recovery_act = recovery_mgr.synthesize_recovery_primitive(strat, failed_act, post_obs)
    assert recovery_act is not None
    assert recovery_act.action_type == AbstractActionType.CLICK
    assert recovery_act.target.name == "Yes"
