"""Tests for ORBIT DiagnosticService and subsystem health evaluation."""

import pytest
import asyncio
from orbit.contracts.capabilities import CapabilityType
from orbit.runtime.diagnostics.models import DiagnosticStatus, SystemDiagnosticReport
from orbit.runtime.diagnostics.service import DiagnosticService
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig


@pytest.fixture
def mock_registry():
    cfg = RuntimeConfig()
    return create_capability_registry(cfg)


@pytest.mark.asyncio
async def test_diagnostic_service_run(mock_registry):
    await mock_registry.initialize_all()
    event_bus = EventBus()
    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=mock_registry,
    )
    await orchestrator.initialize()

    service = DiagnosticService(orchestrator=orchestrator)
    report = await service.run_diagnostics()

    assert isinstance(report, SystemDiagnosticReport)
    assert len(report.subsystems) >= 7
    assert report.overall_status in (DiagnosticStatus.HEALTHY, DiagnosticStatus.DEGRADED)

    # Check specific subsystems
    sub_ids = [s.subsystem_id for s in report.subsystems]
    assert "backend" in sub_ids
    assert "websocket" in sub_ids
    assert "execution_engine" in sub_ids
    assert "safety" in sub_ids
    assert "perception" in sub_ids
    assert "action" in sub_ids

    # Cached report check
    cached = await service.get_cached_or_fresh_report()
    assert cached.timestamp == report.timestamp

    await orchestrator.shutdown()
    await event_bus.close()
