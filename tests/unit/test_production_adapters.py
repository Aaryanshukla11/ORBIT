"""Unit tests for production adapter boundaries and explicit error handling."""

import pytest

from orbit.adapters.base import (
    CapabilityInitializationError,
    CapabilityUnavailableError,
    HumanTakeoverError,
    KeyboardError,
    ObservationError,
    PointerError,
    WorkspaceError,
)
from orbit.adapters.production import (
    ProductionHumanTakeoverAdapter,
    ProductionKeyboardAdapter,
    ProductionObservationAdapter,
    ProductionPointerAdapter,
    ProductionSafetyCoordinator,
    ProductionWorkspaceAdapter,
)
from orbit.contracts.capabilities import (
    CapabilityHealthStatus,
    CapabilityLifecycleState,
)


@pytest.mark.asyncio
async def test_production_observation_adapter_boundary():
    adapter = ProductionObservationAdapter()
    assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED
    assert adapter.is_ready is False

    # Invoking capture before initialization raises CapabilityUnavailableError
    with pytest.raises(CapabilityUnavailableError):
        await adapter.capture_screen()

    await adapter.initialize()
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert adapter.is_ready is True

    health = await adapter.get_health()
    assert health.status in {CapabilityHealthStatus.HEALTHY, CapabilityHealthStatus.DEGRADED}
    assert "providers" in health.details

    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED


@pytest.mark.asyncio
async def test_production_pointer_adapter_boundary():
    adapter = ProductionPointerAdapter()
    assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED
    assert adapter.is_ready is False

    # Invoking move_to before initialization raises CapabilityUnavailableError
    with pytest.raises(CapabilityUnavailableError):
        await adapter.move_to(100, 100)

    # Clicks before initialization raise CapabilityUnavailableError
    with pytest.raises(CapabilityUnavailableError):
        await adapter.click(100, 100)

    await adapter.initialize()
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert adapter.is_ready is True

    # Clicks are active and supported in M1.2B
    assert await adapter.click(100, 100, dwell_ms=10.0) is True

    # Emergency release is always safe
    assert await adapter.emergency_release_all() is True
    assert await adapter.get_lockout_state() == "NORMAL"

    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.HEALTHY
    assert "action_counter" in health.details

    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED


@pytest.mark.asyncio
async def test_production_pointer_adapter_abi_failure_fail_closed():
    # Simulated ABI mismatch must fail closed during initialize
    adapter = ProductionPointerAdapter(abi_override={"sizeof_mouseinput": 48})
    with pytest.raises(CapabilityInitializationError) as exc_info:
        await adapter.initialize()
    assert "ABI" in str(exc_info.value)
    assert adapter.lifecycle_state == CapabilityLifecycleState.FAILED

    with pytest.raises(CapabilityUnavailableError):
        await adapter.move_to(100, 100)


@pytest.mark.asyncio
async def test_production_keyboard_adapter_boundary():
    adapter = ProductionKeyboardAdapter(enable_live_injection=False)

    with pytest.raises(CapabilityInitializationError):
        await adapter.initialize()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.type_text("test")

    assert await adapter.emergency_release_all() is True


@pytest.mark.asyncio
async def test_production_takeover_adapter_boundary():
    adapter = ProductionHumanTakeoverAdapter(enable_live_hooks=False)

    with pytest.raises(CapabilityInitializationError):
        await adapter.initialize()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.start_monitoring(lambda: None)


@pytest.mark.asyncio
async def test_production_workspace_adapter_boundary():
    adapter = ProductionWorkspaceAdapter(enable_live_appbar=False)

    with pytest.raises(CapabilityInitializationError):
        await adapter.initialize()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.register_appbar("right", 300)


@pytest.mark.asyncio
async def test_production_safety_coordinator():
    adapter = ProductionSafetyCoordinator()
    assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED

    await adapter.initialize()
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert adapter.is_ready is True

    assert await adapter.is_safe_state() is True
    assert await adapter.emergency_stop_all() is True

    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.HEALTHY
