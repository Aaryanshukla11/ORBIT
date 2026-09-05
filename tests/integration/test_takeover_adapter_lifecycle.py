"""Integration tests for ProductionHumanTakeoverAdapter lifecycle and health."""

import pytest
from orbit.adapters.takeover.adapter import ProductionHumanTakeoverAdapter
from orbit.adapters.takeover.state import TakeoverState
from orbit.contracts.capabilities import CapabilityHealthStatus, CapabilityLifecycleState


@pytest.mark.asyncio
async def test_production_takeover_adapter_lifecycle():
    adapter = ProductionHumanTakeoverAdapter(enable_live_hooks=True)
    assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED

    await adapter.initialize()
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert adapter.is_ready is True

    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.HEALTHY
    assert health.details["current_takeover_state"] == "STOPPED"

    # Start monitoring with test callback
    called = []
    started = await adapter.start_monitoring(lambda ev=None: called.append(True))
    assert started is True
    assert adapter.current_state == TakeoverState.MONITORING

    health = await adapter.get_health()
    assert health.details["is_monitoring"] is True

    # Stop monitoring
    stopped = await adapter.stop_monitoring()
    assert stopped is True
    assert adapter.current_state == TakeoverState.STOPPED

    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED


@pytest.mark.asyncio
async def test_production_takeover_adapter_reset():
    adapter = ProductionHumanTakeoverAdapter(enable_live_hooks=True)
    await adapter.initialize()
    await adapter.start_monitoring(lambda ev=None: None)

    # Force trigger state for testing reset
    adapter.state_manager.transition_to(TakeoverState.TAKEOVER_TRIGGERED)
    adapter.state_manager.transition_to(TakeoverState.TAKEOVER_ACTIVE)
    assert await adapter.is_takeover_active() is True

    reset_ok = await adapter.reset_takeover_state()
    assert reset_ok is True
    assert await adapter.is_takeover_active() is False
    assert adapter.current_state == TakeoverState.MONITORING

    await adapter.shutdown()
