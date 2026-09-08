"""ORBIT Model Runtime and Safe Switching Engine (Milestone M1.9 Step 4).

Exports all contracts, base classes, provider adapters, factories, and the central
ModelSessionManager.
"""

from __future__ import annotations

from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import (
    ActiveModelContext,
    ActiveTaskConflictError,
    ModelActivationRequest,
    ModelActivationResult,
    ModelActivationStatus,
    ModelInitializationError,
    ModelNotFoundError,
    ModelRuntimeCapability,
    ModelRuntimeError,
    ModelRuntimeHealth,
    ModelRuntimeInfo,
    ModelRuntimeKind,
    ModelRuntimeStatus,
    ModelSwitchPolicy,
    ModelSwitchRejectedError,
    ModelSwitchResult,
    ModelUnavailableError,
    NoActiveModelError,
    RuntimeInitializationResult,
    StaleModelGenerationError,
)
from orbit.runtime.model_runtime.factory import (
    ModelRuntimeFactory,
    create_model_runtime,
)
from orbit.runtime.model_runtime.providers import (
    MockModelRuntimeAdapter,
    OllamaRuntimeAdapter,
    OpenAICompatibleRuntimeAdapter,
)
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.model_runtime.router import (
    ModelRouter,
    ModelRoutingTier,
    PrivacyPolicy,
    RouteResolution,
    RoutingPolicy,
)

__all__ = [
    # Contracts & Enums
    "ModelRuntimeStatus",
    "ModelRuntimeKind",
    "ModelActivationStatus",
    "ModelSwitchPolicy",
    "ModelRuntimeCapability",
    "ModelRuntimeHealth",
    "RuntimeInitializationResult",
    "ModelRuntimeInfo",
    "ActiveModelContext",
    "ModelActivationRequest",
    "ModelActivationResult",
    "ModelSwitchResult",
    # Routing
    "ModelRouter",
    "ModelRoutingTier",
    "PrivacyPolicy",
    "RoutingPolicy",
    "RouteResolution",
    # Exceptions
    "ModelRuntimeError",
    "ModelNotFoundError",
    "ModelUnavailableError",
    "ModelInitializationError",
    "ActiveTaskConflictError",
    "StaleModelGenerationError",
    "NoActiveModelError",
    "ModelSwitchRejectedError",
    # Base and Factory
    "BaseModelRuntime",
    "ModelRuntimeFactory",
    "create_model_runtime",
    # Adapters
    "OllamaRuntimeAdapter",
    "OpenAICompatibleRuntimeAdapter",
    "MockModelRuntimeAdapter",
    # Manager
    "ModelSessionManager",
]
