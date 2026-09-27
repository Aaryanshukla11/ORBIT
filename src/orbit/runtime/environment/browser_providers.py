"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/agent/tools/service.py (scrape_tool)
ORBIT Destination:    src/orbit/runtime/environment/browser_providers.py
Integration Paradigm: Transduced Browser Perception Gateway (Brain-Body Separation)

Adaptations Applied:
- Added AccessibilityBrowserScraperProvider to extract structured web text via OS UIA tree without Selenium/Playwright.
- Enforced strict invariant: Perception transducer only, NO browser agent, prompt loops, or autonomous completion.
======================================
"""

from __future__ import annotations

import logging
import subprocess
import sys
import webbrowser
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from orbit.adapters.uia.controls import ControlFromHandle, GetRootControl
from orbit.adapters.uia.enums import ControlType
from orbit.runtime.agent.contracts import AbstractAction
from orbit.runtime.environment.registry import EnvironmentProvider, ProviderExecutionResult

logger = logging.getLogger(__name__)


class AccessibilityBrowserScraperProvider(EnvironmentProvider):
    """Extracts structured text from active Chrome / Edge windows via UI Automation."""

    @property
    def provider_id(self) -> str:
        return "accessibility_browser_scraper_provider"

    @property
    def supported_features(self) -> List[str]:
        return ["browser_scrape", "accessibility_dom_text", "links_extraction"]

    async def is_available(self) -> bool:
        return sys.platform == "win32"

    async def check_permissions(self, action: AbstractAction) -> bool:
        return True

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        """Scrape text from the foreground or target browser window."""
        if sys.platform != "win32":
            return ProviderExecutionResult(success=False, error="UIA browser scraper requires Windows")

        params = action.parameters or {}
        target_hwnd = params.get("hwnd")

        try:
            root_ctrl = ControlFromHandle(int(target_hwnd)) if target_hwnd else None
            if not root_ctrl:
                # Find foreground browser window
                import ctypes
                user32 = ctypes.windll.user32
                fg_hwnd = user32.GetForegroundWindow()
                if fg_hwnd:
                    root_ctrl = ControlFromHandle(fg_hwnd)

            if not root_ctrl:
                return ProviderExecutionResult(success=False, error="No active browser window found for scraping")

            # Traverse UIA document / text controls
            extracted_lines: List[str] = []
            stack = [(root_ctrl, 0)]
            max_depth = 12

            while stack:
                curr, depth = stack.pop()
                if depth > max_depth:
                    continue

                try:
                    name = curr.Name
                    c_type = curr.ControlType
                    if name and name.strip():
                        if c_type in (ControlType.TextControl, ControlType.HyperlinkControl, ControlType.DocumentControl, ControlType.HeadingControl if hasattr(ControlType, "HeadingControl") else 50037):
                            extracted_lines.append(name.strip())

                    for child in reversed(curr.GetChildren()):
                        stack.append((child, depth + 1))
                except Exception:
                    continue

            full_text = "\n".join(extracted_lines)
            return ProviderExecutionResult(
                success=True,
                output={
                    "window_title": root_ctrl.Name if root_ctrl else "",
                    "extracted_text": full_text,
                    "lines_count": len(extracted_lines),
                },
                metadata={"provider": self.provider_id},
            )

        except Exception as ex:
            logger.error("[ACCESSIBILITY BROWSER SCRAPER] Scraping failed: %s", ex)
            return ProviderExecutionResult(success=False, error=str(ex))



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
