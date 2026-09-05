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

    @property
    def capture_count(self) -> int:
        return self._capture_count

    @property
    def last_frame(self) -> Optional[FrameData]:
        return self._last_frame

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
