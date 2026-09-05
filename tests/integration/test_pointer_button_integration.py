"""Integration tests for ProductionPointerAdapter button operations and click transactions in ORBIT M1.2B."""

import pytest

from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.pointer.safety import MouseButton
from orbit.contracts.capabilities import CapabilityLifecycleState


@pytest.mark.asyncio
async def test_pointer_adapter_click_and_button_lifecycle():
    # Construct adapter with mock native dispatch overrides for deterministic integration testing
    dispatched_packets = []

    def mock_sendinput(n, packet, size):
        dispatched_packets.append(packet)
        return 1

    adapter = ProductionPointerAdapter(
        tolerance_px=2,
        sendinput_override=mock_sendinput,
        cursorpos_override=lambda: (500, 300),
    )
    await adapter.initialize()

    assert adapter.is_ready is True
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY

    # Test 1: Single atomic click
    click_success = await adapter.click(button="left", count=1, dwell_ms=10.0)
    assert click_success is True
    assert adapter.state_manager.is_locked is False

    # Test 2: Click with movement to target (500, 300)
    click_with_move = await adapter.click(x=500, y=300, button="right", count=1)
    assert click_with_move is True

    # Test 3: Manual press_down and release_up
    down_success = await adapter.press_down(button="middle")
    assert down_success is True
    assert MouseButton.MIDDLE in adapter.state_manager.held_buttons

    up_success = await adapter.release_up(button="middle")
    assert up_success is True
    assert len(adapter.state_manager.held_buttons) == 0

    # Test 4: Emergency release all
    await adapter.press_down(button="left")
    assert MouseButton.LEFT in adapter.state_manager.held_buttons

    release_all_success = await adapter.emergency_release_all()
    assert release_all_success is True
    assert len(adapter.state_manager.held_buttons) == 0

    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED


@pytest.mark.asyncio
async def test_pointer_adapter_lockout_and_recovery():
    calls = 0

    def mock_sendinput(n, packet, size):
        nonlocal calls
        calls += 1
        # DOWN succeeds (call 1), UP fails (call 2)
        return 1 if calls == 1 else 0

    adapter = ProductionPointerAdapter(
        tolerance_px=2,
        sendinput_override=mock_sendinput,
        cursorpos_override=lambda: (500, 300),
    )
    await adapter.initialize()

    # DOWN succeeds
    await adapter.press_down(button="left")
    assert MouseButton.LEFT in adapter.state_manager.held_buttons

    # UP fails -> triggers UNRESOLVED_LOCKED
    with pytest.raises(Exception, match="UNRESOLVED_LOCKED"):
        await adapter.release_up(button="left")

    assert await adapter.get_lockout_state() == "LOCKED"
    assert adapter.state_manager.is_locked is True

    # Subsequent clicks must be rejected
    with pytest.raises(Exception, match="UNRESOLVED_LOCKED"):
        await adapter.click(button="left")

    # Recover with active token
    token = adapter.state_manager._active_recovery_token
    assert token is not None

    recovered = adapter.recover_locked_state(token)
    assert recovered is True
    assert await adapter.get_lockout_state() == "NORMAL"
    assert adapter.state_manager.is_locked is False

    await adapter.shutdown()
