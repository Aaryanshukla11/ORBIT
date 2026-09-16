"""Dynamic Perceptual Settle Detection (Phase 2D).

Ensures desktop perception captures occur only after UI animations, window transitions,
and rendering updates have fully settled below a perceptual delta threshold.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional, Tuple
from PIL import Image, ImageChops, ImageStat
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SettleResult(BaseModel):
    """Report on desktop perceptual settlement."""

    is_settled: bool = Field(..., description="Whether desktop visual delta settled below threshold")
    delta_ratio: float = Field(default=0.0, description="Measured pixel difference ratio between consecutive frames")
    settle_duration_ms: float = Field(default=0.0, description="Time spent waiting for desktop settlement")
    frames_sampled: int = Field(default=0, description="Number of frames sampled")
    stable_frames: int = Field(default=0, description="Number of consecutive stable frames recorded")

    @property
    def final_pixel_delta(self) -> float:
        return self.delta_ratio



class PerceptualSettleDetector:
    """Detects when desktop visual state has stabilized after an action."""

    def __init__(
        self,
        delta_threshold: float = 0.002,
        settle_threshold: Optional[float] = None,
        sample_interval_sec: float = 0.1,
        max_settle_timeout_sec: float = 2.0,
        max_settle_timeout: Optional[float] = None,
        min_settle_delay_sec: float = 0.15,
        min_stable_frames: int = 1,
    ) -> None:
        self.delta_threshold = settle_threshold if settle_threshold is not None else delta_threshold
        self.sample_interval_sec = sample_interval_sec
        self.max_settle_timeout_sec = max_settle_timeout if max_settle_timeout is not None else max_settle_timeout_sec
        self.min_settle_delay_sec = min_settle_delay_sec
        self.min_stable_frames = min_stable_frames

    @staticmethod
    def calculate_pixel_delta(img1: Image.Image, img2: Image.Image) -> float:
        """Alias for compute_image_difference."""
        return PerceptualSettleDetector.compute_image_difference(img1, img2)

    @staticmethod
    def compute_image_difference(img1: Image.Image, img2: Image.Image) -> float:
        """Compute normalized pixel difference ratio between two PIL images [0.0, 1.0]."""
        if img1 is None or img2 is None:
            return 1.0
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)

        diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
        stat = ImageStat.Stat(diff)
        avg_diff = sum(stat.mean) / (len(stat.mean) * 255.0) if stat.mean else 0.0
        return avg_diff

    def wait_until_settled(
        self,
        capture_fn: Any,
        initial_frame: Optional[Image.Image] = None,
    ) -> SettleResult:
        """Synchronous sampling until desktop visual differences settle below threshold."""
        t_start = time.perf_counter()
        time.sleep(self.min_settle_delay_sec)

        prev_frame = initial_frame
        if prev_frame is None:
            prev_frame = capture_fn()

        frames_sampled = 1
        stable_count = 0
        delta_ratio = 1.0

        while (time.perf_counter() - t_start) < self.max_settle_timeout_sec:
            time.sleep(self.sample_interval_sec)
            curr_frame = capture_fn()
            frames_sampled += 1

            if curr_frame is not None and prev_frame is not None:
                delta_ratio = self.compute_image_difference(prev_frame, curr_frame)
                if delta_ratio <= self.delta_threshold:
                    stable_count += 1
                    if stable_count >= self.min_stable_frames:
                        duration_ms = (time.perf_counter() - t_start) * 1000.0
                        return SettleResult(
                            is_settled=True,
                            delta_ratio=delta_ratio,
                            settle_duration_ms=duration_ms,
                            frames_sampled=frames_sampled,
                            stable_frames=stable_count,
                        )
                else:
                    stable_count = 0

            prev_frame = curr_frame

        duration_ms = (time.perf_counter() - t_start) * 1000.0
        return SettleResult(
            is_settled=(delta_ratio <= self.delta_threshold * 2.0),
            delta_ratio=delta_ratio,
            settle_duration_ms=duration_ms,
            frames_sampled=frames_sampled,
            stable_frames=stable_count,
        )

    async def wait_for_settle(
        self,
        capture_fn: Any,
        initial_frame: Optional[Image.Image] = None,
    ) -> Tuple[Image.Image, SettleResult]:
        """Sample consecutive frames until difference drops below threshold or timeout elapses."""
        t_start = time.perf_counter()
        await asyncio.sleep(self.min_settle_delay_sec)

        prev_frame = initial_frame
        if prev_frame is None:
            prev_frame = await capture_fn() if asyncio.iscoroutinefunction(capture_fn) else capture_fn()

        frames_sampled = 1
        delta_ratio = 1.0

        while (time.perf_counter() - t_start) < self.max_settle_timeout_sec:
            await asyncio.sleep(self.sample_interval_sec)
            curr_frame = await capture_fn() if asyncio.iscoroutinefunction(capture_fn) else capture_fn()
            frames_sampled += 1

            if curr_frame is not None and prev_frame is not None:
                delta_ratio = self.compute_image_difference(prev_frame, curr_frame)
                if delta_ratio <= self.delta_threshold:
                    duration_ms = (time.perf_counter() - t_start) * 1000.0
                    logger.debug("Desktop settled in %.1fms (delta_ratio=%.5f)", duration_ms, delta_ratio)
                    return curr_frame, SettleResult(
                        is_settled=True,
                        delta_ratio=delta_ratio,
                        settle_duration_ms=duration_ms,
                        frames_sampled=frames_sampled,
                    )

            prev_frame = curr_frame

        duration_ms = (time.perf_counter() - t_start) * 1000.0
        logger.debug("Desktop settle timeout after %.1fms (last delta_ratio=%.5f)", duration_ms, delta_ratio)
        return prev_frame, SettleResult(
            is_settled=(delta_ratio <= self.delta_threshold * 2.0),
            delta_ratio=delta_ratio,
            settle_duration_ms=duration_ms,
            frames_sampled=frames_sampled,
        )
