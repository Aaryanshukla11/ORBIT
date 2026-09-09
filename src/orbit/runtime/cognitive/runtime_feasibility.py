"""Runtime Feasibility Evaluator.

Evaluates whether a sub-objective is executable RIGHT NOW in the live environment.
Strictly distinguishes primitive expressibility from dynamic runtime feasibility:
- Application / process availability
- Desktop lock / screensaver state
- Network requirement and connectivity
- Filesystem write permissions
- Login / Authentication / CAPTCHA blocks
- Tool & EnvironmentProvider operational readiness (Guardrail 10)
"""

from __future__ import annotations

import logging
import os
import re
import socket
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractActionType,
    TIER3_ENVIRONMENT_INTERFACES,
)
from orbit.runtime.cognitive.models import CurrentStateObservation, SubObjective
from orbit.runtime.environment.registry import EnvironmentProviderRegistry
from orbit.runtime.world_model.model import AgentWorldModel

logger = logging.getLogger(__name__)


class RuntimeFeasibilityResult(BaseModel):
    """Result of dynamic environment feasibility evaluation."""

    is_feasible: bool
    blocking_reason: Optional[str] = None
    missing_resources: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommended_precheck: Optional[str] = None


class RuntimeFeasibilityEvaluator:
    """Evaluates live environment executability for a SubObjective."""

    def __init__(self, check_network: bool = True) -> None:
        self._check_network = check_network

    async def evaluate(
        self,
        sub_objective: SubObjective,
        world_model: AgentWorldModel,
        observation: Optional[CurrentStateObservation] = None,
        provider_registry: Optional[EnvironmentProviderRegistry] = None,
    ) -> RuntimeFeasibilityResult:
        """Evaluate whether sub_objective can execute right now."""
        text_corpus = f"{sub_objective.title} {sub_objective.description}".lower()

        # 1. SCREEN ACCESSIBILITY CHECK
        if world_model.is_desktop_locked:
            return RuntimeFeasibilityResult(
                is_feasible=False,
                blocking_reason="Desktop is locked or screensaver is active.",
                missing_resources=["unlocked_desktop"],
            )

        # 2. LOGIN / AUTHENTICATION / CAPTCHA DETECTION
        raw_active_title = world_model.active_window_title or (observation.active_window_title if observation else "") or ""
        active_title = str(raw_active_title).lower()
        ocr_text = " ".join(observation.ocr_tokens if observation else []).lower()

        if any(term in active_title for term in ("login", "sign in", "sign-in", "captcha", "enter credentials")):
            return RuntimeFeasibilityResult(
                is_feasible=False,
                blocking_reason="Authentication or CAPTCHA required — user credentials needed.",
                missing_resources=["user_credentials"],
            )

        captcha_phrases = (
            "enter captcha", "solve captcha", "recaptcha", "verify you are human",
            "security check", "robot check", "complete the captcha"
        )
        if any(phrase in ocr_text for phrase in captcha_phrases) or ("captcha" in active_title):
            return RuntimeFeasibilityResult(
                is_feasible=False,
                blocking_reason="CAPTCHA challenge detected on screen — automated bypass not permitted.",
                missing_resources=["human_verification"],
            )

        # 3. NETWORK REQUIREMENT CHECK
        needs_network = any(
            kw in text_corpus for kw in ("http", "https", "online", "website", "search web", "download")
        )
        if needs_network and self._check_network:
            is_connected = self._ping_connectivity()
            if not is_connected:
                return RuntimeFeasibilityResult(
                    is_feasible=False,
                    blocking_reason="Internet connectivity is unavailable for web-dependent sub-goal.",
                    missing_resources=["internet_connection"],
                )

        # 4. ENVIRONMENT PROVIDER READINESS (Guardrail 10)
        # Check if sub-goal explicitly asks for spreadsheet or browser tool
        if provider_registry is not None:
            if "spreadsheet" in text_corpus or "excel" in text_corpus or "csv" in text_corpus:
                has_provider = await provider_registry.is_primitive_supported(
                    AbstractActionType.SPREADSHEET_WRITE
                ) or await provider_registry.is_primitive_supported(
                    AbstractActionType.SPREADSHEET_READ
                )
                if not has_provider:
                    return RuntimeFeasibilityResult(
                        is_feasible=False,
                        blocking_reason="No operational spreadsheet provider (Excel, LibreOffice, or CSV fallback) is available.",
                        missing_resources=["spreadsheet_provider"],
                    )

                # Semantic compatibility check (Part 7):
                # Provider availability does NOT imply semantic task feasibility.
                # CSV provider availability must NOT imply that operations requiring Excel-specific behavior are feasible.
                excel_specific_terms = ("excel formula", "formula calculation", "macro", "vba", "pivot table", "excel chart", "worksheet formatting", "cell formatting")
                if any(term in text_corpus for term in excel_specific_terms):
                    supports_excel_native = await provider_registry.is_feature_supported(
                        AbstractActionType.SPREADSHEET_WRITE, "formulas"
                    ) or await provider_registry.is_feature_supported(
                        AbstractActionType.SPREADSHEET_WRITE, "excel"
                    )
                    if not supports_excel_native:
                        return RuntimeFeasibilityResult(
                            is_feasible=False,
                            blocking_reason="Sub-objective requires Excel-specific functionality (formulas/macros/formatting), but available spreadsheet provider only supports basic CSV.",
                            missing_resources=["excel_native_provider"],
                        )

            if "browser" in text_corpus or "web" in text_corpus:
                has_browser_provider = await provider_registry.is_primitive_supported(
                    AbstractActionType.BROWSER_NAVIGATE
                )
                if not has_browser_provider:
                    return RuntimeFeasibilityResult(
                        is_feasible=False,
                        blocking_reason="No operational browser provider is available.",
                        missing_resources=["browser_provider"],
                    )

        # 5. FILESYSTEM WRITABILITY CHECK
        file_matches = re.findall(r"[\"']([A-Za-z]:\\[^\"']+|\/[^\"']+)[\"']", text_corpus)
        for target_path in file_matches:
            parent = os.path.dirname(os.path.abspath(target_path)) or "."
            if os.path.exists(parent) and not os.access(parent, os.W_OK):
                return RuntimeFeasibilityResult(
                    is_feasible=False,
                    blocking_reason=f"Target directory '{parent}' is not writable.",
                    missing_resources=["write_permissions"],
                )

        return RuntimeFeasibilityResult(is_feasible=True)

    def _ping_connectivity(self, host: str = "8.8.8.8", port: int = 53, timeout: float = 1.5) -> bool:
        """Lightweight socket check for internet reachability."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False
