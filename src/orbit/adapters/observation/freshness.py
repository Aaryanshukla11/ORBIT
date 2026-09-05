"""Observation freshness evaluation and temporal validity verification."""

from __future__ import annotations

import time
from typing import Optional, Tuple

from orbit.adapters.observation.snapshot import FreshnessState, ObservationSnapshot


class FreshnessEvaluator:
    """Evaluates the temporal validity and generation alignment of observation snapshots."""

    def __init__(
        self,
        fresh_threshold_ms: float = 250.0,
        max_ttl_ms: float = 500.0,
    ) -> None:
        self.fresh_threshold_ms = fresh_threshold_ms
        self.max_ttl_ms = max_ttl_ms

    def evaluate_freshness(
        self,
        snapshot: ObservationSnapshot,
        current_generation: int,
        custom_ttl_ms: Optional[float] = None,
    ) -> Tuple[FreshnessState, bool, Optional[str]]:
        """Evaluate snapshot freshness against active monotonic clock and desktop generation.

        Returns (FreshnessState, is_stale, invalidation_reason).
        """
        now_ns = time.perf_counter_ns()
        if snapshot.timestamp_ns <= 0:
            return FreshnessState.UNKNOWN, True, "INVALID_TIMESTAMP"

        age_ms = (now_ns - snapshot.timestamp_ns) / 1_000_000.0
        ttl_limit = custom_ttl_ms if custom_ttl_ms is not None else self.max_ttl_ms

        # 1. Negative age check (clock anomaly)
        if age_ms < -1.0:
            return FreshnessState.UNKNOWN, True, "FUTURE_TIMESTAMP_DETECTED"

        # 2. Desktop Generation Parity Check
        if snapshot.generation_id != current_generation:
            return (
                FreshnessState.STALE,
                True,
                f"GENERATION_MISMATCH (Snapshot: {snapshot.generation_id}, Active: {current_generation})",
            )

        # 3. TTL Expiry Check
        if age_ms > ttl_limit:
            return (
                FreshnessState.STALE,
                True,
                f"TTL_EXPIRED (Age: {age_ms:.1f}ms > Limit: {ttl_limit:.1f}ms)",
            )

        # 4. Aging vs Fresh classification
        if age_ms >= self.fresh_threshold_ms:
            return FreshnessState.AGING, False, None

        return FreshnessState.FRESH, False, None
