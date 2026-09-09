"""Unit tests for LegacyActionAdapter."""

import pytest
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.agent.legacy_adapter import LegacyActionAdapter


def test_normalize_legacy_strings():
    assert LegacyActionAdapter.normalize_action_type("CLICK_ELEMENT") == AbstractActionType.CLICK
    assert LegacyActionAdapter.normalize_action_type("TYPE") == AbstractActionType.TYPE_TEXT
    assert LegacyActionAdapter.normalize_action_type("HOTKEY") == AbstractActionType.SEND_HOTKEY
    assert LegacyActionAdapter.normalize_action_type("DRAW") == AbstractActionType.DRAW_STROKES
    assert LegacyActionAdapter.normalize_action_type("COMPLETE") == AbstractActionType.COMPLETE_GOAL
    assert LegacyActionAdapter.normalize_action_type("ABORT") == AbstractActionType.ABORT_TASK
    assert LegacyActionAdapter.normalize_action_type("ABORT_UNACHIEVABLE") == AbstractActionType.ABORT_TASK


def test_normalize_canonical_strings():
    assert LegacyActionAdapter.normalize_action_type("CLICK") == AbstractActionType.CLICK
    assert LegacyActionAdapter.normalize_action_type("TYPE_TEXT") == AbstractActionType.TYPE_TEXT
    assert LegacyActionAdapter.normalize_action_type("SEND_HOTKEY") == AbstractActionType.SEND_HOTKEY
    assert LegacyActionAdapter.normalize_action_type("DRAW_STROKES") == AbstractActionType.DRAW_STROKES
    assert LegacyActionAdapter.normalize_action_type("FILE_READ") == AbstractActionType.FILE_READ
    assert LegacyActionAdapter.normalize_action_type("SPREADSHEET_WRITE") == AbstractActionType.SPREADSHEET_WRITE


def test_normalize_dict_action():
    legacy_dict = {
        "action_type": "CLICK_ELEMENT",
        "parameters": {"button": "left"},
        "expected_effect": "click button",
    }
    action = LegacyActionAdapter.normalize_action(legacy_dict)
    assert isinstance(action, AbstractAction)
    assert action.action_type == AbstractActionType.CLICK
    assert action.parameters["button"] == "left"


def test_normalize_abstract_action_object():
    act = AbstractAction(
        action_type=AbstractActionType.CLICK,
        parameters={"button": "left"},
        expected_effect="click button",
    )
    normalized = LegacyActionAdapter.normalize_action(act)
    assert normalized.action_type == AbstractActionType.CLICK


def test_unknown_action_type_raises():
    with pytest.raises(ValueError, match="Unknown action type"):
        LegacyActionAdapter.normalize_action_type("NON_EXISTENT_ACTION_123")
