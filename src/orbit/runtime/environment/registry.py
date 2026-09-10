"""Environment Provider Registry and Base Contracts.

Ensures that environment interfaces (SPREADSHEET_WRITE, BROWSER_NAVIGATE, FILE_READ, FILE_WRITE)
are backed by dynamic, verified provider adapters rather than being assumed automatically available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType

logger = logging.getLogger(__name__)


class ProviderExecutionResult(BaseModel):
    """Result of executing an environment primitive via an EnvironmentProvider."""

    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EnvironmentProvider(ABC):
    """Abstract interface for providers implementing environment actions."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'csv_fallback', 'excel_com')."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider's required dependencies and runtime are available."""
        ...

    @abstractmethod
    async def check_permissions(self, action: AbstractAction) -> bool:
        """Check if permissions exist to execute this specific action."""
        ...

    @property
    def supported_features(self) -> List[str]:
        """List of semantic features supported by this provider (e.g. 'csv', 'formulas', 'excel')."""
        return []

    def supports_feature(self, feature: str) -> bool:
        """Check if provider supports a specific semantic capability."""
        return feature.lower() in [f.lower() for f in self.supported_features]

    @abstractmethod
    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        """Execute the action through this provider."""
        ...


class EnvironmentProviderRegistry:
    """Registry maintaining available providers for environment primitives.

    Allows dynamic selection and fallback (e.g. Excel -> LibreOffice -> CSV fallback).
    """

    def __init__(self) -> None:
        # Map of action_type -> list of (priority, provider)
        # Lower priority number = higher priority
        self._providers: Dict[AbstractActionType, List[Tuple[int, EnvironmentProvider]]] = {}

    def register(
        self,
        primitive: AbstractActionType,
        provider: EnvironmentProvider,
        priority: int = 100,
    ) -> None:
        """Register a provider for a specific primitive."""
        if primitive not in self._providers:
            self._providers[primitive] = []
        self._providers[primitive].append((priority, provider))
        self._providers[primitive].sort(key=lambda x: x[0])
        logger.debug(
            "[PROVIDER REGISTRY] Registered '%s' for primitive %s (priority=%d)",
            provider.provider_id, primitive.value, priority
        )

    async def resolve_provider(
        self,
        primitive: AbstractActionType,
        action: Optional[AbstractAction] = None,
    ) -> Optional[EnvironmentProvider]:
        """Resolve the highest-priority available and permitted provider for a primitive."""
        candidates = self._providers.get(primitive, [])
        for _, provider in candidates:
            try:
                available = await provider.is_available()
                if not available:
                    continue
                if action is not None:
                    permitted = await provider.check_permissions(action)
                    if not permitted:
                        continue
                return provider
            except Exception as e:
                logger.warning(
                    "[PROVIDER REGISTRY] Error evaluating provider '%s': %s",
                    provider.provider_id, e
                )
        return None

    async def is_primitive_supported(self, primitive: AbstractActionType) -> bool:
        """Check if at least one operational provider is currently available for this primitive."""
        provider = await self.resolve_provider(primitive)
        return provider is not None

    def get_all_registered_providers(
        self,
        primitive: AbstractActionType,
    ) -> List[EnvironmentProvider]:
        """Return all registered providers for this primitive regardless of current runtime availability."""
        return [provider for _, provider in self._providers.get(primitive, [])]

    async def get_providers_for_primitive(
        self,
        primitive: AbstractActionType,
    ) -> List[EnvironmentProvider]:
        """Return all operational providers registered for this primitive."""
        available_providers: List[EnvironmentProvider] = []
        for _prio, provider in self._providers.get(primitive, []):
            try:
                if await provider.is_available():
                    available_providers.append(provider)
            except Exception:
                continue
        return available_providers

    async def is_feature_supported(
        self,
        primitive: AbstractActionType,
        feature_name: str,
    ) -> bool:
        """Check if any operational provider for this primitive supports the requested semantic feature."""
        providers = await self.get_providers_for_primitive(primitive)
        return any(p.supports_feature(feature_name) for p in providers)

    async def get_availability_map(self) -> Dict[str, str]:
        """Return a mapping of primitive_name -> active_provider_id for all available primitives."""
        res: Dict[str, str] = {}
        for prim in self._providers.keys():
            provider = await self.resolve_provider(prim)
            if provider is not None:
                res[prim.value] = provider.provider_id
        return res


def get_default_environment_registry() -> EnvironmentProviderRegistry:
    """Create and return an EnvironmentProviderRegistry pre-populated with default providers."""
    from orbit.runtime.environment.spreadsheet_providers import (
        CsvSpreadsheetProvider,
        ExcelComProvider,
        LibreOfficeCalcProvider,
    )
    from orbit.runtime.environment.browser_providers import (
        PlaywrightBrowserProvider,
        SystemDefaultBrowserProvider,
    )
    from orbit.runtime.environment.file_providers import LocalFileProvider
    from orbit.runtime.environment.shell_provider import ShellExecutionProvider
    from orbit.runtime.environment.image_providers import ArtifactImageGenProvider
    from orbit.runtime.environment.drawing_provider import CanvasDrawingProvider

    registry = EnvironmentProviderRegistry()

    # Drawing Provider
    drawing_provider = CanvasDrawingProvider()
    registry.register(AbstractActionType.DRAW_STROKES, drawing_provider, priority=50)

    # Spreadsheet Providers
    csv_provider = CsvSpreadsheetProvider()
    excel_provider = ExcelComProvider()
    libre_provider = LibreOfficeCalcProvider()

    registry.register(AbstractActionType.SPREADSHEET_READ, excel_provider, priority=50)
    registry.register(AbstractActionType.SPREADSHEET_READ, libre_provider, priority=100)
    registry.register(AbstractActionType.SPREADSHEET_READ, csv_provider, priority=200)

    registry.register(AbstractActionType.SPREADSHEET_WRITE, excel_provider, priority=50)
    registry.register(AbstractActionType.SPREADSHEET_WRITE, libre_provider, priority=100)
    registry.register(AbstractActionType.SPREADSHEET_WRITE, csv_provider, priority=200)

    # Browser Providers
    playwright_provider = PlaywrightBrowserProvider()
    default_browser_provider = SystemDefaultBrowserProvider()

    registry.register(AbstractActionType.BROWSER_NAVIGATE, playwright_provider, priority=50)
    registry.register(AbstractActionType.BROWSER_NAVIGATE, default_browser_provider, priority=100)

    # File Providers (Non-physical filesystem interface)
    file_provider = LocalFileProvider()
    registry.register(AbstractActionType.FILE_READ, file_provider, priority=50)
    registry.register(AbstractActionType.FILE_WRITE, file_provider, priority=50)

    # Shell Provider (Hardened non-physical shell, Zero Physical OS Bypass)
    shell_provider = ShellExecutionProvider()
    registry.register(AbstractActionType.SHELL_EXECUTE, shell_provider, priority=50)

    # Image Artifact Provider (Artifact-only, zero physical desktop authority)
    image_provider = ArtifactImageGenProvider()
    registry.register(AbstractActionType.IMAGE_GENERATE, image_provider, priority=50)

    return registry

