"""
Telemetry and Structured Diagnostics for ORBIT Prototype E.
(Phase 1 Telemetry Collector & Statistical Aggregator)

Collects microsecond timing measurements, validation outcomes,
DPI capability states, and diagnostic event logs.
"""

from dataclasses import asdict
import json
import statistics
import time
from typing import Any, Dict, List, Optional

from app_types import (
    PointerTelemetryRecord,
    ValidationFailureReason,
    TargetValidationStatus,
    PointerValidationResult,
    VirtualDesktopMetrics,
    DpiAwarenessStatus,
)


class Phase1TelemetryCollector:
    """Thread-safe collector for Phase 1 validation telemetry and performance metrics."""

    def __init__(self):
        self._records: List[PointerTelemetryRecord] = []
        self._dpi_status: Optional[DpiAwarenessStatus] = None
        self._metrics_samples: List[VirtualDesktopMetrics] = []
        self._validation_durations_us: List[float] = []
        self._normalization_durations_us: List[float] = []

    def record_dpi_status(self, status: DpiAwarenessStatus) -> None:
        self._dpi_status = status

    def record_virtual_metrics(self, metrics: VirtualDesktopMetrics) -> None:
        self._metrics_samples.append(metrics)

    def record_validation(
        self,
        operation_name: str,
        result: PointerValidationResult,
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> PointerTelemetryRecord:
        details = extra_details or {}
        if result.diagnostic_message:
            details["diagnostic_message"] = result.diagnostic_message
        if result.metrics_snapshot:
            details["virtual_width"] = result.metrics_snapshot.width
            details["virtual_height"] = result.metrics_snapshot.height

        self._validation_durations_us.append(result.validation_duration_us)

        record = PointerTelemetryRecord(
            operation_name=operation_name,
            timestamp_ns=time.perf_counter_ns(),
            duration_us=result.validation_duration_us,
            is_success=result.is_valid,
            failure_reason=result.failure_reason,
            details=details,
        )
        self._records.append(record)
        return record

    def record_normalization(
        self,
        duration_us: float,
        is_valid: bool,
        failure_reason: ValidationFailureReason = ValidationFailureReason.NONE,
        details: Optional[Dict[str, Any]] = None,
    ) -> PointerTelemetryRecord:
        self._normalization_durations_us.append(duration_us)
        record = PointerTelemetryRecord(
            operation_name="COORDINATE_NORMALIZATION",
            timestamp_ns=time.perf_counter_ns(),
            duration_us=duration_us,
            is_success=is_valid,
            failure_reason=failure_reason,
            details=details or {},
        )
        self._records.append(record)
        return record

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Calculates statistical summary across recorded operations."""
        val_count = len(self._validation_durations_us)
        norm_count = len(self._normalization_durations_us)

        val_stats = {}
        if val_count > 0:
            val_stats = {
                "count": val_count,
                "mean_us": round(statistics.mean(self._validation_durations_us), 2),
                "median_us": round(statistics.median(self._validation_durations_us), 2),
                "min_us": round(min(self._validation_durations_us), 2),
                "max_us": round(max(self._validation_durations_us), 2),
                "p95_us": round(
                    statistics.quantiles(self._validation_durations_us, n=20)[18]
                    if val_count >= 20
                    else max(self._validation_durations_us),
                    2,
                ),
            }

        norm_stats = {}
        if norm_count > 0:
            norm_stats = {
                "count": norm_count,
                "mean_us": round(statistics.mean(self._normalization_durations_us), 2),
                "median_us": round(statistics.median(self._normalization_durations_us), 2),
                "min_us": round(min(self._normalization_durations_us), 2),
                "max_us": round(max(self._normalization_durations_us), 2),
            }

        return {
            "total_records": len(self._records),
            "dpi_status": asdict(self._dpi_status) if self._dpi_status else None,
            "latest_metrics": asdict(self._metrics_samples[-1]) if self._metrics_samples else None,
            "validation_performance": val_stats,
            "normalization_performance": norm_stats,
        }

    def export_records_as_dicts(self) -> List[Dict[str, Any]]:
        return [
            {
                "operation_name": r.operation_name,
                "timestamp_ns": r.timestamp_ns,
                "duration_us": r.duration_us,
                "is_success": r.is_success,
                "failure_reason": r.failure_reason.value,
                "details": r.details,
            }
            for r in self._records
        ]


class Phase2bTelemetryCollector:
    """Collector for Phase 2B cursor movement telemetry and performance metrics."""

    def __init__(self):
        self._movement_records: List[Dict[str, Any]] = []
        self._durations_us: List[float] = []
        self._deltas_x: List[int] = []
        self._deltas_y: List[int] = []

    def record_movement(self, record: Dict[str, Any]) -> None:
        self._movement_records.append(record)
        if "duration_us" in record:
            self._durations_us.append(record["duration_us"])
        if "delta_px" in record and record["delta_px"] is not None:
            self._deltas_x.append(record["delta_px"][0])
            self._deltas_y.append(record["delta_px"][1])

    def get_summary_statistics(self) -> Dict[str, Any]:
        count = len(self._durations_us)
        lat_stats = {}
        if count > 0:
            lat_stats = {
                "count": count,
                "mean_us": round(statistics.mean(self._durations_us), 2),
                "median_us": round(statistics.median(self._durations_us), 2),
                "min_us": round(min(self._durations_us), 2),
                "max_us": round(max(self._durations_us), 2),
            }

        delta_stats = {}
        if self._deltas_x:
            delta_stats = {
                "max_delta_x": max(self._deltas_x),
                "max_delta_y": max(self._deltas_y),
                "mean_delta_x": round(statistics.mean(self._deltas_x), 2),
                "mean_delta_y": round(statistics.mean(self._deltas_y), 2),
            }

        return {
            "total_movements": len(self._movement_records),
            "latency_statistics": lat_stats,
            "delta_statistics": delta_stats,
            "records": self._movement_records,
        }

