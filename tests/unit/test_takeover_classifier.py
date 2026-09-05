"""Unit tests for TakeoverClassifier and input attribution."""

import time
import pytest
from orbit.adapters.takeover.classifier import (
    InputDevice,
    InputEventType,
    InputSource,
    TakeoverClassifier,
)
from orbit.adapters.takeover.safety import (
    KBDLLHOOKSTRUCT,
    LLKHF_INJECTED,
    LLMHF_INJECTED,
    MSLLHOOKSTRUCT,
    ORBIT_EXTRA_INFO_SIGNATURE,
    POINT,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MBUTTONDOWN,
    WM_MOUSEMOVE,
    WM_MOUSEWHEEL,
    WM_RBUTTONDOWN,
)


def test_physical_mouse_movement_attribution():
    struct = MSLLHOOKSTRUCT()
    struct.pt = POINT(100, 200)
    struct.mouseData = 0
    struct.flags = 0  # Not injected
    struct.time = 0
    struct.dwExtraInfo = 0

    evidence = TakeoverClassifier.classify_mouse(
        event_id=1,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_MOUSEMOVE,
        info=struct,
    )

    assert evidence.source == InputSource.USER_PHYSICAL
    assert evidence.device == InputDevice.MOUSE
    assert evidence.event_type == InputEventType.MOUSE_MOVE
    assert evidence.should_trigger_takeover is True
    assert evidence.x == 100
    assert evidence.y == 200
    assert "Physical mouse movement" in evidence.reason


def test_physical_mouse_click_attribution():
    struct = MSLLHOOKSTRUCT()
    struct.pt = POINT(500, 600)
    struct.mouseData = 0
    struct.flags = 0
    struct.dwExtraInfo = 0

    evidence = TakeoverClassifier.classify_mouse(
        event_id=2,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_LBUTTONDOWN,
        info=struct,
    )

    assert evidence.source == InputSource.USER_PHYSICAL
    assert evidence.event_type == InputEventType.LBUTTON_DOWN
    assert evidence.should_trigger_takeover is True
    assert "Physical mouse button interaction" in evidence.reason


def test_orbit_synthetic_mouse_bypass():
    struct = MSLLHOOKSTRUCT()
    struct.pt = POINT(300, 400)
    struct.mouseData = 0
    struct.flags = LLMHF_INJECTED
    struct.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

    evidence = TakeoverClassifier.classify_mouse(
        event_id=3,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_MOUSEMOVE,
        info=struct,
    )

    assert evidence.source == InputSource.ORBIT_EXPECTED
    assert evidence.should_trigger_takeover is False
    assert "Expected ORBIT synthetic mouse" in evidence.reason


def test_foreign_ambiguous_mouse_injection():
    struct = MSLLHOOKSTRUCT()
    struct.pt = POINT(300, 400)
    struct.mouseData = 0
    struct.flags = LLMHF_INJECTED
    struct.dwExtraInfo = 0xDEADBEEF  # Not ORBIT

    evidence = TakeoverClassifier.classify_mouse(
        event_id=4,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_MOUSEMOVE,
        info=struct,
    )

    assert evidence.source == InputSource.INPUT_AMBIGUOUS
    assert evidence.should_trigger_takeover is True
    assert "Ambiguous foreign injected mouse input" in evidence.reason


def test_physical_keystroke_attribution():
    struct = KBDLLHOOKSTRUCT()
    struct.vkCode = 0x41  # VK_A
    struct.scanCode = 0x1E
    struct.flags = 0
    struct.dwExtraInfo = 0

    evidence_down = TakeoverClassifier.classify_keyboard(
        event_id=5,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_KEYDOWN,
        info=struct,
    )

    assert evidence_down.source == InputSource.USER_PHYSICAL
    assert evidence_down.device == InputDevice.KEYBOARD
    assert evidence_down.event_type == InputEventType.KEY_DOWN
    assert evidence_down.should_trigger_takeover is True
    assert evidence_down.vk_code == 0x41

    evidence_up = TakeoverClassifier.classify_keyboard(
        event_id=6,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_KEYUP,
        info=struct,
    )

    assert evidence_up.source == InputSource.USER_PHYSICAL
    assert evidence_up.event_type == InputEventType.KEY_UP
    assert evidence_up.should_trigger_takeover is False


def test_orbit_synthetic_keyboard_bypass():
    struct = KBDLLHOOKSTRUCT()
    struct.vkCode = 0x43  # VK_C
    struct.scanCode = 0x2E
    struct.flags = LLKHF_INJECTED
    struct.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

    evidence = TakeoverClassifier.classify_keyboard(
        event_id=7,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_KEYDOWN,
        info=struct,
    )

    assert evidence.source == InputSource.ORBIT_EXPECTED
    assert evidence.should_trigger_takeover is False


def test_foreign_ambiguous_keyboard_injection():
    struct = KBDLLHOOKSTRUCT()
    struct.vkCode = 0x20  # VK_SPACE
    struct.scanCode = 0x39
    struct.flags = LLKHF_INJECTED
    struct.dwExtraInfo = 0x12345678  # Not ORBIT

    evidence = TakeoverClassifier.classify_keyboard(
        event_id=8,
        timestamp_ns=time.perf_counter_ns(),
        w_param=WM_KEYDOWN,
        info=struct,
    )

    assert evidence.source == InputSource.INPUT_AMBIGUOUS
    assert evidence.should_trigger_takeover is True
