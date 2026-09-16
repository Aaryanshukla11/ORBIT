"""Multimodal Desktop Perception Engine (Step 3).

Orchestrates multi-channel desktop perception (Win32, UIA, OCR, Visual), executes
multi-modal evidence fusion into PerceivedElements, and produces concise LLM context summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from PIL import Image

from orbit.adapters.observation.snapshot import FreshnessState, ObservationSnapshot
from orbit.contracts.capabilities import ObservationCapability
from orbit.models.common import BoundingBox
from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
from orbit.runtime.perception.fusion_models import (
    FusionPolicy,
    MultiModalFusionResult,
    PerceptionEvidence as LegacyPerceptionEvidence,
)
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRBoundingBox,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRToken,
    OCRWord,
    PerceivedElement,
    PerceptionEvidence,
    UIElementObservation,
    VisualRegion,
    VisualRegionType,
    WindowObservation,
)
from orbit.runtime.perception.normalization import matches_text, normalize_text
from orbit.runtime.perception.observer import DesktopObserver
from orbit.runtime.perception.ocr import OCRProvider, WindowsNativeOCRProvider
from orbit.runtime.perception.visual_engine import VisualPerceptionEngine
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchResult,
    VisualTemplate,
)

logger = logging.getLogger(__name__)


class DesktopPerceptionEngine:
    """Canonical production multimodal perception and evidence fusion engine."""

    def __init__(
        self,
        desktop_observer: Optional[DesktopObserver] = None,
        ocr_provider: Optional[OCRProvider] = None,
        visual_engine: Optional[VisualPerceptionEngine] = None,
        observation_capability: Optional[ObservationCapability] = None,
    ) -> None:
        self._desktop_observer = desktop_observer or DesktopObserver(observation_capability=observation_capability)
        self._ocr_provider = ocr_provider or WindowsNativeOCRProvider()
        self._visual_engine = visual_engine or VisualPerceptionEngine()
        self._legacy_fusion = MultiModalPerceptionFusionEngine()

    @property
    def observer(self) -> DesktopObserver:
        return self._desktop_observer

    @property
    def ocr_provider(self) -> OCRProvider:
        return self._ocr_provider

    @property
    def visual_engine(self) -> VisualPerceptionEngine:
        return self._visual_engine

    def set_observation_capability(self, cap: ObservationCapability) -> None:
        """Update the underlying observation adapter."""
        self._desktop_observer.set_observation_capability(cap)

    async def observe(
        self,
        target_hwnd: Optional[int] = None,
        include_screenshot_base64: bool = True,
        include_ocr: bool = True,
        include_uia: bool = True,
    ) -> DesktopObservation:
        """Capture fresh desktop state, fuse multi-modal evidence, and summarize for LLM."""
        raw_obs = await self._desktop_observer.observe_desktop(
            include_screenshot_base64=include_screenshot_base64,
            include_ocr=include_ocr,
            include_uia=include_uia,
            target_hwnd=target_hwnd,
        )

        # Execute Multi-Modal Perception Fusion
        fused_elements = self._fuse_evidence(raw_obs)
        raw_obs.perceived_elements = fused_elements

        # Generate Structured LLM Context Summary
        summary = self.summarize_for_llm(raw_obs)
        raw_obs.desktop_summary = summary

        return raw_obs

    def _fuse_evidence(self, obs: DesktopObservation) -> List[PerceivedElement]:
        """Fuse Win32, UIA, OCR, and Visual evidence into PerceivedElements."""
        perceived: List[PerceivedElement] = []
        matched_tok_ids = set()

        # 1. Fuse UIA Elements with overlapping OCR Tokens
        for uia in obs.uia_elements:
            matched_tokens: List[OCRToken] = []
            if uia.bounding_box:
                for tok in obs.ocr_tokens:
                    if tok.token_id not in matched_tok_ids and self._boxes_intersect(uia.bounding_box, tok.bounding_box):
                        matched_tokens.append(tok)
                        matched_tok_ids.add(tok.token_id)

            sources = ["UIA"]
            conf = 0.90
            tok_texts = []
            if matched_tokens:
                sources.append("OCR")
                conf = 0.98
                tok_texts = [t.text for t in matched_tokens]

            name = uia.name or (" ".join(tok_texts) if tok_texts else "Unnamed Control")
            role = self._normalize_role(uia.control_type)

            perceived.append(
                PerceivedElement(
                    element_id=f"pe_{uuid4().hex[:8]}",
                    name=name,
                    role=role,
                    context=uia.parent_context or (obs.foreground_window.title if obs.foreground_window else ""),
                    bounds=uia.bounding_box,
                    evidence=PerceptionEvidence(
                        evidence_sources=sources,
                        confidence=conf,
                        matched_tokens=tok_texts,
                        matched_uia_role=uia.control_type,
                    ),
                    confidence=conf,
                    uia_element=uia,
                    ocr_tokens=matched_tokens,
                )
            )

        # 2. Add Unmatched OCR Tokens as standalone text elements
        for tok in obs.ocr_tokens:
            if tok.token_id not in matched_tok_ids:
                perceived.append(
                    PerceivedElement(
                        element_id=f"pe_ocr_{tok.token_id}",
                        name=tok.text,
                        role="text",
                        context=obs.foreground_window.title if obs.foreground_window else "",
                        bounds=tok.bounding_box,
                        evidence=PerceptionEvidence(
                            evidence_sources=["OCR"],
                            confidence=tok.confidence,
                            matched_tokens=[tok.text],
                        ),
                        confidence=tok.confidence,
                        ocr_tokens=[tok],
                    )
                )

        # 3. Add Visual Regions (e.g. Canvas Surface)
        for vreg in obs.visual_regions:
            perceived.append(
                PerceivedElement(
                    element_id=f"pe_vreg_{vreg.region_id}",
                    name=vreg.description or vreg.region_type.value,
                    role=vreg.region_type.value.lower(),
                    context=obs.foreground_window.title if obs.foreground_window else "",
                    bounds=vreg.bounds,
                    evidence=PerceptionEvidence(
                        evidence_sources=[vreg.source],
                        confidence=vreg.confidence,
                    ),
                    confidence=vreg.confidence,
                    visual_region=vreg,
                )
            )

        return perceived

    def summarize_for_llm(self, obs: DesktopObservation) -> str:
        """Create a token-efficient, structured text summary of live desktop state for LLMs."""
        lines: List[str] = [f"=== LIVE DESKTOP STATE ({obs.screen_width}x{obs.screen_height}) ==="]

        # 1. Active Window
        if obs.foreground_window:
            fg = obs.foreground_window
            lines.append(f"Active Window: '{fg.title}' (Class: {fg.window_class}, HWND: {fg.hwnd})")
        else:
            lines.append("Active Window: None / Desktop")

        # 2. Visible Applications
        vis_apps = []
        for win in obs.visible_windows[:5]:
            if win.title and win.title not in vis_apps:
                vis_apps.append(f"'{win.title}'")
        if vis_apps:
            lines.append(f"Visible Windows: {', '.join(vis_apps)}")

        # 3. Key Perceived Elements (Top 6 interactive controls)
        ctrl_lines = []
        for pe in obs.perceived_elements[:6]:
            if pe.role != "text":
                ctrl_lines.append(f"- {pe.role.title()}: '{pe.name}' (Confidence: {pe.confidence:.2f})")
        if ctrl_lines:
            lines.append("Interactive Elements:")
            lines.extend(ctrl_lines)

        # 4. OCR Keywords (Sample)
        if obs.ocr_tokens:
            sample_words = [t.text for t in obs.ocr_tokens[:12]]
            lines.append(f"OCR Tokens: {' | '.join(sample_words)}")

        # 5. Canvas Status
        if obs.canvas_status and obs.canvas_status != "UNKNOWN":
            lines.append(f"Canvas Status: {obs.canvas_status}")

        if not obs.is_consistent:
            lines.append("WARNING: Potential window shift detected during observation capture.")

        return "\n".join(lines)

    def _boxes_intersect(self, b1: BoundingBox, b2: BoundingBox) -> bool:
        """Check if two bounding boxes geometrically overlap."""
        return not (
            b1.left + b1.width < b2.left
            or b2.left + b2.width < b1.left
            or b1.top + b1.height < b2.top
            or b2.top + b2.height < b1.top
        )

    def _normalize_role(self, ctrl_type: Optional[str]) -> str:
        """Normalize UIA control types into semantic roles."""
        if not ctrl_type:
            return "element"
        ct_low = ctrl_type.lower()
        if "button" in ct_low:
            return "button"
        elif "edit" in ct_low or "text" in ct_low:
            return "text_field"
        elif "menu" in ct_low:
            return "menu_item"
        elif "tab" in ct_low:
            return "tab"
        elif "document" in ct_low:
            return "document"
        elif "pane" in ct_low:
            return "pane"
        return ct_low


# Backward compatibility class preserving legacy methods for tests
class SemanticPerceptionEngine(DesktopPerceptionEngine):
    """Backward-compatible wrapper preserving legacy semantic perception API."""

    def __init__(
        self,
        ocr_provider: Optional[Any] = None,
        visual_engine: Optional[VisualPerceptionEngine] = None,
        fusion_engine: Optional[MultiModalPerceptionFusionEngine] = None,
        desktop_observer: Optional[DesktopObserver] = None,
        observation_capability: Optional[ObservationCapability] = None,
    ) -> None:
        super().__init__(
            desktop_observer=desktop_observer,
            ocr_provider=ocr_provider,
            visual_engine=visual_engine,
            observation_capability=observation_capability,
        )
        if fusion_engine is not None:
            self._legacy_fusion = fusion_engine

    @property
    def ocr_provider(self) -> Any:
        return self._ocr_provider

    @property
    def visual_engine(self) -> VisualPerceptionEngine:
        return self._visual_engine

    async def scan_observation(
        self,
        snapshot: ObservationSnapshot,
        image: Optional[Image.Image] = None,
    ) -> OCRResult:
        """Scan observation snapshot for OCR text."""
        if getattr(snapshot, "is_stale", False) or getattr(snapshot, "freshness_state", None) == FreshnessState.STALE:
            return OCRResult(
                status=OCRStatus.STALE_OBSERVATION,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=getattr(snapshot, "snapshot_id", "unknown"),
                desktop_generation_id=getattr(snapshot, "generation_id", 0),
                error_message="Observation snapshot is stale",
            )

        search_image = image
        if search_image is None:
            raw_img = snapshot.telemetry.get("screenshot") or snapshot.telemetry.get("image")
            if isinstance(raw_img, Image.Image):
                search_image = raw_img
        if search_image is None:
            try:
                search_image = snapshot.to_pil_image()
            except Exception:
                search_image = Image.new("RGB", (100, 100))

        return await self._ocr_provider.extract_text(
            image=search_image,
            desktop_generation_id=getattr(snapshot, "generation_id", 0),
            observation_id=getattr(snapshot, "snapshot_id", "unknown"),
        )

    def scan_observation_sync(
        self,
        snapshot: ObservationSnapshot,
        image: Optional[Image.Image] = None,
    ) -> OCRResult:
        """Synchronously scan observation snapshot for OCR text."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(asyncio.run, self.scan_observation(snapshot, image)).result()
            return loop.run_until_complete(self.scan_observation(snapshot, image))
        except Exception:
            return asyncio.run(self.scan_observation(snapshot, image))

    def find_text_regions(
        self,
        ocr_result: OCRResult,
        query_text: str,
        exact_match: bool = False,
        case_sensitive: bool = False,
        min_confidence: Optional[float] = 0.0,
    ) -> List[OCRTextRegion]:
        """Search matching text regions from an OCRResult."""
        if not ocr_result or not ocr_result.text_regions:
            return []
        min_conf = float(min_confidence) if min_confidence is not None else 0.0
        matches: List[OCRTextRegion] = []
        for reg in ocr_result.text_regions:
            reg_conf = float(reg.confidence) if reg.confidence is not None else 1.0
            if reg_conf >= min_conf and matches_text(reg.text, query_text, exact_match=exact_match, case_sensitive=case_sensitive):
                matches.append(reg)
                continue
            if reg.words:
                for w in reg.words:
                    w_conf = float(w.confidence) if w.confidence is not None else 1.0
                    if w_conf >= min_conf and matches_text(w.text, query_text, exact_match=exact_match, case_sensitive=case_sensitive):
                        word_reg = OCRTextRegion(
                            text=w.text,
                            normalized_text=w.normalized_text,
                            bounding_box=w.bounding_box,
                            words=[w],
                            confidence=w.confidence,
                            source_provider=reg.source_provider,
                        )
                        matches.append(word_reg)
                        break
        return matches

    async def find_template_near_text(
        self,
        snapshot: ObservationSnapshot,
        template: VisualTemplate,
        text_label: str,
        image: Optional[Image.Image] = None,
        max_distance_px: float = 100.0,
        policy: Optional[VisualMatchPolicy] = None,
    ) -> VisualMatchResult:
        """Disambiguate visual template match by anchoring near an OCR text label."""
        vis_res = await self._visual_engine.find_template(snapshot, template, image=image, policy=policy)
        if not vis_res.matches:
            return vis_res

        ocr_res = await self.scan_observation(snapshot, image=image)
        if not ocr_res.is_success or not ocr_res.text_regions:
            return vis_res

        text_regions = self.find_text_regions(ocr_res, text_label, exact_match=False, case_sensitive=False)
        if not text_regions:
            return vis_res

        anchor_box = text_regions[0].bounding_box
        anchor_center = anchor_box.center

        import math
        valid_matches = []
        for m in vis_res.matches:
            mc = m.bounding_box.center
            dist = math.hypot(mc[0] - anchor_center[0], mc[1] - anchor_center[1])
            if dist <= max_distance_px:
                valid_matches.append((dist, m))

        if not valid_matches:
            from orbit.runtime.perception.visual_models import VisualMatchStatus
            return VisualMatchResult(
                status=VisualMatchStatus.NOT_FOUND,
                matcher_kind=vis_res.matcher_kind,
                template_id=template.template_id,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message=f"No visual template matches found within {max_distance_px}px of '{text_label}'",
            )

        valid_matches.sort(key=lambda x: x[0])
        best_dist, best_match = valid_matches[0]

        from orbit.runtime.perception.visual_models import VisualMatchStatus
        return VisualMatchResult(
            status=VisualMatchStatus.MATCHED,
            matcher_kind=vis_res.matcher_kind,
            matches=[m for _, m in valid_matches],
            best_match=best_match,
            template_id=template.template_id,
            observation_id=snapshot.snapshot_id,
            desktop_generation_id=snapshot.generation_id,
            duration_ms=vis_res.duration_ms,
        )

    def fuse_multimodal_observation(
        self,
        snapshot: ObservationSnapshot,
        intent: Any,
        ocr_result: Optional[OCRResult] = None,
        visual_result: Optional[VisualMatchResult] = None,
        policy: Optional[FusionPolicy] = None,
    ) -> MultiModalFusionResult:
        """Fuse multimodal observation evidence for an intent."""
        return self._legacy_fusion.fuse_multimodal_intent(
            snapshot=snapshot,
            intent=intent,
            ocr_result=ocr_result,
            visual_result=visual_result,
            policy=policy,
        )

    async def extract_text_from_image(
        self,
        image: Image.Image,
        desktop_generation_id: int = 0,
        observation_id: Optional[str] = None,
        region_offset: Optional[Tuple[int, int]] = None,
    ) -> OCRResult:
        if not self._ocr_provider.is_available():
            return OCRResult(
                status=OCRStatus.UNSUPPORTED,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                error_message=f"OCR provider {self._ocr_provider.provider_kind.value} is unavailable",
            )
        return await self._ocr_provider.extract_text(
            image=image,
            desktop_generation_id=desktop_generation_id,
            observation_id=observation_id,
            region_offset=region_offset,
        )

    async def extract_text_from_snapshot(
        self,
        snapshot: ObservationSnapshot,
        region: Optional[BoundingBox] = None,
    ) -> OCRResult:
        if not snapshot.is_usable:
            return OCRResult(
                status=OCRStatus.STALE_OBSERVATION,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.desktop_generation_id,
                error_message="Snapshot is stale or unusable",
            )
        img = snapshot.to_pil_image()
        offset = None
        if region is not None:
            box = (region.left, region.top, region.left + region.width, region.top + region.height)
            img = img.crop(box)
            offset = (region.left, region.top)

        return await self.extract_text_from_image(
            image=img,
            desktop_generation_id=snapshot.desktop_generation_id,
            observation_id=snapshot.snapshot_id,
            region_offset=offset,
        )

    async def locate_text_regions(
        self,
        snapshot: ObservationSnapshot,
        query: str,
        exact_match: bool = False,
        case_sensitive: bool = False,
    ) -> List[OCRTextRegion]:
        ocr_res = await self.extract_text_from_snapshot(snapshot)
        if not ocr_res.is_success:
            return []
        matches: List[OCRTextRegion] = []
        for reg in ocr_res.text_regions:
            if matches_text(reg.text, query, exact_match=exact_match, case_sensitive=case_sensitive):
                matches.append(reg)
        return matches

    async def match_visual_template(
        self,
        snapshot: ObservationSnapshot,
        template: VisualTemplate,
        policy: Optional[VisualMatchPolicy] = None,
    ) -> VisualMatchResult:
        return await self._visual_engine.find_template(snapshot, template, policy=policy)
