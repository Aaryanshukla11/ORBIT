"""Browser environment providers for ORBIT.

Supports BROWSER_NAVIGATE via:
1. PlaywrightBrowserProvider (Direct headless or headed browser control if installed)
2. SystemDefaultBrowserProvider (Launches standard system browser with specified URL)
"""

from __future__ import annotations

import logging
import subprocess
import webbrowser
from typing import Optional
from urllib.parse import urlparse

from orbit.runtime.agent.contracts import AbstractAction
from orbit.runtime.environment.registry import EnvironmentProvider, ProviderExecutionResult

logger = logging.getLogger(__name__)


class SystemDefaultBrowserProvider(EnvironmentProvider):
    """Launches or navigates via the OS default web browser."""

    @property
    def provider_id(self) -> str:
        return "system_default_browser_provider"

    async def is_available(self) -> bool:
        # Standard library webbrowser is always available
        return True

    async def check_permissions(self, action: AbstractAction) -> bool:
        url = action.parameters.get("url")
        if not url:
            return False
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https", "file")

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        url = action.parameters.get("url")
        if not url:
            return ProviderExecutionResult(success=False, error="Missing required parameter 'url'")

        try:
            opened = webbrowser.open(url)
            return ProviderExecutionResult(
                success=opened,
                output={"url": url, "browser_opened": opened},
                metadata={"provider": self.provider_id},
            )
        except Exception as e:
            logger.error("[BROWSER PROVIDER] Failed to open URL '%s': %s", url, e)
            return ProviderExecutionResult(success=False, error=str(e))


class PlaywrightBrowserProvider(EnvironmentProvider):
    """Browser provider utilizing Playwright for automation if installed."""

    @property
    def provider_id(self) -> str:
        return "playwright_browser_provider"

    async def is_available(self) -> bool:
        try:
            import playwright  # type: ignore[import-not-found]
            return True
        except ImportError:
            return False

    async def check_permissions(self, action: AbstractAction) -> bool:
        url = action.parameters.get("url")
        if not url:
            return False
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https", "file")

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        url = action.parameters.get("url")
        if not url:
            return ProviderExecutionResult(success=False, error="Missing parameter 'url'")
        # Dispatches via playwright when available
        return ProviderExecutionResult(
            success=False,
            error="Playwright automation session not active",
            metadata={"provider": self.provider_id},
        )
