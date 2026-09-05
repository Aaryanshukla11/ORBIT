"""Integration tests for ProductionObservationAdapter integrating Prototype D capabilities."""

import pytest
import sys

from orbit.adapters.base import (
    CapabilityInitializationError,
    CapabilityUnavailableError,
    ObservationError,
)
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
)
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
    FrameData,
)


@pytest.mark.asyncio
async def test_adapter_full_lifecycle():
    adapter = ProductionObservationAdapter(default_ttl_ms=500.0)
    assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED
    assert adapter.is_ready is False

    # 1. Initialize
    await adapter.initialize()
    assert adapter.lifecycle_state == CapabilityLifecycleState.READY
    assert adapter.is_ready is True

    # 2. Query Display Metrics
    metrics = await adapter.get_display_metrics()
    assert len(metrics) > 0
    assert metrics[0].bounds.width > 0
    assert metrics[0].bounds.height > 0
    assert metrics[0].is_primary is True

    # 3. Capture Screen (GDI virtual desktop capture)
    frame = await adapter.capture_screen()
    assert isinstance(frame, FrameData)
    assert frame.frame_id.startswith("frame_")
    assert frame.resolution.width > 0
    assert frame.resolution.height > 0
    assert len(frame.raw_bytes) > 0
    assert frame.format == "jpeg"

    # 4. Capture Observation Snapshot
    snapshot = await adapter.capture_snapshot()
    assert isinstance(snapshot, ObservationSnapshot)
    assert snapshot.snapshot_id.startswith("snap_")
    assert snapshot.desktop_geometry.width > 0
    assert snapshot.coordinate_space == CoordinateSpace.VIRTUAL_DESKTOP
    assert snapshot.freshness_state in {FreshnessState.FRESH, FreshnessState.AGING}
    assert snapshot.is_stale is False

    # 5. Health reporting
    health = await adapter.get_health()
    assert health.capability_name == "ProductionObservation"
    assert health.capability_type == CapabilityType.OBSERVATION
    assert health.adapter_mode == AdapterMode.PRODUCTION
    assert health.lifecycle_state == CapabilityLifecycleState.READY
    assert health.status in {CapabilityHealthStatus.HEALTHY, CapabilityHealthStatus.DEGRADED}
    assert "GDI_CAPTURE" in health.details["providers"]
    assert health.details["providers"]["GDI_CAPTURE"]["successful_calls"] >= 1

    # 6. Shutdown
    await adapter.shutdown()
    assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED
    assert adapter.is_ready is False


@pytest.mark.asyncio
async def test_repeated_lifecycle_execution():
    """Verify that repeated startup and shutdown cycles do not leak or corrupt state."""
    adapter = ProductionObservationAdapter()

    for cycle in range(3):
        await adapter.initialize()
        assert adapter.is_ready is True

        frame = await adapter.capture_screen()
        assert len(frame.raw_bytes) > 0

        await adapter.shutdown()
        assert adapter.is_ready is False


@pytest.mark.asyncio
async def test_uninitialized_calls_raise_unavailable():
    adapter = ProductionObservationAdapter()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.capture_screen()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.capture_snapshot()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.get_display_metrics()


@pytest.mark.asyncio
async def test_stopped_calls_raise_unavailable():
    adapter = ProductionObservationAdapter()
    await adapter.initialize()
    await adapter.shutdown()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.capture_screen()

    with pytest.raises(CapabilityUnavailableError):
        await adapter.capture_snapshot()
