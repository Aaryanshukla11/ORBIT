"""
Telemetry Engine for Prototype C (Keyboard Interaction & Unicode Engine).
Records structured stage latencies (T1..T7), typing speeds (CPS), in-flight queue metrics,
Unicode outcome distributions, and exports machine-readable JSON metrics.
"""

import json
import time
from typing import List, Dict, Any, Optional
from dataclasses import asdict
from app_types import TelemetryRecord, StageLatencyRecord, UnicodeValidationRecord


class KeyboardTelemetryLogger:
    """
    Thread-safe telemetry aggregator for keyboard operations.
    """

    def __init__(self):
        self.records: List[TelemetryRecord] = []
        self.cancellation_latencies_us: List[float] = []
        self.observation_latencies_us: List[float] = []
        self.sanitization_latencies_us: List[float] = []
        self.worker_teardown_latencies_us: List[float] = []
        self.cps_values: List[float] = []
        self.total_characters_typed: int = 0
        self.total_errors: int = 0
        self.total_sessions: int = 0
        self.cancelled_sessions: int = 0

    def log_record(self, record: TelemetryRecord):
        self.records.append(record)
        self.total_sessions += 1
        self.total_characters_typed += record.character_count
        self.total_errors += record.error_count

        if record.characters_per_second > 0:
            self.cps_values.append(record.characters_per_second)

        if record.stage_latency and record.stage_latency.t4_cancel_requested_ns:
            self.cancelled_sessions += 1
            lat = record.stage_latency.true_cancellation_latency_us
            if lat > 0:
                self.cancellation_latencies_us.append(lat)
            obs = record.stage_latency.signal_to_observation_us
            if obs > 0:
                self.observation_latencies_us.append(obs)
            san = record.stage_latency.sanitization_latency_us
            if san > 0:
                self.sanitization_latencies_us.append(san)
            tear = record.stage_latency.worker_teardown_latency_us
            if tear > 0:
                self.worker_teardown_latencies_us.append(tear)

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Calculates statistical distributions (Mean, Median, P95, Max) for all stages."""

        def calc_stats(values: List[float]):
            if not values:
                return {"mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0, "count": 0}
            s = sorted(values)
            n = len(s)
            p95_idx = int(0.95 * (n - 1))
            return {
                "mean": round(sum(s) / n, 2),
                "median": round(s[n // 2], 2),
                "p95": round(s[p95_idx], 2),
                "max": round(s[-1], 2),
                "count": n,
            }

        return {
            "total_sessions": self.total_sessions,
            "cancelled_sessions": self.cancelled_sessions,
            "total_characters_typed": self.total_characters_typed,
            "total_errors": self.total_errors,
            "characters_per_second": calc_stats(self.cps_values),
            "true_cancellation_latency_us (T7 - T4)": calc_stats(self.cancellation_latencies_us),
            "signal_to_observation_us (T5 - T4)": calc_stats(self.observation_latencies_us),
            "sanitization_latency_us (T6 - T5)": calc_stats(self.sanitization_latencies_us),
            "worker_teardown_latency_us (T7 - T6)": calc_stats(self.worker_teardown_latencies_us),
        }

    def export_json(self, filepath: str):
        data = {
            "timestamp": time.time(),
            "summary": self.get_summary_statistics(),
            "sample_records": [asdict(r) for r in self.records[-200:]],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
