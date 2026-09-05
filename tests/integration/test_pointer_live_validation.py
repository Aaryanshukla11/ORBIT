"""Controlled Live Validation Suite for ProductionPointerAdapter on Windows OS.

Classifies all pointer executions honestly according to the epistemic validation taxonomy:
- LIVE_OS_VALIDATED: Tested directly against live Win32 SendInput and GetCursorPos on real OS.
- CONTROLLED_LIVE_ENVIRONMENT: Tested in controlled async test harnesses on real OS.
- INTERNAL_LOGIC_VALIDATED: Normalization math, cancellations, and ABI layout verified.
"""

import asyncio
import sys
import time
import pytest

from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.pointer.movement import MovementEvidenceLevel, MovementStatus
from orbit.contracts.capabilities import (
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
)
from orbit.models.common import ScreenPoint
from orbit.runtime.cancellation import CancellationSource


@pytest.mark.asyncio
async def test_live_os_pointer_validation():
    """Execute controlled live pointer movement validation against the Windows host."""
    if sys.platform != "win32":
        pytest.skip("Live OS pointer validation requires Windows platform")

    results = {}

    # Step 1: Initialize ProductionPointerAdapter (includes Win32 ABI Gate)
    adapter = ProductionPointerAdapter(tolerance_px=1)
    t0 = time.perf_counter()
    await adapter.initialize()
    init_duration_ms = (time.perf_counter() - t0) * 1000.0

    assert adapter.is_ready is True
    results["adapter_initialization_and_abi_gate"] = {
        "classification": "LIVE_OS_VALIDATED",
        "duration_ms": init_duration_ms,
        "lifecycle_state": adapter.lifecycle_state.value,
        "abi_status": adapter.health_tracker.abi_status,
    }

    # Step 2: Query Live Desktop Topology
    virtual_desktop = adapter._details.get("virtual_desktop", {})
    assert virtual_desktop["width"] > 0
    assert virtual_desktop["height"] > 0
    results["display_topology"] = {
        "classification": "LIVE_OS_VALIDATED",
        "topology": virtual_desktop,
    }

    # Step 3: Record Original Cursor Position
    original_pos: ScreenPoint = await adapter.get_cursor_position()
    assert original_pos.x >= 0
    assert original_pos.y >= 0
    results["initial_cursor_readback"] = {
        "classification": "LIVE_OS_VALIDATED",
        "original_pos": (original_pos.x, original_pos.y),
    }

    # Step 4: Controlled Safe Movement (Move to Center of Primary Screen)
    target_x = virtual_desktop["origin_x"] + virtual_desktop["width"] // 2
    target_y = virtual_desktop["origin_y"] + virtual_desktop["height"] // 2

    t_mov0 = time.perf_counter()
    success = await adapter.move_to(target_x, target_y)
    mov_duration_ms = (time.perf_counter() - t_mov0) * 1000.0

    assert success is True

    # Step 5: Readback and Tolerance Verification
    new_pos: ScreenPoint = await adapter.get_cursor_position()
    delta_x = abs(new_pos.x - target_x)
    delta_y = abs(new_pos.y - target_y)

    assert delta_x <= 1
    assert delta_y <= 1

    results["controlled_movement_and_readback"] = {
        "classification": "LIVE_OS_VALIDATED",
        "target": (target_x, target_y),
        "observed": (new_pos.x, new_pos.y),
        "delta_px": (delta_x, delta_y),
        "duration_ms": mov_duration_ms,
        "verified": True,
    }

    # Step 6: Cancellation-Before-Dispatch Verification
    cancel_source = CancellationSource()
    cancel_source.cancel("Controlled test preemption")
    with pytest.raises(Exception) as exc_info:
        await adapter.move_to(target_x, target_y, cancellation_token=cancel_source.token)
    assert "CANCELLED_BEFORE_DISPATCH" in str(exc_info.value)

    results["cancellation_before_dispatch"] = {
        "classification": "CONTROLLED_LIVE_ENVIRONMENT",
        "outcome": "CANCELLED_BEFORE_DISPATCH",
    }

    # Step 7: Restore Original Cursor Position via the same authorized SendInput pipeline
    await adapter.move_to(original_pos.x, original_pos.y)
    restored_pos: ScreenPoint = await adapter.get_cursor_position()
    assert abs(restored_pos.x - original_pos.x) <= 1
    assert abs(restored_pos.y - original_pos.y) <= 1

    results["cursor_restoration"] = {
        "classification": "LIVE_OS_VALIDATED",
        "restored_pos": (restored_pos.x, restored_pos.y),
    }

    # Step 8: Query Diagnostic Health
    health = await adapter.get_health()
    assert health.status == CapabilityHealthStatus.HEALTHY
    results["diagnostic_health_and_telemetry"] = {
        "classification": "LIVE_OS_VALIDATED",
        "status": health.status.value,
        "action_counter": health.details["action_counter"],
    }

    # Step 9: Clean Shutdown
    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED
    results["clean_shutdown"] = {
        "classification": "CONTROLLED_LIVE_ENVIRONMENT",
        "final_state": adapter.lifecycle_state.value,
    }

    print("\n--- LIVE POINTER VALIDATION REPORT ---")
    for key, data in results.items():
        print(f"[{data['classification']}] {key}: {data}")


if __name__ == "__main__":
    asyncio.run(test_live_os_pointer_validation())
