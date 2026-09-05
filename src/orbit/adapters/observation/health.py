"""Observation provider health tracking, circuit breaker states, and diagnostics."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
)

logger = logging.getLogger(__name__)


class ProviderHealthRecord(BaseModel):
    """Detailed diagnostic health report for a specific observation provider channel."""

    provider_name: str
    status: CapabilityHealthStatus = CapabilityHealthStatus.HEALTHY
    is_available: bool = True
    is_quarantined: bool = False
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    timeout_calls: int = 0
    last_latency_ms: float = 0.0
    last_error: Optional[str] = None


class ObservationHealthTracker:
    """Aggregates and evaluates multi-channel observation health."""

    def __init__(self) -> None:
        self._providers: Dict[str, ProviderHealthRecord] = {
            "GDI_CAPTURE": ProviderHealthRecord(provider_name="GDI_CAPTURE"),
            "WINDOW_TRACKER": ProviderHealthRecord(provider_name="WINDOW_TRACKER"),
            "WIN32_CONTROL": ProviderHealthRecord(provider_name="WIN32_CONTROL"),
            "MSAA": ProviderHealthRecord(provider_name="MSAA"),
            "UI_AUTOMATION": ProviderHealthRecord(provider_name="UI_AUTOMATION"),
            "VISUAL_ENGINE": ProviderHealthRecord(provider_name="VISUAL_ENGINE"),
        }

    def record_success(self, provider_name: str, duration_ms: float) -> None:
        rec = self._providers.get(provider_name)
        if rec:
            rec.total_calls += 1
            rec.successful_calls += 1
            rec.last_latency_ms = duration_ms
            rec.status = CapabilityHealthStatus.HEALTHY
            rec.is_available = True

    def record_failure(self, provider_name: str, error_msg: str, is_timeout: bool = False) -> None:
        rec = self._providers.get(provider_name)
        if rec:
            rec.total_calls += 1
            rec.failed_calls += 1
            rec.last_error = error_msg
            if is_timeout:
                rec.timeout_calls += 1
            rec.status = CapabilityHealthStatus.DEGRADED if rec.successful_calls > 0 else CapabilityHealthStatus.FAILED

    def record_quarantine(self, provider_name: str, reason: str) -> None:
        rec = self._providers.get(provider_name)
        if rec:
            rec.is_quarantined = True
            rec.status = CapabilityHealthStatus.UNAVAILABLE
            rec.last_error = f"QUARANTINED: {reason}"
            logger.warning("Observation provider %s QUARANTINED: %s", provider_name, reason)

    def evaluate_overall_health(self, lifecycle_state: CapabilityLifecycleState) -> CapabilityHealth:
        """Calculate high-level CapabilityHealth from multi-provider health records."""
        if lifecycle_state == CapabilityLifecycleState.FAILED:
            overall_status = CapabilityHealthStatus.FAILED
        elif lifecycle_state != CapabilityLifecycleState.READY:
            overall_status = CapabilityHealthStatus.UNAVAILABLE
        else:
            gdi_rec = self._providers["GDI_CAPTURE"]
            if gdi_rec.status == CapabilityHealthStatus.FAILED and gdi_rec.total_calls > 0:
                overall_status = CapabilityHealthStatus.FAILED
            elif any(
                p.status in {CapabilityHealthStatus.DEGRADED, CapabilityHealthStatus.UNAVAILABLE, CapabilityHealthStatus.FAILED}
                for p in self._providers.values()
            ):
                overall_status = CapabilityHealthStatus.DEGRADED
            else:
                overall_status = CapabilityHealthStatus.HEALTHY

        error_sum = sum(p.failed_calls for p in self._providers.values())
        last_err = next((p.last_error for p in self._providers.values() if p.last_error), None)

        details = {
            "providers": {k: v.model_dump() for k, v in self._providers.items()},
        }

        return CapabilityHealth(
            capability_name="ProductionObservation",
            capability_type=CapabilityType.OBSERVATION,
            adapter_mode=AdapterMode.PRODUCTION,
            lifecycle_state=lifecycle_state,
            status=overall_status,
            error_count=error_sum,
            last_error=last_err,
            details=details,
        )
