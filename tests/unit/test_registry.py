"""Unit tests for CapabilityRegistry and lifecycle management."""

import pytest

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityInitializationError,
    CapabilityNotFoundError,
    CapabilityUnavailableError,
    DuplicateRegistrationError,
)
from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
    ObservationCapability,
    PointerCapability,
)


class FailingTestAdapter(BaseCapabilityAdapter):
    """Test adapter designed to fail during initialization."""

    def __init__(self, cap_type: CapabilityType = CapabilityType.POINTER) -> None:
        super().__init__(
            capability_name="FailingTestAdapter",
            capability_type=cap_type,
            adapter_mode=AdapterMode.PRODUCTION,
        )

    async def _on_initialize(self) -> None:
        raise RuntimeError("Simulated initialization hardware failure")


@pytest.mark.asyncio
async def test_registry_registration_and_resolution():
    registry = CapabilityRegistry()
    obs = MockObservationAdapter()
    registry.register(CapabilityType.OBSERVATION, obs)

    assert registry.has(CapabilityType.OBSERVATION) is True
    assert registry.has(CapabilityType.POINTER) is False

    resolved = registry.resolve(CapabilityType.OBSERVATION)
    assert resolved is obs

    typed_resolved = registry.resolve_typed(CapabilityType.OBSERVATION, ObservationCapability)
    assert typed_resolved is obs


def test_registry_duplicate_registration_rejected():
    registry = CapabilityRegistry()
    obs1 = MockObservationAdapter()
    obs2 = MockObservationAdapter()

    registry.register(CapabilityType.OBSERVATION, obs1)
    with pytest.raises(DuplicateRegistrationError):
        registry.register(CapabilityType.OBSERVATION, obs2)

    # Allowed with override=True
    registry.register(CapabilityType.OBSERVATION, obs2, override=True)
    assert registry.resolve(CapabilityType.OBSERVATION) is obs2


def test_registry_missing_capability_resolution():
    registry = CapabilityRegistry()
    with pytest.raises(CapabilityNotFoundError):
        registry.resolve(CapabilityType.POINTER)


def test_registry_type_mismatch_registration():
    registry = CapabilityRegistry()
    obs = MockObservationAdapter()  # capability_type = OBSERVATION

    with pytest.raises(ValueError) as exc_info:
        # Attempt to register observation adapter under POINTER
        registry.register(CapabilityType.POINTER, obs)
    assert "does not match" in str(exc_info.value)


@pytest.mark.asyncio
async def test_registry_deterministic_initialization():
    registry = CapabilityRegistry()
    sft = MockSafetyCoordinator()
    wsp = MockWorkspaceAdapter()
    tkv = MockHumanTakeoverAdapter()
    obs = MockObservationAdapter()
    kbd = MockKeyboardAdapter()
    ptr = MockPointerAdapter()

    # Register in random order
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.SAFETY, sft)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.HUMAN_TAKEOVER, tkv)
    registry.register(CapabilityType.WORKSPACE, wsp)

    assert registry.is_ready(CapabilityType.POINTER) is False

    health_reports = await registry.initialize_all()

    assert registry.is_initialized is True
    assert registry.is_ready(CapabilityType.POINTER) is True
    assert registry.is_ready(CapabilityType.OBSERVATION) is True
    assert registry.is_ready(CapabilityType.SAFETY) is True

    # Check health reports
    for cap_type, health in health_reports.items():
        assert health.lifecycle_state == CapabilityLifecycleState.READY
        assert health.status == CapabilityHealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_registry_partial_failure_isolation():
    registry = CapabilityRegistry()
    obs = MockObservationAdapter()
    failing_ptr = FailingTestAdapter(CapabilityType.POINTER)
    sft = MockSafetyCoordinator()

    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, failing_ptr)
    registry.register(CapabilityType.SAFETY, sft)

    health_reports = await registry.initialize_all()

    # Observation and Safety should be READY despite Pointer failing
    assert registry.is_ready(CapabilityType.OBSERVATION) is True
    assert registry.is_ready(CapabilityType.SAFETY) is True
    assert registry.is_ready(CapabilityType.POINTER) is False

    assert health_reports[CapabilityType.POINTER].lifecycle_state == CapabilityLifecycleState.FAILED
    assert health_reports[CapabilityType.POINTER].status == CapabilityHealthStatus.FAILED
    assert "Simulated initialization" in health_reports[CapabilityType.POINTER].last_error


@pytest.mark.asyncio
async def test_registry_shutdown_idempotent():
    registry = CapabilityRegistry()
    obs = MockObservationAdapter()
    registry.register(CapabilityType.OBSERVATION, obs)

    await registry.initialize_all()
    assert obs.is_ready is True

    await registry.shutdown_all()
    assert obs.lifecycle_state == CapabilityLifecycleState.STOPPED
    assert registry.is_ready(CapabilityType.OBSERVATION) is False

    # Second shutdown call should be safe and idempotent
    await registry.shutdown_all()
    assert obs.lifecycle_state == CapabilityLifecycleState.STOPPED
