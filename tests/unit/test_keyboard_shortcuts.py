"""Unit tests for ShortcutPolicy and ShortcutExecutor in ORBIT M1.3."""

import pytest
from orbit.adapters.keyboard.shortcuts import (
    ShortcutExecutor,
    ShortcutPolicy,
    ShortcutRiskLevel,
)
from orbit.adapters.keyboard.state import KeyboardStateManager
from orbit.runtime.cancellation import CancellationSource, CancellationToken



def test_shortcut_policy_classification():
    policy = ShortcutPolicy()

    # Allowed safe editing shortcuts
    assert policy.classify(["ctrl"], "c") == ShortcutRiskLevel.ALLOWED
    assert policy.classify(["ctrl"], "v") == ShortcutRiskLevel.ALLOWED
    assert policy.classify(["ctrl", "shift"], "s") == ShortcutRiskLevel.ALLOWED
    assert policy.classify(["alt"], "f") == ShortcutRiskLevel.ALLOWED

    # Restricted destructive system shortcuts
    assert policy.classify(["win"], "l") == ShortcutRiskLevel.RESTRICTED
    assert policy.classify(["alt"], "f4") == ShortcutRiskLevel.RESTRICTED
    assert policy.classify(["ctrl", "alt"], "delete") == ShortcutRiskLevel.RESTRICTED
    assert policy.classify(["ctrl", "shift"], "escape") == ShortcutRiskLevel.RESTRICTED
    assert policy.classify(["win"], "d") == ShortcutRiskLevel.RESTRICTED

    # Manual controlled shortcuts
    assert policy.classify(["alt"], "tab") == ShortcutRiskLevel.MANUAL_CONTROLLED_ONLY
    assert policy.classify(["win"], "tab") == ShortcutRiskLevel.MANUAL_CONTROLLED_ONLY


def test_shortcut_policy_parsing():
    policy = ShortcutPolicy()
    mods, act = policy.parse_combination("ctrl+shift+s")
    assert mods == ["ctrl", "shift"]
    assert act == "s"

    mods2, act2 = policy.parse_combination("enter")
    assert mods2 == []
    assert act2 == "enter"

    with pytest.raises(ValueError):
        policy.parse_combination("")


def test_shortcut_restricted_execution_rejection():
    mgr = KeyboardStateManager()
    executor = ShortcutExecutor(mgr)

    with pytest.raises(ValueError, match="RESTRICTED"):
        executor.execute_shortcut("win+l")

    with pytest.raises(ValueError, match="RESTRICTED"):
        executor.execute_shortcut("alt+f4")


def test_shortcut_cancellation_before_execution():
    mgr = KeyboardStateManager()
    executor = ShortcutExecutor(mgr)
    source = CancellationSource()
    source.cancel("User cancelled before shortcut")

    success = executor.execute_shortcut("ctrl+c", cancellation_token=source.token)
    assert success is False
    assert len(mgr.get_orbit_pressed_keys()) == 0

