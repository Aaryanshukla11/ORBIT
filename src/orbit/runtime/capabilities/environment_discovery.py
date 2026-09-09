"""Dynamic Environment Capability Discovery empirically probing host system resources."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from typing import Any, Dict, List, Optional, Set

from orbit.runtime.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilityLimitation,
    CapabilitySource,
)

logger = logging.getLogger(__name__)


class EnvironmentCapabilityDiscovery:
    """Discovers installed host applications, browsers, and AI model capabilities without hallucination."""

    # Standard Windows binary paths to check for common tools
    COMMON_WINDOWS_APPS: Dict[str, List[str]] = {
        "paint": ["mspaint.exe", r"C:\Windows\System32\mspaint.exe", r"C:\Windows\mspaint.exe"],
        "notepad": ["notepad.exe", r"C:\Windows\System32\notepad.exe", r"C:\Windows\notepad.exe"],
        "calculator": ["calc.exe", r"C:\Windows\System32\calc.exe"],
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "chrome.exe",
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "msedge.exe",
        ],
        "firefox": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "firefox.exe",
        ],
        "gimp": [
            r"C:\Program Files\GIMP 2\bin\gimp-2.10.exe",
            r"C:\Program Files\GIMP 3\bin\gimp-3.0.exe",
        ],
        "blender": [
            r"C:\Program Files\Blender Foundation\Blender\blender.exe",
        ],
        "photoshop": [
            r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
            r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
        ],
    }

    def __init__(self, model_session_manager: Optional[Any] = None) -> None:
        self._model_session_manager = model_session_manager
        self._cache_discovered: Optional[List[Capability]] = None

    def set_model_session_manager(self, msm: Any) -> None:
        self._model_session_manager = msm

    def is_app_installed(self, app_name: str) -> bool:
        """Empirically check if an application binary exists on the host machine."""
        return self.get_app_path(app_name) is not None

    def get_app_path(self, app_name: str) -> Optional[str]:
        """Locate verified absolute executable path for an application without guessing."""
        app_clean = app_name.strip().lower().replace(".exe", "")
        candidates = self.COMMON_WINDOWS_APPS.get(app_clean, [f"{app_clean}.exe"])

        for candidate in candidates:
            # Check direct file existence
            if os.path.isabs(candidate) and os.path.isfile(candidate):
                return candidate
            # Check PATH
            found = shutil.which(candidate)
            if found:
                return found

        return None

    def has_generative_image_model(self) -> bool:
        """Empirically verify if an active generative image model is available."""
        if self._model_session_manager is None:
            return False

        # Check active session context capabilities
        if hasattr(self._model_session_manager, "get_active_context"):
            ctx = self._model_session_manager.get_active_context()
            if ctx is not None:
                caps = getattr(ctx, "capabilities", [])
                if any("image_gen" in str(c).lower() or "image_generation" in str(c).lower() for c in caps):
                    return True

        # Check runtime provider descriptors
        if hasattr(self._model_session_manager, "get_registered_providers"):
            try:
                providers = self._model_session_manager.get_registered_providers()
                for p in providers:
                    if getattr(p, "supports_image_generation", False):
                        return True
            except Exception:
                pass

        return False

    def discover_capabilities(self, force_refresh: bool = False) -> List[Capability]:
        """Empirically discover all operational environment capabilities on this machine."""
        if self._cache_discovered is not None and not force_refresh:
            return self._cache_discovered

        discovered: List[Capability] = []

        # 1. Probe Installed Applications
        for app_key in self.COMMON_WINDOWS_APPS.keys():
            app_path = self.get_app_path(app_key)
            if app_path:
                category = CapabilityCategory.DESKTOP_CONTROL
                if app_key in ("chrome", "edge", "firefox"):
                    category = CapabilityCategory.BROWSER
                elif app_key in ("paint", "gimp", "photoshop", "blender"):
                    category = CapabilityCategory.CREATIVE_VISUAL

                discovered.append(
                    Capability(
                        capability_id=f"ENV_APP_{app_key.upper()}",
                        name=f"Installed {app_key.capitalize()}",
                        description=f"Local application binary verified at '{app_path}'",
                        category=category,
                        source=CapabilitySource.ENVIRONMENT_APP,
                        supported_goal_types=["launch", "open", "interact", app_key],
                        reliability_score=0.98,
                        is_available=True,
                        metadata={"executable_path": app_path, "application_key": app_key},
                    )
                )

        # 2. Probe AI Model Generative Capabilities
        has_img_gen = self.has_generative_image_model()
        if has_img_gen:
            discovered.append(
                Capability(
                    capability_id="ENV_MODEL_IMAGE_GEN",
                    name="Host Generative Image Synthesis",
                    description="Active local/cloud generative AI model capable of rendering portraits and scenes",
                    category=CapabilityCategory.CREATIVE_VISUAL,
                    source=CapabilitySource.ENVIRONMENT_MODEL,
                    supported_goal_types=["draw", "create_image", "generate_visual", "portrait"],
                    supported_subtypes=["portrait", "boy", "girl", "person", "face", "scene"],
                    reliability_score=0.92,
                    is_available=True,
                    metadata={"provider": "active_model_session"},
                )
            )

        self._cache_discovered = discovered
        logger.debug(
            "Discovered %d environment capabilities: %s",
            len(discovered),
            [c.capability_id for c in discovered],
        )
        return discovered
