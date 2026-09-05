"""Unit tests for ObservationHealthTracker and multi-provider health diagnostics."""

import pytest

from orbit.adapters.observation.health import ObservationHealthTracker
from orbit.contracts.capabilities import (
    CapabilityHealthStatus,
    CapabilityLifecycleState,
)


def test_health_tracker_initial_state():
    tracker = ObservationHealthTracker()
    health_created = tracker.evaluate_overall_health(CapabilityLifecycleState.CREATED)
    assert health_created.status == CapabilityHealthStatus.UNAVAILABLE

    health_ready = tracker.evaluate_overall_health(CapabilityLifecycleState.READY)
    assert health_ready.status == CapabilityHealthStatus.HEALTHY


def test_health_tracker_records_success_and_failure():
    tracker = ObservationHealthTracker()

    tracker.record_success("GDI_CAPTURE", 12.5)
    tracker.record_success("WINDOW_TRACKER", 4.2)
    tracker.record_failure("MSAA", "COM element unhandled", is_timeout=False)

    health = tracker.evaluate_overall_health(CapabilityLifecycleState.READY)
    # GDI capture is healthy, but MSAA failed -> overall status is DEGRADED
    assert health.status == CapabilityHealthStatus.DEGRADED
    assert health.error_count == 1

    providers = health.details["providers"]
    assert providers["GDI_CAPTURE"]["successful_calls"] == 1
    assert providers["GDI_CAPTURE"]["last_latency_ms"] == 12.5
    assert providers["MSAA"]["failed_calls"] == 1
    assert "COM element unhandled" in providers["MSAA"]["last_error"]


def test_health_tracker_quarantine_state():
    tracker = ObservationHealthTracker()
    tracker.record_quarantine("UI_AUTOMATION", "Consecutive worker timeout threshold exceeded")

    health = tracker.evaluate_overall_health(CapabilityLifecycleState.READY)
    assert health.status == CapabilityHealthStatus.DEGRADED

    providers = health.details["providers"]
    assert providers["UI_AUTOMATION"]["is_quarantined"] is True
    assert providers["UI_AUTOMATION"]["status"] == "UNAVAILABLE"


def test_health_tracker_core_gdi_failure():
    tracker = ObservationHealthTracker()
    tracker.record_failure("GDI_CAPTURE", "Desktop DC access denied")

    health = tracker.evaluate_overall_health(CapabilityLifecycleState.READY)
    assert health.status == CapabilityHealthStatus.FAILED
