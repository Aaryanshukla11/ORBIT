"""Integration tests for ProductionKeyboardAdapter lifecycle, health, and lockout in ORBIT M1.3."""

import pytest
from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.contracts.capabilities import CapabilityHealthStatus, CapabilityLifecycleState


@pytest.mark.asyncio
async def test_production_keyboard_adapter_lifecycle():
    adapter = ProductionKeyboardAdapter(enable_live_injection=True)
    assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED

    await adapter.initialize()
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert adapter.is_ready is True

    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.HEALTHY

    lockout = await adapter.get_lockout_state()
    assert lockout == "NORMAL"

    # Emergency release works cleanly in normal state
    ok = await adapter.emergency_release_all()
    assert ok is True

    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED


@pytest.mark.asyncio
async def test_production_keyboard_adapter_lockout_propagation():
    adapter = ProductionKeyboardAdapter(enable_live_injection=True)
    await adapter.initialize()

    # Lock state
    token = adapter.state_manager.lock_state("Simulated keyboard driver desynchronization")
    assert await adapter.get_lockout_state() == "UNRESOLVED_LOCKED"

    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.DEGRADED

    # Typing should be rejected fail-closed
    with pytest.raises(Exception):
        await adapter.type_text("test")

    # Recover with token
    recovered = adapter.recover_locked_state(token)
    assert recovered is True
    assert await adapter.get_lockout_state() == "NORMAL"

    health_recovered = await adapter.get_health()
    assert health_recovered.status == CapabilityHealthStatus.HEALTHY

    await adapter.shutdown()
