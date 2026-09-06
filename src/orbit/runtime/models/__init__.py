"""ORBIT AI Model Runtime Subsystem (Milestone M1.9 Step 3).

Provides provider-independent AI model discovery, registration, selection,
activation, safe runtime switching with atomic rollback, monotonic generation
tracking, runtime adapters, lifecycle management, file weight scanning,
installation, cloud provider integration, and system inventory reporting.
"""

from __future__ import annotations

from orbit.runtime.models.adapters import (
    AdapterCapabilityStatus,
    CloudRuntimeAdapter,
    LocalRuntimeAdapter,
    ModelRuntimeAdapter,
    OpenAICompatibleAdapter,
    create_runtime_adapter,
)
from orbit.runtime.models.capabilities import infer_capabilities, matches_capabilities
from orbit.runtime.models.discovery import (
    DiscoveryResult,
    ModelDiscoveryEngine,
    ProviderDiscoveryReport,
)
from orbit.runtime.models.file_scanner import (
    LocalFileModelScanner,
    parse_gguf_header_safe,
)
from orbit.runtime.models.health import HealthEvaluator, measure_roundtrip_latency
from orbit.runtime.models.installer import (
    InstallationProvider,
    ModelInstallationError,
    ModelInstaller,
    OllamaInstallationProvider,
)
from orbit.runtime.models.inventory import (
    CloudProviderInventorySummary,
    InventoryReport,
    ModelInventory,
    RuntimeInventorySummary,
    SystemCapabilitiesReport,
)
from orbit.runtime.models.lifecycle import (
    InvalidStateTransitionError,
    ModelLifecycleManager,
    ModelLifecycleTransition,
)
from orbit.runtime.models.manager import (
    CapabilityMismatchError,
    CloudAuthRequiredError,
    ModelManager,
    ModelManagerError,
    ModelNotFoundError,
    ModelSwitchError,
    ModelUnavailableError,
    NoActiveModelError,
    ProviderNotFoundError,
    ProviderUnhealthyError,
    StaleModelGenerationError,
)
from orbit.runtime.models.models import (
    ActiveModelSession,
    CloudAuthStatus,
    CloudProviderKind,
    InstallationProgress,
    InstallationRequest,
    InstallationResult,
    InstallationStage,
    LocalModelFileDescriptor,
    ModelActivationRequest,
    ModelActivationResult,
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelFileFormat,
    ModelGenerateRequest,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSelectionRequest,
    ModelSelectionResult,
    ModelSelectionStatus,
    ModelSessionStatus,
    ModelSourceType,
    ModelStatus,
    ModelSwitchPolicy,
    ModelSwitchResult,
    ProviderHealth,
    ProviderHealthStatus,
)
from orbit.runtime.models.registry import ModelRegistry

__all__ = [
    # Models & Enums
    "ModelProviderKind",
    "ModelSourceType",
    "CloudProviderKind",
    "CloudAuthStatus",
    "ModelFileFormat",
    "ModelStatus",
    "ModelCapability",
    "ProviderHealthStatus",
    "ProviderHealth",
    "ModelDescriptor",
    "LocalModelFileDescriptor",
    "InstallationStage",
    "InstallationRequest",
    "InstallationProgress",
    "InstallationResult",
    "ModelGenerateRequest",
    "ModelChatMessage",
    "ModelChatRequest",
    "ModelGenerateResponse",
    # M1.9 Step 3 Models & Session
    "ModelSelectionStatus",
    "ModelSelectionRequest",
    "ModelSelectionResult",
    "ModelActivationRequest",
    "ModelActivationResult",
    "ModelSwitchPolicy",
    "ModelSwitchResult",
    "ModelSessionStatus",
    "ActiveModelSession",
    # Runtime Adapters
    "ModelRuntimeAdapter",
    "LocalRuntimeAdapter",
    "CloudRuntimeAdapter",
    "OpenAICompatibleAdapter",
    "AdapterCapabilityStatus",
    "create_runtime_adapter",
    # Capabilities
    "infer_capabilities",
    "matches_capabilities",
    # Health
    "HealthEvaluator",
    "measure_roundtrip_latency",
    # Discovery
    "ModelDiscoveryEngine",
    "DiscoveryResult",
    "ProviderDiscoveryReport",
    # File Scanner
    "LocalFileModelScanner",
    "parse_gguf_header_safe",
    # Lifecycle
    "ModelLifecycleManager",
    "ModelLifecycleTransition",
    "InvalidStateTransitionError",
    # Installer
    "ModelInstaller",
    "InstallationProvider",
    "OllamaInstallationProvider",
    "ModelInstallationError",
    # Inventory
    "ModelInventory",
    "InventoryReport",
    "SystemCapabilitiesReport",
    "RuntimeInventorySummary",
    "CloudProviderInventorySummary",
    # Registry
    "ModelRegistry",
    # Manager & Exceptions
    "ModelManager",
    "ModelManagerError",
    "ModelNotFoundError",
    "ModelUnavailableError",
    "ProviderNotFoundError",
    "ProviderUnhealthyError",
    "CloudAuthRequiredError",
    "CapabilityMismatchError",
    "StaleModelGenerationError",
    "NoActiveModelError",
    "ModelSwitchError",
]
