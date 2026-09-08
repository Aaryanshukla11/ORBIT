"""Perception Router with Multi-Tier Query Hierarchy (Milestone M2.0).

Routes perception queries through a hierarchical decision tree:
1. Win32 Native API (0ms latency: window titles, HWNDs, process names, rects)
       ↓ (If unanswered)
2. UI Automation Accessibility Tree (~5ms: named controls, buttons, text fields)
       ↓ (If unanswered)
3. OCR Text Engine (~15ms: text tokens on rendered screen pixels)
       ↓ (If unanswered)
4. Multimodal Vision Model (Deep visual understanding via ModelRouter)

SAFETY INVARIANT:
Physical coordinates (x, y) are resolved exclusively by the grounding layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.agent.contracts import SemanticTarget
from orbit.runtime.model_runtime.router import ModelRouter, RoutingPolicy
from orbit.runtime.models.models import ModelCapability, ModelGenerateRequest
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    ResolvedTarget,
    TargetIntent,
    TargetLocator,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetStrategy,
)

logger = logging.getLogger(__name__)


class PerceptionLayer(str, Enum):
    """Hierarchical perception query layers ordered by increasing latency and generality."""

    WIN32 = "WIN32"                  # Tier 1: Win32 API native queries
    UIA = "UIA"                      # Tier 2: UI Automation accessibility tree
    OCR = "OCR"                      # Tier 3: Optical Character Recognition
    VISION_MODEL = "VISION_MODEL"    # Tier 4: Multimodal Vision Model evaluation


class PerceptionQueryResult(BaseModel):
    """Outcome of a routed perception query."""

    query: str = Field(..., description="Query or semantic target label")
    layer_used: PerceptionLayer = Field(..., description="Perception layer that resolved the query")
    is_resolved: bool = Field(default=False, description="Whether target or question was successfully resolved")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    coordinates: Optional[Tuple[int, int]] = Field(default=None, description="Resolved physical (x, y) screen center point")
    resolved_target: Optional[ResolvedTarget] = Field(default=None, description="Detailed resolved UI target structure")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Supporting evidence data")
    diagnostic_message: str = Field(default="", description="Diagnostic status message")
    duration_ms: float = Field(default=0.0, description="Elapsed query time in milliseconds")


class PerceptionRouter:
    """Intelligent Router directing perception questions through the 4-tier perception hierarchy."""

    def __init__(
        self,
        target_locator: Optional[TargetLocator] = None,
        model_router: Optional[ModelRouter] = None,
    ) -> None:
        self._target_locator = target_locator or EvidenceBasedTargetLocator()
        self._model_router = model_router

    def set_model_router(self, router: ModelRouter) -> None:
        """Attach or update the ModelRouter for Tier 4 Vision Model queries."""
        self._model_router = router

    async def query_target(
        self,
        target: SemanticTarget,
        observation: Optional[ObservationSnapshot] = None,
    ) -> PerceptionQueryResult:
        """Resolve a SemanticTarget by walking down the 4-tier perception hierarchy."""
        t_start = time.perf_counter()
        target_name = target.name or ""
        target_role = target.role or ""

        # -------------------------------------------------------------
        # Tier 1: Win32 Native API Query (Window title, class, HWND)
        # -------------------------------------------------------------
        if target_role.lower() in ("window", "app", "application") or "window" in (target.context or "").lower():
            win32_res = await self._query_win32_window(target_name)
            if win32_res.is_resolved:
                win32_res.duration_ms = (time.perf_counter() - t_start) * 1000.0
                return win32_res

        # -------------------------------------------------------------
        # Tier 2: UI Automation Query (Named controls, buttons, menus)
        # -------------------------------------------------------------
        uia_res = await self._query_uia_element(target, observation)
        if uia_res.is_resolved:
            uia_res.duration_ms = (time.perf_counter() - t_start) * 1000.0
            return uia_res

        # -------------------------------------------------------------
        # Tier 3: OCR Engine Query (Screen text tokens)
        # -------------------------------------------------------------
        if target_name:
            ocr_res = await self._query_ocr_text(target_name, observation)
            if ocr_res.is_resolved:
                ocr_res.duration_ms = (time.perf_counter() - t_start) * 1000.0
                return ocr_res

        # -------------------------------------------------------------
        # Tier 4: Multimodal Vision Model Query (Visual reasoning)
        # -------------------------------------------------------------
        if self._model_router is not None:
            vision_res = await self._query_vision_model(target, observation)
            if vision_res.is_resolved:
                vision_res.duration_ms = (time.perf_counter() - t_start) * 1000.0
                return vision_res

        # Unresolved through all 4 tiers
        return PerceptionQueryResult(
            query=target_name or str(target),
            layer_used=PerceptionLayer.VISION_MODEL if self._model_router else PerceptionLayer.OCR,
            is_resolved=False,
            confidence=0.0,
            diagnostic_message=f"Target '{target_name}' could not be resolved across perception hierarchy",
            duration_ms=(time.perf_counter() - t_start) * 1000.0,
        )

    async def _query_win32_window(self, target_name: str) -> PerceptionQueryResult:
        """Tier 1: Query Win32 top-level window list and active foreground window."""
        t_start = time.perf_counter()
        if not target_name:
            return PerceptionQueryResult(
                query="",
                layer_used=PerceptionLayer.WIN32,
                is_resolved=False,
                diagnostic_message="Empty target name for Win32 query",
            )

        target_norm = target_name.lower().strip()
        matched_hwnd = None
        matched_title = None

        if sys.platform == "win32":
            try:
                import ctypes
                import ctypes.wintypes
                from orbit.adapters.pointer.safety import attached_to_input_desktop

                windows: List[Tuple[int, str]] = []

                def _enum_cb(hwnd: int, extra: Any) -> bool:
                    user32 = ctypes.windll.user32
                    if user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
                        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
                            windows.append((hwnd, buf.value))
                    return True

                with attached_to_input_desktop():
                    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_enum_cb)
                    ctypes.windll.user32.EnumWindows(enum_proc, 0)

                for hwnd, title in windows:
                    if target_norm in title.lower():
                        matched_hwnd = hwnd
                        matched_title = title
                        break

            except Exception as ex:
                logger.debug("Win32 window enumeration notice: %s", ex)

        if matched_hwnd is not None:
            return PerceptionQueryResult(
                query=target_name,
                layer_used=PerceptionLayer.WIN32,
                is_resolved=True,
                confidence=0.98,
                evidence={"hwnd": matched_hwnd, "title": matched_title},
                diagnostic_message=f"Resolved via Win32: HWND {matched_hwnd} ('{matched_title}')",
                duration_ms=(time.perf_counter() - t_start) * 1000.0,
            )

        return PerceptionQueryResult(
            query=target_name,
            layer_used=PerceptionLayer.WIN32,
            is_resolved=False,
            confidence=0.0,
            diagnostic_message=f"No matching Win32 window found for '{target_name}'",
        )

    async def _query_uia_element(
        self,
        target: SemanticTarget,
        observation: Optional[ObservationSnapshot] = None,
    ) -> PerceptionQueryResult:
        """Tier 2: Query UI Automation accessibility tree via EvidenceBasedTargetLocator."""
        t_start = time.perf_counter()
        target_intent = TargetIntent(
            name=target.name,
            role=target.role,
            strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        )
        try:
            res: TargetResolutionResult = await self._target_locator.locate_target(target_intent, observation)
            is_resolved = (
                res.status == TargetResolutionStatus.RESOLVED
                if hasattr(res, "status")
                else getattr(res, "is_resolved", False)
            )
            resolved_tgt = getattr(res, "target", None) or getattr(res, "resolved_target", None)
            if res and is_resolved and resolved_tgt:
                coords = (int(resolved_tgt.safe_point.x), int(resolved_tgt.safe_point.y))
                return PerceptionQueryResult(
                    query=target.name or "",
                    layer_used=PerceptionLayer.UIA,
                    is_resolved=True,
                    confidence=resolved_tgt.confidence,
                    coordinates=coords,
                    resolved_target=resolved_tgt,
                    evidence=resolved_tgt.evidence.model_dump() if hasattr(resolved_tgt.evidence, "model_dump") else {},
                    diagnostic_message=f"Resolved via UI Automation at ({coords[0]}, {coords[1]})",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )
        except Exception as ex:
            logger.debug("UIA element query notice: %s", ex)

        return PerceptionQueryResult(
            query=target.name or "",
            layer_used=PerceptionLayer.UIA,
            is_resolved=False,
            confidence=0.0,
            diagnostic_message="Element not found via UI Automation",
        )

    async def _query_ocr_text(
        self,
        target_text: str,
        observation: Optional[ObservationSnapshot] = None,
    ) -> PerceptionQueryResult:
        """Tier 3: Query OCR text tokens via TargetStrategy.OCR_TEXT."""
        t_start = time.perf_counter()
        target_intent = TargetIntent(
            text=target_text,
            strategy=TargetStrategy.OCR_TEXT,
        )
        try:
            res: TargetResolutionResult = await self._target_locator.locate_target(target_intent, observation)
            is_resolved = (
                res.status == TargetResolutionStatus.RESOLVED
                if hasattr(res, "status")
                else getattr(res, "is_resolved", False)
            )
            resolved_tgt = getattr(res, "target", None) or getattr(res, "resolved_target", None)
            if res and is_resolved and resolved_tgt:
                coords = (int(resolved_tgt.safe_point.x), int(resolved_tgt.safe_point.y))
                return PerceptionQueryResult(
                    query=target_text,
                    layer_used=PerceptionLayer.OCR,
                    is_resolved=True,
                    confidence=resolved_tgt.confidence,
                    coordinates=coords,
                    resolved_target=resolved_tgt,
                    evidence=resolved_tgt.evidence.model_dump() if hasattr(resolved_tgt.evidence, "model_dump") else {},
                    diagnostic_message=f"Resolved via OCR at ({coords[0]}, {coords[1]})",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )
        except Exception as ex:
            logger.debug("OCR text query notice: %s", ex)

        return PerceptionQueryResult(
            query=target_text,
            layer_used=PerceptionLayer.OCR,
            is_resolved=False,
            confidence=0.0,
            diagnostic_message="Text not found via OCR",
        )

    async def _query_vision_model(
        self,
        target: SemanticTarget,
        observation: Optional[ObservationSnapshot] = None,
    ) -> PerceptionQueryResult:
        """Tier 4: Query Multimodal Vision Model via ModelRouter."""
        t_start = time.perf_counter()
        if self._model_router is None:
            return PerceptionQueryResult(
                query=target.name or "",
                layer_used=PerceptionLayer.VISION_MODEL,
                is_resolved=False,
                diagnostic_message="ModelRouter not attached",
            )

        try:
            policy = RoutingPolicy(required_capabilities={ModelCapability.VISION})
            req = ModelGenerateRequest(
                prompt=f"Identify the screen presence and location of target: {target.model_dump_json()}",
                system_prompt="You are ORBIT Vision Perception Engine. Identify UI elements on screen.",
            )
            resp = await self._model_router.generate(req, policy=policy)
            if resp and resp.content:
                return PerceptionQueryResult(
                    query=target.name or "",
                    layer_used=PerceptionLayer.VISION_MODEL,
                    is_resolved=True,
                    confidence=0.85,
                    evidence={"response": resp.content},
                    diagnostic_message="Evaluated via Multimodal Vision Model",
                    duration_ms=(time.perf_counter() - t_start) * 1000.0,
                )
        except Exception as ex:
            logger.debug("Vision model query notice: %s", ex)

        return PerceptionQueryResult(
            query=target.name or "",
            layer_used=PerceptionLayer.VISION_MODEL,
            is_resolved=False,
            confidence=0.0,
            diagnostic_message="Vision model query failed or target not visible",
        )
