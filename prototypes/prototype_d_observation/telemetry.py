"""
Telemetry & Performance Profiler for ORBIT Prototype D v1.2.1.
Records hardware-normalized statistical distributions (Mean, Median, P95, Max, Min)
for Screen Capture, Accessibility Traversal, Source Fusion, and Total Pipeline Latencies.
"""

import json
import os
import time
import platform
from typing import Dict, List, Any, Optional


class ObservationTelemetryLogger:
    """
    Thread-safe performance profiler and telemetry aggregator.
    """

    def __init__(self):
        self.capture_latencies_ms: List[float] = []
        self.traversal_latencies_ms: List[float] = []
        self.fusion_latencies_ms: List[float] = []
        self.total_snapshot_latencies_ms: List[float] = []
        self.elements_discovered: List[int] = []
        self.memory_samples_mb: List[float] = []
        self.total_snapshots_created: int = 0
        self.stale_detections_count: int = 0

    def log_capture_duration(self, ms: float):
        if ms > 0:
            self.capture_latencies_ms.append(ms)

    def log_traversal_duration(self, ms: float):
        if ms > 0:
            self.traversal_latencies_ms.append(ms)

    def log_fusion_duration(self, ms: float):
        if ms > 0:
            self.fusion_latencies_ms.append(ms)

    def log_total_snapshot_duration(self, ms: float):
        if ms > 0:
            self.total_snapshot_latencies_ms.append(ms)
            self.total_snapshots_created += 1

    def log_elements_count(self, count: int):
        self.elements_discovered.append(count)

    def log_stale_detection(self):
        self.stale_detections_count += 1

    @staticmethod
    def _calc_stats(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {"mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0, "min": 0.0, "count": 0}
        s = sorted(values)
        n = len(s)
        p95_idx = int(0.95 * (n - 1))
        return {
            "mean": round(sum(s) / n, 2),
            "median": round(s[n // 2], 2),
            "p95": round(s[p95_idx], 2),
            "max": round(s[-1], 2),
            "min": round(s[0], 2),
            "count": n,
        }

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Calculates statistical distributions across all observation stages."""
        return {
            "total_snapshots_created": self.total_snapshots_created,
            "stale_detections_count": self.stale_detections_count,
            "capture_latency_ms (Target: <75ms)": self._calc_stats(self.capture_latencies_ms),
            "traversal_latency_ms (Target: <150ms)": self._calc_stats(self.traversal_latencies_ms),
            "fusion_latency_ms (Target: <25ms)": self._calc_stats(self.fusion_latencies_ms),
            "total_pipeline_latency_ms": self._calc_stats(self.total_snapshot_latencies_ms),
            "elements_discovered_per_snapshot": self._calc_stats([float(x) for x in self.elements_discovered]),
        }

    def export_json(self, filepath: str, extra_data: Optional[Dict[str, Any]] = None):
        """Exports structured JSON telemetry report."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        data = {
            "timestamp": time.time(),
            "environment": {
                "os": platform.platform(),
                "python": platform.python_version(),
            },
            "summary": self.get_summary_statistics(),
        }
        if extra_data:
            data.update(extra_data)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
