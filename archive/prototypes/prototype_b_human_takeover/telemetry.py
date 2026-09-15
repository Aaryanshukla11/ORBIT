"""
Telemetry Engine for Prototype B.
Records structured event telemetry, measures detection and halt latencies,
and aggregates false positive/negative statistics.
"""

import time
import json
from typing import List, Dict, Any
from dataclasses import asdict
from app_types import TelemetryRecord


class TelemetryLogger:
    def __init__(self):
        self.records: List[TelemetryRecord] = []
        self.detection_latencies_us: List[float] = []
        self.halt_latencies_ms: List[float] = []
        self.false_positive_count: int = 0
        self.false_negative_count: int = 0
        self.ambiguous_event_count: int = 0
        self.takeover_count: int = 0

    def log_event(self, record: TelemetryRecord):
        self.records.append(record)
        if record.decision_latency_us > 0:
            self.detection_latencies_us.append(record.decision_latency_us)
        if record.decision == "PAUSE_REQUESTED":
            self.takeover_count += 1
        if record.input_source == "INPUT_AMBIGUOUS":
            self.ambiguous_event_count += 1

    def record_halt_latency(self, latency_ms: float):
        self.halt_latencies_ms.append(latency_ms)

    def record_false_positive(self):
        self.false_positive_count += 1

    def record_false_negative(self):
        self.false_negative_count += 1

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Calculates aggregated metrics and latency percentiles."""
        total_events = len(self.records)

        def calc_stats(values: List[float]):
            if not values:
                return {"min": 0.0, "mean": 0.0, "max": 0.0, "p95": 0.0}
            s = sorted(values)
            n = len(s)
            p95_idx = int(0.95 * (n - 1))
            return {
                "min": round(s[0], 3),
                "mean": round(sum(s) / n, 3),
                "max": round(s[-1], 3),
                "p95": round(s[p95_idx], 3),
                "count": n
            }

        return {
            "total_events_processed": total_events,
            "takeover_events_triggered": self.takeover_count,
            "false_positives": self.false_positive_count,
            "false_negatives": self.false_negative_count,
            "ambiguous_events": self.ambiguous_event_count,
            "detection_latency_us": calc_stats(self.detection_latencies_us),
            "halt_latency_ms": calc_stats(self.halt_latencies_ms),
        }

    def export_json(self, filepath: str):
        data = {
            "timestamp": time.time(),
            "summary": self.get_summary_statistics(),
            "event_sample": [asdict(r) for r in self.records[-200:]]  # Last 200 records
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
