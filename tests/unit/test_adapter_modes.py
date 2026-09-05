"""Unit tests for explicit adapter mode selection and no-silent-fallback invariant."""

import pytest

from orbit.adapters.factory import create_capability_registry
from orbit.adapters.mocks import (
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
)
from orbit.adapters.production import (
    ProductionHumanTakeoverAdapter,
    ProductionKeyboardAdapter,
    ProductionObservationAdapter,
    ProductionPointerAdapter,
    ProductionWorkspaceAdapter,
)
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
)


def test_global_mock_mode_selection():
    config = RuntimeConfig(adapter_mode=AdapterMode.MOCK)
    registry = create_capability_registry(config)

    for cap_type in [
        CapabilityType.OBSERVATION,
        CapabilityType.POINTER,
        CapabilityType.KEYBOARD,
        CapabilityType.HUMAN_TAKEOVER,
        CapabilityType.WORKSPACE,
        CapabilityType.SAFETY,
    ]:
        adapter = registry.resolve(cap_type)
        assert adapter.adapter_mode == AdapterMode.MOCK
        assert "Mock" in adapter.capability_name


def test_global_production_mode_selection():
    config = RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION)
    registry = create_capability_registry(config)

    for cap_type in [
        CapabilityType.OBSERVATION,
        CapabilityType.POINTER,
        CapabilityType.KEYBOARD,
        CapabilityType.HUMAN_TAKEOVER,
        CapabilityType.WORKSPACE,
        CapabilityType.SAFETY,
    ]:
        adapter = registry.resolve(cap_type)
        assert adapter.adapter_mode == AdapterMode.PRODUCTION
        assert "Production" in adapter.capability_name


def test_per_capability_mode_overrides():
    config = RuntimeConfig(
        adapter_mode=AdapterMode.MOCK,
        capability_overrides={
            CapabilityType.OBSERVATION: AdapterMode.PRODUCTION,
            CapabilityType.KEYBOARD: AdapterMode.PRODUCTION,
        },
    )
    registry = create_capability_registry(config)

    obs = registry.resolve(CapabilityType.OBSERVATION)
    assert isinstance(obs, ProductionObservationAdapter)
    assert obs.adapter_mode == AdapterMode.PRODUCTION

    kbd = registry.resolve(CapabilityType.KEYBOARD)
    assert isinstance(kbd, ProductionKeyboardAdapter)
    assert kbd.adapter_mode == AdapterMode.PRODUCTION

    ptr = registry.resolve(CapabilityType.POINTER)
    assert isinstance(ptr, MockPointerAdapter)
    assert ptr.adapter_mode == AdapterMode.MOCK


@pytest.mark.asyncio
async def test_no_silent_fallback_on_production_failure():
    """Verify that a failed production adapter NEVER silently reverts to a mock adapter."""
    config = RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION)
    registry = create_capability_registry(config)

    # Initialize all adapters in production mode
    health_reports = await registry.initialize_all()

    # Observation is active in M1.1 -> initializes to READY
    obs_adapter = registry.resolve(CapabilityType.OBSERVATION)
    assert isinstance(obs_adapter, ProductionObservationAdapter)  # NOT MockObservationAdapter!
    assert obs_adapter.adapter_mode == AdapterMode.PRODUCTION
    assert obs_adapter.lifecycle_state == CapabilityLifecycleState.READY

    # Pointer is active in M1.2A -> initializes to READY
    ptr_adapter = registry.resolve(CapabilityType.POINTER)
    assert isinstance(ptr_adapter, ProductionPointerAdapter)  # NOT MockPointerAdapter!
    assert ptr_adapter.adapter_mode == AdapterMode.PRODUCTION
    assert ptr_adapter.lifecycle_state == CapabilityLifecycleState.READY

    # Keyboard is active in M1.3 -> initializes to READY
    kbd_adapter = registry.resolve(CapabilityType.KEYBOARD)
    assert isinstance(kbd_adapter, ProductionKeyboardAdapter)  # NOT MockKeyboardAdapter!
    assert kbd_adapter.adapter_mode == AdapterMode.PRODUCTION
    assert kbd_adapter.lifecycle_state == CapabilityLifecycleState.READY

    # Human Takeover is active in M1.4 -> initializes to READY
    tkv_adapter = registry.resolve(CapabilityType.HUMAN_TAKEOVER)
    assert isinstance(tkv_adapter, ProductionHumanTakeoverAdapter)
    assert tkv_adapter.adapter_mode == AdapterMode.PRODUCTION
    assert tkv_adapter.lifecycle_state == CapabilityLifecycleState.READY

    # Workspace remains deferred -> should fail honestly
    wsp_adapter = registry.resolve(CapabilityType.WORKSPACE)
    assert isinstance(wsp_adapter, ProductionWorkspaceAdapter)
    assert wsp_adapter.adapter_mode == AdapterMode.PRODUCTION
    assert wsp_adapter.lifecycle_state == CapabilityLifecycleState.FAILED

    # Health must report honest status, never fake HEALTHY for failed capability
    assert health_reports[CapabilityType.OBSERVATION].status in {CapabilityHealthStatus.HEALTHY, CapabilityHealthStatus.DEGRADED}
    assert health_reports[CapabilityType.POINTER].status in {CapabilityHealthStatus.HEALTHY, CapabilityHealthStatus.DEGRADED}
    assert health_reports[CapabilityType.KEYBOARD].status in {CapabilityHealthStatus.HEALTHY, CapabilityHealthStatus.DEGRADED}
    assert health_reports[CapabilityType.HUMAN_TAKEOVER].status in {CapabilityHealthStatus.HEALTHY, CapabilityHealthStatus.DEGRADED}
    assert health_reports[CapabilityType.WORKSPACE].status == CapabilityHealthStatus.FAILED
