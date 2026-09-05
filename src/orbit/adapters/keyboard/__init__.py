"""Production Keyboard Capability Package for ORBIT."""

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.keyboard.dispatch import (
    KeyboardDispatchResult,
    NativeKeyboardDispatchGateway,
)
from orbit.adapters.keyboard.focus import TargetContext, TargetFocusValidator
from orbit.adapters.keyboard.safety import (
    MODIFIER_MAP,
    SPECIAL_KEY_MAP,
    KeyboardAbiGate,
)
from orbit.adapters.keyboard.shortcuts import (
    ShortcutExecutor,
    ShortcutPolicy,
    ShortcutRiskLevel,
)
from orbit.adapters.keyboard.state import (
    KeyboardStateManager,
    KeyOwner,
    PressedKey,
)
from orbit.adapters.keyboard.text import TextTypingExecutor
from orbit.adapters.keyboard.unicode import (
    UnicodeEngine,
    UnicodeMatchOutcome,
    UnicodeValidationRecord,
)

__all__ = [
    "KeyboardAbiGate",
    "KeyboardDispatchResult",
    "KeyboardStateManager",
    "KeyOwner",
    "MODIFIER_MAP",
    "NativeKeyboardDispatchGateway",
    "PressedKey",
    "ProductionKeyboardAdapter",
    "SPECIAL_KEY_MAP",
    "ShortcutExecutor",
    "ShortcutPolicy",
    "ShortcutRiskLevel",
    "TargetContext",
    "TargetFocusValidator",
    "TextTypingExecutor",
    "UnicodeEngine",
    "UnicodeMatchOutcome",
    "UnicodeValidationRecord",
]
