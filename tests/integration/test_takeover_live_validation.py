"""Controlled Live Windows validation for Human Takeover hooks and preemption."""

import asyncio
import ctypes
import sys
import time
import pytest

from orbit.adapters.keyboard.dispatch import NativeKeyboardDispatchGateway
from orbit.adapters.pointer.health import ActionCounter
from orbit.adapters.pointer.movement import NativeDispatchGateway
from orbit.adapters.pointer.safety import (
    FLAGS_ABSOLUTE_MOVE,
    INPUT,
    INPUT_MOUSE,
    ORBIT_EXTRA_INFO_SIGNATURE,
    AbiGate,
)
from orbit.adapters.takeover.adapter import ProductionHumanTakeoverAdapter
from orbit.adapters.takeover.classifier import InputSource
from orbit.adapters.takeover.safety import TakeoverAbiGate
from orbit.adapters.takeover.state import TakeoverState


@pytest.mark.asyncio
async def test_live_windows_takeover_hook_and_synthetic_bypass():
    if sys.platform != "win32":
        pytest.skip("Windows only live hook validation")

    abi_res = TakeoverAbiGate.validate_abi()
    assert abi_res.is_valid is True

    adapter = ProductionHumanTakeoverAdapter(enable_live_hooks=True, quiet_period_seconds=0.1)
    await adapter.initialize()
    assert adapter.is_ready is True

    events_received = []

    def on_takeover(evidence=None):
        events_received.append(evidence)

    started = await adapter.start_monitoring(on_takeover)
    assert started is True
    assert adapter.current_state == TakeoverState.MONITORING

    # 1. Dispatch synthetic ORBIT mouse packet with signature
    gateway = NativeDispatchGateway(abi_gate=AbiGate(), action_counter=ActionCounter())
    input_packet = INPUT()
    input_packet.type = INPUT_MOUSE
    input_packet.union.mi.dx = 32768
    input_packet.union.mi.dy = 32768
    input_packet.union.mi.dwFlags = FLAGS_ABSOLUTE_MOVE
    input_packet.union.mi.dwExtraInfo = ORBIT_EXTRA_INFO_SIGNATURE

    acc, err, dur = gateway.dispatch_single_packet(input_packet)
    assert acc == 1

    # Give hook thread a moment to process the message
    await asyncio.sleep(0.05)

    # Synthetic ORBIT event must NOT trigger takeover
    assert await adapter.is_takeover_active() is False

    # 2. Dispatch synthetic ORBIT keyboard packet with signature
    res = NativeKeyboardDispatchGateway.dispatch_key_packet(
        vk_or_scan=0x11,  # VK_CONTROL
        is_extended=False,
        is_unicode=False,
        is_down=True,
    )
    assert res.success is True

    # Release it immediately
    NativeKeyboardDispatchGateway.dispatch_key_packet(
        vk_or_scan=0x11,
        is_extended=False,
        is_unicode=False,
        is_down=False,
    )

    await asyncio.sleep(0.05)
    # Synthetic ORBIT key must NOT trigger takeover
    assert await adapter.is_takeover_active() is False

    # 3. Clean shutdown unhooks hooks
    await adapter.shutdown()
    assert adapter.lifecycle_state.value == "STOPPED"
