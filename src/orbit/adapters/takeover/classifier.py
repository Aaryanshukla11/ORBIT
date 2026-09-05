"""Input Attribution and Takeover Evidence Classifier."""

from __future__ import annotations

from enum import Enum
import time
from typing import Optional
from pydantic import BaseModel, Field

from orbit.adapters.takeover.safety import (
    KBDLLHOOKSTRUCT,
    LLKHF_INJECTED,
    LLMHF_INJECTED,
    MSLLHOOKSTRUCT,
    ORBIT_EXTRA_INFO_SIGNATURE,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MBUTTONDOWN,
    WM_MBUTTONUP,
    WM_MOUSEMOVE,
    WM_MOUSEWHEEL,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
    WM_SYSKEYDOWN,
    WM_SYSKEYUP,
)


class InputSource(str, Enum):
    """Classification of input origin."""
    USER_PHYSICAL = "USER_PHYSICAL"
    ORBIT_EXPECTED = "ORBIT_EXPECTED"
    INPUT_AMBIGUOUS = "INPUT_AMBIGUOUS"


class InputDevice(str, Enum):
    """Device family generating the event."""
    MOUSE = "MOUSE"
    KEYBOARD = "KEYBOARD"


class InputEventType(str, Enum):
    """Discrete message event types."""
    MOUSE_MOVE = "MOUSE_MOVE"
    LBUTTON_DOWN = "LBUTTON_DOWN"
    LBUTTON_UP = "LBUTTON_UP"
    RBUTTON_DOWN = "RBUTTON_DOWN"
    RBUTTON_UP = "RBUTTON_UP"
    MBUTTON_DOWN = "MBUTTON_DOWN"
    MBUTTON_UP = "MBUTTON_UP"
    MOUSE_WHEEL = "MOUSE_WHEEL"
    KEY_DOWN = "KEY_DOWN"
    KEY_UP = "KEY_UP"


class TakeoverEvidence(BaseModel):
    """Epistemically honest structured evidence of an input event and takeover decision."""
    event_id: int
    timestamp_ns: int
    device: InputDevice
    event_type: InputEventType
    source: InputSource
    should_trigger_takeover: bool
    reason: str
    x: Optional[int] = None
    y: Optional[int] = None
    vk_code: Optional[int] = None
    scan_code: Optional[int] = None
    extra_info: int = 0
    is_injected: bool = False
    classification_latency_us: float = 0.0


class TakeoverClassifier:
    """Fast, non-blocking input attribution classifier executing in <10 microseconds."""

    @staticmethod
    def classify_mouse(
        event_id: int,
        timestamp_ns: int,
        w_param: int,
        info: MSLLHOOKSTRUCT,
    ) -> TakeoverEvidence:
        t_start = time.perf_counter_ns()
        is_injected = bool(info.flags & LLMHF_INJECTED)
        extra_info = int(info.dwExtraInfo)

        # 1. Attribute input source
        if not is_injected:
            source = InputSource.USER_PHYSICAL
        elif extra_info == ORBIT_EXTRA_INFO_SIGNATURE:
            source = InputSource.ORBIT_EXPECTED
        else:
            source = InputSource.INPUT_AMBIGUOUS

        # 2. Map message type
        if w_param == WM_MOUSEMOVE:
            event_type = InputEventType.MOUSE_MOVE
        elif w_param == WM_LBUTTONDOWN:
            event_type = InputEventType.LBUTTON_DOWN
        elif w_param == WM_LBUTTONUP:
            event_type = InputEventType.LBUTTON_UP
        elif w_param == WM_RBUTTONDOWN:
            event_type = InputEventType.RBUTTON_DOWN
        elif w_param == WM_RBUTTONUP:
            event_type = InputEventType.RBUTTON_UP
        elif w_param == WM_MBUTTONDOWN:
            event_type = InputEventType.MBUTTON_DOWN
        elif w_param == WM_MBUTTONUP:
            event_type = InputEventType.MBUTTON_UP
        elif w_param == WM_MOUSEWHEEL:
            event_type = InputEventType.MOUSE_WHEEL
        else:
            event_type = InputEventType.MOUSE_MOVE

        # 3. Determine takeover trigger
        if source == InputSource.USER_PHYSICAL:
            should_takeover = True
            if event_type in (
                InputEventType.LBUTTON_DOWN,
                InputEventType.RBUTTON_DOWN,
                InputEventType.MBUTTON_DOWN,
                InputEventType.MOUSE_WHEEL,
            ):
                reason = f"Physical mouse button interaction ({event_type.value})"
            else:
                reason = f"Physical mouse movement at ({info.pt.x}, {info.pt.y})"
        elif source == InputSource.INPUT_AMBIGUOUS:
            should_takeover = True
            reason = f"Ambiguous foreign injected mouse input (signature: 0x{extra_info:08X})"
        else:
            # ORBIT_EXPECTED
            should_takeover = False
            reason = "Expected ORBIT synthetic mouse dispatch"

        latency_us = max(0.0, (time.perf_counter_ns() - t_start) / 1000.0)

        return TakeoverEvidence(
            event_id=event_id,
            timestamp_ns=timestamp_ns,
            device=InputDevice.MOUSE,
            event_type=event_type,
            source=source,
            should_trigger_takeover=should_takeover,
            reason=reason,
            x=info.pt.x,
            y=info.pt.y,
            extra_info=extra_info,
            is_injected=is_injected,
            classification_latency_us=latency_us,
        )

    @staticmethod
    def classify_keyboard(
        event_id: int,
        timestamp_ns: int,
        w_param: int,
        info: KBDLLHOOKSTRUCT,
    ) -> TakeoverEvidence:
        t_start = time.perf_counter_ns()
        is_injected = bool(info.flags & LLKHF_INJECTED)
        extra_info = int(info.dwExtraInfo)

        # 1. Attribute input source
        if not is_injected:
            source = InputSource.USER_PHYSICAL
        elif extra_info == ORBIT_EXTRA_INFO_SIGNATURE:
            source = InputSource.ORBIT_EXPECTED
        else:
            source = InputSource.INPUT_AMBIGUOUS

        # 2. Map message type
        is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        event_type = InputEventType.KEY_DOWN if is_down else InputEventType.KEY_UP

        # 3. Determine takeover trigger
        if source == InputSource.USER_PHYSICAL:
            # Physical keystroke down triggers immediate takeover
            should_takeover = is_down
            reason = f"Physical keystroke {'DOWN' if is_down else 'UP'} (VK=0x{info.vkCode:02X}, scan=0x{info.scanCode:02X})"
        elif source == InputSource.INPUT_AMBIGUOUS:
            should_takeover = is_down
            reason = f"Ambiguous foreign injected keystroke (signature: 0x{extra_info:08X})"
        else:
            # ORBIT_EXPECTED
            should_takeover = False
            reason = "Expected ORBIT synthetic keyboard dispatch"

        latency_us = max(0.0, (time.perf_counter_ns() - t_start) / 1000.0)

        return TakeoverEvidence(
            event_id=event_id,
            timestamp_ns=timestamp_ns,
            device=InputDevice.KEYBOARD,
            event_type=event_type,
            source=source,
            should_trigger_takeover=should_takeover,
            reason=reason,
            vk_code=info.vkCode,
            scan_code=info.scanCode,
            extra_info=extra_info,
            is_injected=is_injected,
            classification_latency_us=latency_us,
        )
