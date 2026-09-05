"""Unit tests for Keyboard ABI validation and NativeKeyboardDispatchGateway."""

import sys
import pytest
from orbit.adapters.keyboard.dispatch import NativeKeyboardDispatchGateway
from orbit.adapters.keyboard.safety import (
    INPUT,
    KEYBDINPUT,
    KeyboardAbiGate,
)


def test_keyboard_abi_gate():
    if sys.platform != "win32":
        pytest.skip("Keyboard ABI verification requires Windows host")

    assert KeyboardAbiGate.is_abi_valid() is True
    # Calling require_abi_valid should not raise
    KeyboardAbiGate.require_abi_valid()


def test_keyboard_dispatch_gateway_telemetry():
    req_before, acc_before = NativeKeyboardDispatchGateway.get_telemetry_totals()
    assert req_before >= 0
    assert acc_before >= 0
