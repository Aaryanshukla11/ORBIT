"""Telemetry tracking and latency profiling for Human Takeover."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.adapters.takeover.classifier import InputSource, TakeoverEvidence


class LatencyStats(BaseModel):
    min: float = 0.0
    mean: float = 0.0
    p95: float = 0.0
    max: float = 0.0
    count: int = 0


class TakeoverTelemetrySnapshot(BaseModel):
    total_events_processed: int = 0
    takeover_events_triggered: int = 0
    deduplicated_events: int = 0
    ambiguous_events: int = 0
    last_takeover_reason: Optional[str] = None
    classification_latency_us: LatencyStats = Field(default_factory=LatencyStats)
    hook_to_signal_latency_us: LatencyStats = Field(default_factory=LatencyStats)


class TakeoverTelemetryLogger:
    """Thread-safe performance recorder for low-level hook latency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_events = 0
        self._takeovers_triggered = 0
        self._deduplicated_events = 0
        self._ambiguous_events = 0
        self._last_reason: Optional[str] = None
        self._classification_latencies_us: List[float] = []
        self._hook_to_signal_latencies_us: List[float] = []

    def log_evidence(
        self,
        evidence: TakeoverEvidence,
        is_primary_trigger: bool,
        hook_to_signal_us: float = 0.0,
    ) -> None:
        with self._lock:
            self._total_events += 1
            if evidence.classification_latency_us > 0:
                self._classification_latencies_us.append(evidence.classification_latency_us)

            if hook_to_signal_us > 0:
                self._hook_to_signal_latencies_us.append(hook_to_signal_us)

            if evidence.source == InputSource.INPUT_AMBIGUOUS:
                self._ambiguous_events += 1

            if is_primary_trigger:
                self._takeovers_triggered += 1
                self._last_reason = evidence.reason
            elif evidence.should_trigger_takeover:
                self._deduplicated_events += 1

    def get_snapshot(self) -> TakeoverTelemetrySnapshot:
        with self._lock:
            def _calc(vals: List[float]) -> LatencyStats:
                if not vals:
                    return LatencyStats()
                s = sorted(vals)
                n = len(s)
                p95_idx = int(0.95 * (n - 1))
                return LatencyStats(
                    min=round(s[0], 3),
                    mean=round(sum(s) / n, 3),
                    p95=round(s[p95_idx], 3),
                    max=round(s[-1], 3),
                    count=n,
                )

            return TakeoverTelemetrySnapshot(
                total_events_processed=self._total_events,
                takeover_events_triggered=self._takeovers_triggered,
                deduplicated_events=self._deduplicated_events,
                ambiguous_events=self._ambiguous_events,
                last_takeover_reason=self._last_reason,
                classification_latency_us=_calc(self._classification_latencies_us),
                hook_to_signal_latency_us=_calc(self._hook_to_signal_latencies_us),
            )

    def reset(self) -> None:
        with self._lock:
            self._total_events = 0
            self._takeovers_triggered = 0
            self._deduplicated_events = 0
            self._ambiguous_events = 0
            self._last_reason = None
            self._classification_latencies_us.clear()
            self._hook_to_signal_latencies_us.clear()
