"""Integration tests for ProductionPointerAdapter lifecycle, movement execution, and deferred capabilities."""

import pytest

from orbit.adapters.base import (
    CapabilityInitializationError,
    CapabilityUnavailableError,
    PointerError,
)
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
)
from orbit.models.common import ScreenPoint


@pytest.mark.asyncio
async def test_production_pointer_adapter_full_lifecycle():
    adapter = ProductionPointerAdapter(
        cursorpos_override=lambda: (600, 400),
        sendinput_override=lambda n, ptr, sz: 1,
    )
    assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED
    assert adapter.is_ready is False

    # 1. Initialize
    await adapter.initialize()
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert adapter.is_ready is True

    # 2. Get cursor position
    pos = await adapter.get_cursor_position()
    assert isinstance(pos, ScreenPoint)
    assert pos.x == 600
    assert pos.y == 400

    # 3. Move to target coordinate
    success = await adapter.move_to(x=600, y=400)
    assert success is True

    # 4. Query Health
    health = await adapter.get_health()
    assert health.capability_name == "ProductionPointer"
    assert health.capability_type == CapabilityType.POINTER
    assert health.adapter_mode == AdapterMode.PRODUCTION
    assert health.status == CapabilityHealthStatus.HEALTHY
    assert health.details["action_counter"]["verified_movements"] >= 1

    # 5. Button and click operations execute safely
    assert await adapter.click(600, 400, dwell_ms=10.0) is True
    assert await adapter.press_down("left") is True
    assert await adapter.release_up("left") is True

    # 6. Safety functions
    assert await adapter.emergency_release_all() is True
    assert await adapter.get_lockout_state() == "NORMAL"

    # 7. Shutdown
    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED
    assert adapter.is_ready is False


@pytest.mark.asyncio
async def test_pointer_adapter_out_of_bounds_rejection():
    adapter = ProductionPointerAdapter()
    await adapter.initialize()

    # Move outside virtual desktop should raise PointerError fail-closed
    with pytest.raises(PointerError) as exc_info:
        await adapter.move_to(x=-1000, y=500)
    assert "REJECTED_OUT_OF_BOUNDS" in str(exc_info.value)

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_pointer_adapter_repeated_lifecycle():
    adapter = ProductionPointerAdapter()

    for _ in range(3):
        await adapter.initialize()
        assert adapter.is_ready is True
        await adapter.shutdown()
        assert adapter.is_ready is False
