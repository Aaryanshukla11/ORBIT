"""Base adapter interfaces, lifecycle management, and exception hierarchies."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, Optional

from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
)

logger = logging.getLogger(__name__)


# ============================================================================
# EXCEPTION HIERARCHY
# ============================================================================

class OrbitCapabilityError(Exception):
    """Base exception for all capability adapter errors."""

    def __init__(self, capability: str, message: str, recoverable: bool = True) -> None:
        self.capability = capability
        self.message = message
        self.recoverable = recoverable
        super().__init__(f"[{capability}] {message}")


class DuplicateRegistrationError(OrbitCapabilityError):
    """Raised when attempting to register a capability type that already exists."""

    def __init__(self, capability_type: CapabilityType) -> None:
        super().__init__(capability_type.value, f"Capability '{capability_type.value}' is already registered")


class CapabilityNotFoundError(OrbitCapabilityError):
    """Raised when resolving a capability type that is not registered."""

    def __init__(self, capability_type: CapabilityType) -> None:
        super().__init__(capability_type.value, f"Capability '{capability_type.value}' is not registered in registry")


class CapabilityUnavailableError(OrbitCapabilityError):
    """Raised when invoking a capability that is not in the READY lifecycle state."""

    def __init__(self, capability_type: CapabilityType, state: CapabilityLifecycleState, reason: str = "") -> None:
        msg = f"Capability '{capability_type.value}' is unavailable (state: {state.value})"
        if reason:
            msg += f": {reason}"
        super().__init__(capability_type.value, msg)


class CapabilityInitializationError(OrbitCapabilityError):
    """Raised when a capability adapter fails to initialize."""

    def __init__(self, capability_type: CapabilityType, message: str) -> None:
        super().__init__(capability_type.value, f"Initialization failed for '{capability_type.value}': {message}")


class ObservationError(OrbitCapabilityError):
    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__("Observation", message, recoverable)


class PointerError(OrbitCapabilityError):
    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__("Pointer", message, recoverable)


class KeyboardError(OrbitCapabilityError):
    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__("Keyboard", message, recoverable)


class HumanTakeoverError(OrbitCapabilityError):
    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__("HumanTakeover", message, recoverable)


class WorkspaceError(OrbitCapabilityError):
    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__("Workspace", message, recoverable)


class SafetyError(OrbitCapabilityError):
    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__("EmergencySafety", message, recoverable)


# ============================================================================
# BASE CAPABILITY ADAPTER
# ============================================================================

class BaseCapabilityAdapter(ABC):
    """Abstract base class providing standard lifecycle management for all capability adapters."""

    def __init__(
        self,
        capability_name: str,
        capability_type: CapabilityType,
        adapter_mode: AdapterMode = AdapterMode.MOCK,
    ) -> None:
        self._capability_name = capability_name
        self._capability_type = capability_type
        self._adapter_mode = adapter_mode
        self._lifecycle_state = CapabilityLifecycleState.CREATED
        self._health_status = CapabilityHealthStatus.HEALTHY
        self._error_count = 0
        self._last_error: Optional[str] = None
        self._details: Dict[str, Any] = {}

    @property
    def capability_name(self) -> str:
        return self._capability_name

    @property
    def capability_type(self) -> CapabilityType:
        return self._capability_type

    @property
    def adapter_mode(self) -> AdapterMode:
        return self._adapter_mode

    @property
    def lifecycle_state(self) -> CapabilityLifecycleState:
        return self._lifecycle_state

    @property
    def is_ready(self) -> bool:
        return self._lifecycle_state == CapabilityLifecycleState.READY

    async def initialize(self) -> None:
        """Standard template method for initializing adapter resources."""
        if self._lifecycle_state == CapabilityLifecycleState.READY:
            return

        self._lifecycle_state = CapabilityLifecycleState.INITIALIZING
        try:
            await self._on_initialize()
            self._lifecycle_state = CapabilityLifecycleState.READY
            self._health_status = CapabilityHealthStatus.HEALTHY
            logger.info("Adapter initialized successfully: %s (%s)", self._capability_name, self._adapter_mode.value)
        except Exception as ex:
            self._lifecycle_state = CapabilityLifecycleState.FAILED
            self._health_status = CapabilityHealthStatus.FAILED
            self._error_count += 1
            self._last_error = str(ex)
            logger.error("Adapter initialization failed: %s: %s", self._capability_name, ex)
            raise CapabilityInitializationError(self._capability_type, str(ex)) from ex

    async def shutdown(self) -> None:
        """Standard template method for gracefully shutting down adapter resources."""
        if self._lifecycle_state in {CapabilityLifecycleState.STOPPED, CapabilityLifecycleState.CREATED}:
            return

        self._lifecycle_state = CapabilityLifecycleState.STOPPING
        try:
            await self._on_shutdown()
        except Exception as ex:
            logger.warning("Error during adapter shutdown for %s: %s", self._capability_name, ex)
            self._last_error = str(ex)
            self._error_count += 1
        finally:
            self._lifecycle_state = CapabilityLifecycleState.STOPPED
            logger.info("Adapter stopped: %s", self._capability_name)

    async def get_health(self) -> CapabilityHealth:
        """Generate a structured health diagnostic report."""
        status = self._health_status
        if self._lifecycle_state == CapabilityLifecycleState.FAILED:
            status = CapabilityHealthStatus.FAILED
        elif self._lifecycle_state != CapabilityLifecycleState.READY:
            status = CapabilityHealthStatus.UNAVAILABLE

        return CapabilityHealth(
            capability_name=self._capability_name,
            capability_type=self._capability_type,
            adapter_mode=self._adapter_mode,
            lifecycle_state=self._lifecycle_state,
            status=status,
            error_count=self._error_count,
            last_error=self._last_error,
            details=dict(self._details),
        )

    # Subclass hooks
    async def _on_initialize(self) -> None:
        """Hook for concrete adapter initialization logic."""
        pass

    async def _on_shutdown(self) -> None:
        """Hook for concrete adapter resource cleanup."""
        pass
