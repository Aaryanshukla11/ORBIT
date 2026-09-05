"""Controlled Live Validation Suite for ProductionObservationAdapter on Windows OS.

Classifies all observations honestly according to the epistemic validation taxonomy:
- LIVE_OS_VALIDATED: Tested directly against live Win32 GDI display and window subsystems.
- CONTROLLED_LIVE_ENVIRONMENT: Tested in controlled async test harnesses on real OS.
- INTERNAL_LOGIC_VALIDATED: Model conversions and threshold calculations verified.
"""

import asyncio
import sys
import time
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
)
from orbit.contracts.capabilities import (
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    FrameData,
)


@pytest.mark.asyncio
async def test_live_os_observation_validation():
    """Execute live observation validation against the Windows OS desktop."""
    if sys.platform != "win32":
        pytest.skip("Live OS observation validation requires Windows platform")

    results = {}

    # Step 1: Adapter Initialization
    adapter = ProductionObservationAdapter(default_ttl_ms=500.0)
    t0 = time.perf_counter()
    await adapter.initialize()
    init_duration_ms = (time.perf_counter() - t0) * 1000.0

    assert adapter.is_ready is True
    results["adapter_initialization"] = {
        "classification": "LIVE_OS_VALIDATED",
        "duration_ms": init_duration_ms,
        "state": adapter.lifecycle_state.value,
    }

    # Step 2: Query Live Display Topology
    metrics = await adapter.get_display_metrics()
    assert len(metrics) > 0
    assert metrics[0].bounds.width > 0
    assert metrics[0].bounds.height > 0
    results["display_topology"] = {
        "classification": "LIVE_OS_VALIDATED",
        "display_count": len(metrics),
        "primary_bounds": {
            "left": metrics[0].bounds.left,
            "top": metrics[0].bounds.top,
            "width": metrics[0].bounds.width,
            "height": metrics[0].bounds.height,
        },
    }

    # Step 3: Real Screen Frame Capture (GDI)
    t_cap0 = time.perf_counter()
    frame = await adapter.capture_screen()
    cap_duration_ms = (time.perf_counter() - t_cap0) * 1000.0

    assert isinstance(frame, FrameData)
    assert len(frame.raw_bytes) > 1000  # Non-trivial JPEG payload
    assert frame.resolution.width > 0
    results["screen_capture"] = {
        "classification": "LIVE_OS_VALIDATED",
        "frame_id": frame.frame_id,
        "bytes_count": len(frame.raw_bytes),
        "format": frame.format,
        "duration_ms": cap_duration_ms,
    }

    # Step 4: Multi-Source Observation Snapshot (Windows + Accessibility)
    t_snap0 = time.perf_counter()
    snapshot = await adapter.capture_snapshot()
    snap_duration_ms = (time.perf_counter() - t_snap0) * 1000.0

    assert isinstance(snapshot, ObservationSnapshot)
    assert snapshot.coordinate_space == CoordinateSpace.VIRTUAL_DESKTOP
    assert snapshot.freshness_state in {FreshnessState.FRESH, FreshnessState.AGING}
    assert snapshot.is_stale is False

    results["snapshot_capture"] = {
        "classification": "LIVE_OS_VALIDATED",
        "snapshot_id": snapshot.snapshot_id,
        "generation_id": snapshot.generation_id,
        "windows_observed": len(snapshot.windows),
        "elements_detected": len(snapshot.detected_elements),
        "coordinate_space": snapshot.coordinate_space.value,
        "freshness_state": snapshot.freshness_state.value,
        "duration_ms": snap_duration_ms,
    }

    # Step 5: Provider Health Reporting
    health = await adapter.get_health()
    assert health.status in {CapabilityHealthStatus.HEALTHY, CapabilityHealthStatus.DEGRADED}
    results["provider_health"] = {
        "classification": "LIVE_OS_VALIDATED",
        "overall_status": health.status.value,
        "providers": list(health.details.get("providers", {}).keys()),
    }

    # Step 6: Clean Shutdown
    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED
    results["clean_shutdown"] = {
        "classification": "CONTROLLED_LIVE_ENVIRONMENT",
        "final_state": adapter.lifecycle_state.value,
    }

    print("\n--- LIVE VALIDATION REPORT ---")
    for key, data in results.items():
        print(f"[{data['classification']}] {key}: {data}")


if __name__ == "__main__":
    asyncio.run(test_live_os_observation_validation())
