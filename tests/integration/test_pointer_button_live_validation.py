"""Controlled live OS pointer button and click transaction validation for ORBIT M1.2B."""

import asyncio
import sys
import time
import pytest

from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.pointer.buttons import ButtonExecutionStatus, ClickExecutionStatus
from orbit.adapters.pointer.safety import MouseButton
from orbit.contracts.capabilities import CapabilityLifecycleState


@pytest.mark.asyncio
async def test_live_os_pointer_button_validation():
    """Execute controlled live button and click transaction validation against Windows host."""
    if sys.platform != "win32":
        pytest.skip("Live OS pointer validation requires Windows platform")

    adapter = ProductionPointerAdapter(tolerance_px=2)
    await adapter.initialize()

    assert adapter.is_ready is True
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY

    try:
        # Step 1: Initial resting state
        assert adapter.state_manager.is_locked is False
        assert len(adapter.state_manager.held_buttons) == 0

        # Step 2: Atomic controlled click (dwell 20ms)
        click_success = await adapter.click(button="left", count=1, dwell_ms=20.0)
        assert click_success is True
        assert adapter.state_manager.is_locked is False
        assert len(adapter.state_manager.held_buttons) == 0

        # Step 3: Single controlled DOWN and UP transaction
        down_success = await adapter.press_down(button="left")
        assert down_success is True
        assert MouseButton.LEFT in adapter.state_manager.held_buttons

        up_success = await adapter.release_up(button="left")
        assert up_success is True
        assert len(adapter.state_manager.held_buttons) == 0

        # Step 4: Emergency release check
        await adapter.press_down(button="right")
        assert MouseButton.RIGHT in adapter.state_manager.held_buttons

        release_success = await adapter.emergency_release_all()
        assert release_success is True
        assert len(adapter.state_manager.held_buttons) == 0
        assert adapter.state_manager.is_locked is False

    finally:
        await adapter.shutdown()
