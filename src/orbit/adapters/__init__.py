"""ORBIT Capability Adapters package."""

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityInitializationError,
    CapabilityNotFoundError,
    CapabilityUnavailableError,
    DuplicateRegistrationError,
    HumanTakeoverError,
    KeyboardError,
    ObservationError,
    OrbitCapabilityError,
    PointerError,
    SafetyError,
    WorkspaceError,
)
from orbit.adapters.factory import create_capability_registry
from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.production import (
    ProductionHumanTakeoverAdapter,
    ProductionKeyboardAdapter,
    ProductionObservationAdapter,
    ProductionPointerAdapter,
    ProductionSafetyCoordinator,
    ProductionWorkspaceAdapter,
)
from orbit.adapters.registry import CapabilityRegistry

__all__ = [
    # Base and exceptions
    "BaseCapabilityAdapter",
    "CapabilityInitializationError",
    "CapabilityNotFoundError",
    "CapabilityRegistry",
    "CapabilityUnavailableError",
    "DuplicateRegistrationError",
    "HumanTakeoverError",
    "KeyboardError",
    "ObservationError",
    "OrbitCapabilityError",
    "PointerError",
    "SafetyError",
    "WorkspaceError",
    "create_capability_registry",
    # Mocks
    "MockHumanTakeoverAdapter",
    "MockKeyboardAdapter",
    "MockObservationAdapter",
    "MockPointerAdapter",
    "MockSafetyCoordinator",
    "MockWorkspaceAdapter",
    # Production
    "ProductionHumanTakeoverAdapter",
    "ProductionKeyboardAdapter",
    "ProductionObservationAdapter",
    "ProductionPointerAdapter",
    "ProductionSafetyCoordinator",
    "ProductionWorkspaceAdapter",
]
