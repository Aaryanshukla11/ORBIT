"""Pointer health tracking, observable action counters, and diagnostic reports."""

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


class ActionCounter(BaseModel):
    """Observable telemetry counter tracking all pointer dispatch and safety events."""

    sendinput_calls: int = 0
    requested_packets: int = 0
    accepted_packets: int = 0
    failed_dispatches: int = 0
    rejected_before_dispatch: int = 0
    topology_rejections: int = 0
    cancellations_before_dispatch: int = 0
    cancellations_after_dispatch: int = 0
    verified_movements: int = 0
    readback_mismatches: int = 0

    def record_sendinput_attempt(self, requested: int = 1) -> None:
        self.sendinput_calls += 1
        self.requested_packets += requested

    def record_dispatch_result(self, accepted: int) -> None:
        self.accepted_packets += accepted
        if accepted == 0:
            self.failed_dispatches += 1

    def record_rejected_before_dispatch(self, is_topology: bool = False) -> None:
        self.rejected_before_dispatch += 1
        if is_topology:
            self.topology_rejections += 1

    def record_cancellation(self, before_dispatch: bool) -> None:
        if before_dispatch:
            self.cancellations_before_dispatch += 1
        else:
            self.cancellations_after_dispatch += 1

    def record_movement_verification(self, is_verified: bool) -> None:
        if is_verified:
            self.verified_movements += 1
        else:
            self.readback_mismatches += 1


class PointerHealthTracker:
    """Manages diagnostic state and produces CapabilityHealth reports for Pointer."""

    def __init__(self) -> None:
        self.action_counter = ActionCounter()
        self.last_error: Optional[str] = None
        self.last_latency_us: float = 0.0
        self.abi_status: str = "NOT_EVALUATED"

    def evaluate_health(self, lifecycle_state: CapabilityLifecycleState) -> CapabilityHealth:
        """Calculate high-level CapabilityHealth from action counter and lifecycle state."""
        if lifecycle_state == CapabilityLifecycleState.FAILED:
            status = CapabilityHealthStatus.FAILED
        elif lifecycle_state != CapabilityLifecycleState.READY:
            status = CapabilityHealthStatus.UNAVAILABLE
        elif self.action_counter.failed_dispatches > 0 or self.action_counter.readback_mismatches > 0:
            status = CapabilityHealthStatus.DEGRADED
        else:
            status = CapabilityHealthStatus.HEALTHY

        details = {
            "abi_status": self.abi_status,
            "action_counter": self.action_counter.model_dump(),
            "last_latency_us": self.last_latency_us,
        }

        total_errors = (
            self.action_counter.failed_dispatches
            + self.action_counter.topology_rejections
            + self.action_counter.readback_mismatches
        )

        return CapabilityHealth(
            capability_name="ProductionPointer",
            capability_type=CapabilityType.POINTER,
            adapter_mode=AdapterMode.PRODUCTION,
            lifecycle_state=lifecycle_state,
            status=status,
            error_count=total_errors,
            last_error=self.last_error,
            details=details,
        )
