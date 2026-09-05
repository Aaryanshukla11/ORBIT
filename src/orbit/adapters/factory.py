"""Capability factory for instantiating mock and production adapters based on configuration."""

from __future__ import annotations

import logging
from typing import Optional

from orbit.adapters.base import BaseCapabilityAdapter
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
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType

logger = logging.getLogger(__name__)


def create_capability_registry(config: Optional[RuntimeConfig] = None) -> CapabilityRegistry:
    """Instantiate and register capability adapters according to the runtime configuration."""
    cfg = config or RuntimeConfig()
    registry = CapabilityRegistry()

    logger.info("Building CapabilityRegistry (Global Mode: %s)", cfg.adapter_mode.value)

    # 1. Observation Capability
    obs_mode = cfg.get_mode_for(CapabilityType.OBSERVATION)
    if obs_mode == AdapterMode.MOCK:
        registry.register(CapabilityType.OBSERVATION, MockObservationAdapter())
    else:
        registry.register(CapabilityType.OBSERVATION, ProductionObservationAdapter())

    # 2. Pointer Capability
    ptr_mode = cfg.get_mode_for(CapabilityType.POINTER)
    if ptr_mode == AdapterMode.MOCK:
        registry.register(CapabilityType.POINTER, MockPointerAdapter())
    else:
        registry.register(CapabilityType.POINTER, ProductionPointerAdapter())

    # 3. Keyboard Capability
    kbd_mode = cfg.get_mode_for(CapabilityType.KEYBOARD)
    if kbd_mode == AdapterMode.MOCK:
        registry.register(CapabilityType.KEYBOARD, MockKeyboardAdapter())
    else:
        registry.register(CapabilityType.KEYBOARD, ProductionKeyboardAdapter())

    # 4. Human Takeover Capability
    tkv_mode = cfg.get_mode_for(CapabilityType.HUMAN_TAKEOVER)
    if tkv_mode == AdapterMode.MOCK:
        registry.register(CapabilityType.HUMAN_TAKEOVER, MockHumanTakeoverAdapter())
    else:
        registry.register(CapabilityType.HUMAN_TAKEOVER, ProductionHumanTakeoverAdapter())

    # 5. Workspace Capability
    wsp_mode = cfg.get_mode_for(CapabilityType.WORKSPACE)
    if wsp_mode == AdapterMode.MOCK:
        registry.register(CapabilityType.WORKSPACE, MockWorkspaceAdapter())
    else:
        registry.register(CapabilityType.WORKSPACE, ProductionWorkspaceAdapter())

    # 6. Safety Coordinator
    sft_mode = cfg.get_mode_for(CapabilityType.SAFETY)
    if sft_mode == AdapterMode.MOCK:
        registry.register(CapabilityType.SAFETY, MockSafetyCoordinator())
    else:
        registry.register(CapabilityType.SAFETY, ProductionSafetyCoordinator())

    return registry
