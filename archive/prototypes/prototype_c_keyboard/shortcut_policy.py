"""
Shortcut Risk Classification Layer for Prototype C.
Categorizes shortcut sequences into ALLOWED, RESTRICTED, and MANUAL_CONTROLLED_ONLY.
Ensures destructive or focus-disruptive shortcuts are blocked from unattended automated execution.
"""

from typing import List, Set
from app_types import ShortcutRiskLevel


class ShortcutPolicyClassifier:
    """
    Evaluates keyboard shortcut risk before execution.
    """

    def __init__(self):
        # Normal safe editing shortcuts
        self._allowed_keys: Set[str] = {
            "a", "c", "v", "x", "z", "y", "s", "f", "p", "o", "n", "w",
            "left", "right", "up", "down", "home", "end", "pageup", "pagedown",
            "backspace", "delete", "enter", "tab", "space"
        }

        # Destructive system shortcuts (blocked by default in automated tests)
        self._restricted_combinations = {
            ("win", "l"),        # Lock workstation
            ("alt", "f4"),       # Close active window
            ("win", "d"),        # Minimize all windows
            ("win", "m"),        # Minimize all
            ("win", "r"),        # Run dialog
            ("win", "e"),        # File Explorer
            ("ctrl", "alt", "delete"),
            ("ctrl", "shift", "escape"),  # Task Manager
        }

        # Context-disruptive shortcuts (manual controlled validation only)
        self._manual_only_combinations = {
            ("alt", "tab"),
            ("alt", "shift", "tab"),
            ("win", "tab"),
            ("win", "ctrl", "left"),
            ("win", "ctrl", "right"),
        }

    def classify(self, modifiers: List[str], action_key: str) -> ShortcutRiskLevel:
        """
        Classifies a modifier + action key sequence.
        """
        norm_mods = tuple(sorted([m.lower().strip() for m in modifiers]))
        norm_act = action_key.lower().strip()
        full_tuple = tuple(sorted(list(norm_mods) + [norm_act]))

        # Check manual-only
        if (norm_mods == ("alt",) and norm_act == "tab") or full_tuple in self._manual_only_combinations:
            return ShortcutRiskLevel.MANUAL_CONTROLLED_ONLY

        # Check restricted
        for restricted in self._restricted_combinations:
            if set(restricted) == set(list(norm_mods) + [norm_act]):
                return ShortcutRiskLevel.RESTRICTED

        # If it includes Win key without explicit whitelist
        if "win" in norm_mods or norm_act in ("win", "lwin", "rwin"):
            return ShortcutRiskLevel.RESTRICTED

        # Allowed standard shortcuts
        if norm_act in self._allowed_keys:
            return ShortcutRiskLevel.ALLOWED

        return ShortcutRiskLevel.ALLOWED

    def is_safe_for_unattended_automation(self, modifiers: List[str], action_key: str) -> bool:
        """
        Returns True only if shortcut is ALLOWED for automated test suites.
        """
        return self.classify(modifiers, action_key) == ShortcutRiskLevel.ALLOWED
