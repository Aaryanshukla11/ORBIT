"""Unit tests for observation freshness evaluation and generation tracking."""

import time
from datetime import datetime, timezone
import pytest

from orbit.adapters.observation.freshness import FreshnessEvaluator
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
)
from orbit.models.common import BoundingBox


def _create_test_snapshot(
    snapshot_id: str = "snap_test",
    timestamp_ns: int = 0,
    generation_id: int = 1,
) -> ObservationSnapshot:
    return ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=generation_id,
        timestamp_ns=timestamp_ns,
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=10.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
    )


def test_fresh_snapshot_evaluation():
    evaluator = FreshnessEvaluator(fresh_threshold_ms=250.0, max_ttl_ms=500.0)
    now_ns = time.perf_counter_ns()
    # 50ms old snapshot
    snap = _create_test_snapshot(timestamp_ns=now_ns - int(50 * 1_000_000), generation_id=5)

    state, is_stale, reason = evaluator.evaluate_freshness(snap, current_generation=5)
    assert state == FreshnessState.FRESH
    assert is_stale is False
    assert reason is None


def test_aging_snapshot_evaluation():
    evaluator = FreshnessEvaluator(fresh_threshold_ms=250.0, max_ttl_ms=500.0)
    now_ns = time.perf_counter_ns()
    # 350ms old snapshot (between 250ms and 500ms)
    snap = _create_test_snapshot(timestamp_ns=now_ns - int(350 * 1_000_000), generation_id=5)

    state, is_stale, reason = evaluator.evaluate_freshness(snap, current_generation=5)
    assert state == FreshnessState.AGING
    assert is_stale is False
    assert reason is None


def test_ttl_expired_stale_snapshot():
    evaluator = FreshnessEvaluator(fresh_threshold_ms=250.0, max_ttl_ms=500.0)
    now_ns = time.perf_counter_ns()
    # 600ms old snapshot (exceeds 500ms TTL)
    snap = _create_test_snapshot(timestamp_ns=now_ns - int(600 * 1_000_000), generation_id=5)

    state, is_stale, reason = evaluator.evaluate_freshness(snap, current_generation=5)
    assert state == FreshnessState.STALE
    assert is_stale is True
    assert "TTL_EXPIRED" in reason


def test_generation_mismatch_invalidation():
    evaluator = FreshnessEvaluator(fresh_threshold_ms=250.0, max_ttl_ms=500.0)
    now_ns = time.perf_counter_ns()
    # Young timestamp but old generation (e.g. desktop window focus changed)
    snap = _create_test_snapshot(timestamp_ns=now_ns - int(20 * 1_000_000), generation_id=4)

    state, is_stale, reason = evaluator.evaluate_freshness(snap, current_generation=5)
    assert state == FreshnessState.STALE
    assert is_stale is True
    assert "GENERATION_MISMATCH" in reason


def test_invalid_zero_timestamp():
    evaluator = FreshnessEvaluator()
    snap = _create_test_snapshot(timestamp_ns=0, generation_id=1)

    state, is_stale, reason = evaluator.evaluate_freshness(snap, current_generation=1)
    assert state == FreshnessState.UNKNOWN
    assert is_stale is True
    assert reason == "INVALID_TIMESTAMP"


def test_future_timestamp_clock_anomaly():
    evaluator = FreshnessEvaluator()
    now_ns = time.perf_counter_ns()
    snap = _create_test_snapshot(timestamp_ns=now_ns + int(10_000 * 1_000_000), generation_id=1)

    state, is_stale, reason = evaluator.evaluate_freshness(snap, current_generation=1)
    assert state == FreshnessState.UNKNOWN
    assert is_stale is True
    assert reason == "FUTURE_TIMESTAMP_DETECTED"
