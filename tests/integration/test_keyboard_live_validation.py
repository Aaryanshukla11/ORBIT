"""Controlled Live OS validation suite for Production Keyboard Capability in ORBIT M1.3."""

import sys
import pytest
from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.keyboard.dispatch import NativeKeyboardDispatchGateway
from orbit.adapters.keyboard.safety import KeyboardAbiGate, VK_SHIFT
from orbit.adapters.pointer.safety import ensure_thread_input_desktop
from orbit.runtime.cancellation import CancellationSource, CancellationToken



@pytest.mark.asyncio
async def test_live_keyboard_controlled_validation():
    if sys.platform != "win32":
        pytest.skip("Controlled live keyboard validation requires Windows host")

    # 1. Verify ABI Gate
    assert KeyboardAbiGate.is_abi_valid() is True

    # 2. Verify Desktop Attachment
    attached = ensure_thread_input_desktop()
    assert attached is True

    # 3. Instantiate and initialize ProductionKeyboardAdapter
    adapter = ProductionKeyboardAdapter(enable_live_injection=True)
    await adapter.initialize()
    assert adapter.is_ready is True

    try:
        # 4. Controlled key press / release (VK_SHIFT)
        down_ok = await adapter.press_key("shift")
        assert down_ok is True
        assert adapter.state_manager.is_key_down(VK_SHIFT) is True

        up_ok = await adapter.release_key("shift")
        assert up_ok is True
        assert adapter.state_manager.is_key_down(VK_SHIFT) is False

        # 5. Controlled shortcut execution (e.g. shift+a)
        sc_ok = await adapter.press_shortcut("shift+a")
        assert sc_ok is True
        assert len(adapter.state_manager.get_orbit_pressed_keys()) == 0

        # 6. Cancellation test
        source = CancellationSource()
        source.cancel("Controlled validation cancellation")
        type_cancelled = await adapter.type_text("Test", cancellation_token=source.token)
        assert type_cancelled is False


        # 7. Emergency sanitization check
        clean = await adapter.emergency_release_all()
        assert clean is True
        assert len(adapter.state_manager.get_orbit_pressed_keys()) == 0

    finally:
        await adapter.shutdown()
