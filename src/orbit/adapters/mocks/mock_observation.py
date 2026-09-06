"""Mock Observation Adapter for Milestone M0 and M1A."""

from __future__ import annotations

import io
import time
from typing import List, Optional
from PIL import Image

from orbit.adapters.base import BaseCapabilityAdapter
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityType,
    DisplayMetrics,
    FrameData,
    ObservationCapability,
)
from orbit.models.common import BoundingBox, Resolution


class MockObservationAdapter(BaseCapabilityAdapter, ObservationCapability):
    """Mock implementation of ObservationCapability generating synthetic test frames."""

    def __init__(
        self,
        default_resolution: Optional[Resolution] = None,
        health_status: CapabilityHealthStatus = CapabilityHealthStatus.HEALTHY,
    ) -> None:
        super().__init__(
            capability_name="MockObservation",
            capability_type=CapabilityType.OBSERVATION,
            adapter_mode=AdapterMode.MOCK,
        )
        self._resolution = default_resolution or Resolution(width=1920, height=1080, scale_factor=1.0)
        self._health_status = health_status
        self._capture_count = 0
        self._last_frame: Optional[FrameData] = None
        self._mock_snapshot: Optional[Any] = None
        self._mock_snapshots: List[Any] = []

    @property
    def capture_count(self) -> int:
        return self._capture_count

    @property
    def last_frame(self) -> Optional[FrameData]:
        return self._last_frame

    @property
    def mock_snapshot(self) -> Optional[Any]:
        return self._mock_snapshot

    @mock_snapshot.setter
    def mock_snapshot(self, snapshot: Optional[Any]) -> None:
        self._mock_snapshot = snapshot

    def queue_mock_snapshot(self, snapshot: Any) -> None:
        """Queue a snapshot to be returned sequentially by capture_snapshot."""
        self._mock_snapshots.append(snapshot)

    async def capture_snapshot(self, target_hwnd: Optional[int] = None) -> Any:
        self._capture_count += 1
        if self._mock_snapshots:
            return self._mock_snapshots.pop(0)

        if self._mock_snapshot is not None:
            if hasattr(self._mock_snapshot, "model_copy"):
                from uuid import uuid4
                return self._mock_snapshot.model_copy(
                    update={
                        "snapshot_id": f"{self._mock_snapshot.snapshot_id}_{uuid4().hex[:6]}",
                        "timestamp_ns": time.monotonic_ns(),
                    }
                )
            return self._mock_snapshot

        from datetime import datetime, timezone
        from uuid import uuid4
        from orbit.adapters.observation.snapshot import (
            CoordinateSpace,
            FreshnessState,
            ObservationConfidence,
            ObservationSnapshot,
        )
        return ObservationSnapshot(
            snapshot_id=f"snap_mock_{uuid4().hex[:8]}",
            generation_id=0,
            timestamp_ns=time.monotonic_ns(),
            timestamp_utc=datetime.now(timezone.utc),
            capture_duration_ms=5.0,
            desktop_geometry=BoundingBox(left=0, top=0, width=self._resolution.width, height=self._resolution.height),
            coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
            confidence=ObservationConfidence.CONFIRMED,
            freshness_state=FreshnessState.FRESH,
            is_stale=False,
        )


    async def capture_screen(self, display_index: int = 0) -> FrameData:
        self._capture_count += 1
        # Create a tiny synthetic solid color JPEG frame
        img = Image.new("RGB", (self._resolution.width, self._resolution.height), color=(30, 30, 40))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        frame_bytes = buffer.getvalue()

        frame = FrameData(
            frame_id=f"frame_{self._capture_count:06d}",
            timestamp_ns=time.monotonic_ns(),
            resolution=self._resolution,
            raw_bytes=frame_bytes,
            format="jpeg",
            roi=BoundingBox(left=0, top=0, width=self._resolution.width, height=self._resolution.height),
        )
        self._last_frame = frame
        self._details["capture_count"] = self._capture_count
        return frame

    async def get_display_metrics(self) -> List[DisplayMetrics]:
        return [
            DisplayMetrics(
                display_index=0,
                bounds=BoundingBox(left=0, top=0, width=self._resolution.width, height=self._resolution.height),
                resolution=self._resolution,
                is_primary=True,
            )
        ]
