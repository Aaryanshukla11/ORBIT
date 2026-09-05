"""Production Capability Registry and lifecycle management for ORBIT."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Type, TypeVar

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityNotFoundError,
    CapabilityUnavailableError,
    DuplicateRegistrationError,
)
from orbit.contracts.capabilities import (
    CapabilityHealth,
    CapabilityLifecycleState,
    CapabilityType,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Deterministic initialization order: Safety & boundaries first, then inputs
DEFAULT_INIT_ORDER: List[CapabilityType] = [
    CapabilityType.SAFETY,
    CapabilityType.WORKSPACE,
    CapabilityType.HUMAN_TAKEOVER,
    CapabilityType.OBSERVATION,
    CapabilityType.KEYBOARD,
    CapabilityType.POINTER,
]


class CapabilityRegistry:
    """Thread-safe registry managing the lifecycle, resolution, and health of capability adapters."""

    def __init__(self, init_order: Optional[List[CapabilityType]] = None) -> None:
        self._adapters: Dict[CapabilityType, BaseCapabilityAdapter] = {}
        self._init_order = init_order or list(DEFAULT_INIT_ORDER)
        self._lock = asyncio.Lock()
        self._is_initialized = False

    @property
    def registered_capabilities(self) -> Set[CapabilityType]:
        """Return set of all registered capability types."""
        return set(self._adapters.keys())

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def register(
        self,
        capability_type: CapabilityType,
        adapter: BaseCapabilityAdapter,
        override: bool = False,
    ) -> None:
        """Register a capability adapter in the registry.

        Raises DuplicateRegistrationError if already registered and override is False.
        """
        if capability_type in self._adapters and not override:
            raise DuplicateRegistrationError(capability_type)

        if adapter.capability_type != capability_type:
            raise ValueError(
                f"Adapter capability_type '{adapter.capability_type}' does not match target registration '{capability_type}'"
            )

        self._adapters[capability_type] = adapter
        logger.debug("Registered capability: %s (%s mode)", capability_type.value, adapter.adapter_mode.value)

    def resolve(self, capability_type: CapabilityType) -> BaseCapabilityAdapter:
        """Resolve an adapter by capability type.

        Raises CapabilityNotFoundError if not registered.
        """
        adapter = self._adapters.get(capability_type)
        if not adapter:
            raise CapabilityNotFoundError(capability_type)
        return adapter

    def resolve_typed(self, capability_type: CapabilityType, expected_type: Type[T]) -> T:
        """Resolve an adapter and verify it matches the expected type/protocol."""
        adapter = self.resolve(capability_type)
        if not isinstance(adapter, expected_type):
            raise TypeError(
                f"Resolved adapter for {capability_type.value} ({type(adapter).__name__}) does not match expected {expected_type.__name__}"
            )
        return adapter  # type: ignore

    def get_optional(self, capability_type: CapabilityType) -> Optional[BaseCapabilityAdapter]:
        """Return adapter if registered, else None."""
        return self._adapters.get(capability_type)

    def has(self, capability_type: CapabilityType) -> bool:
        """Check if capability is registered."""
        return capability_type in self._adapters

    def is_ready(self, capability_type: CapabilityType) -> bool:
        """Check if capability is registered and currently in READY lifecycle state."""
        adapter = self._adapters.get(capability_type)
        return adapter is not None and adapter.is_ready

    async def initialize_all(self) -> Dict[CapabilityType, CapabilityHealth]:
        """Initialize all registered adapters in deterministic order.

        Failure of one adapter is isolated and does not abort the initialization of others.
        Returns the health status of all registered capabilities.
        """
        async with self._lock:
            # Determine execution order (defined order first, then remaining)
            ordered_keys: List[CapabilityType] = [k for k in self._init_order if k in self._adapters]
            for k in self._adapters:
                if k not in ordered_keys:
                    ordered_keys.append(k)

            logger.info("Initializing capabilities in order: %s", [k.value for k in ordered_keys])

            for cap_type in ordered_keys:
                adapter = self._adapters[cap_type]
                try:
                    await adapter.initialize()
                except Exception as ex:
                    logger.warning("Failed to initialize capability %s: %s", cap_type.value, ex)

            self._is_initialized = True
            return await self.get_health_all()

    async def shutdown_all(self) -> None:
        """Gracefully shut down all registered adapters in reverse initialization order."""
        async with self._lock:
            ordered_keys: List[CapabilityType] = [k for k in self._init_order if k in self._adapters]
            for k in self._adapters:
                if k not in ordered_keys:
                    ordered_keys.append(k)

            # Reverse order for shutdown
            reverse_keys = list(reversed(ordered_keys))
            logger.info("Shutting down capabilities in order: %s", [k.value for k in reverse_keys])

            for cap_type in reverse_keys:
                adapter = self._adapters[cap_type]
                try:
                    await adapter.shutdown()
                except Exception as ex:
                    logger.warning("Error during capability %s shutdown: %s", cap_type.value, ex)

            self._is_initialized = False

    async def get_health_all(self) -> Dict[CapabilityType, CapabilityHealth]:
        """Collect health diagnostic reports from all registered capability adapters."""
        health_reports: Dict[CapabilityType, CapabilityHealth] = {}
        for cap_type, adapter in self._adapters.items():
            health_reports[cap_type] = await adapter.get_health()
        return health_reports
