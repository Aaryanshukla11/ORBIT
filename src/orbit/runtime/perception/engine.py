"""Semantic perception engine orchestrating OCR extraction and visual template perception."""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

from orbit.adapters.observation.snapshot import FreshnessState, ObservationSnapshot
from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
from orbit.runtime.perception.fusion_models import (
    FusionPolicy,
    MultiModalFusionResult,
    PerceptionEvidence,
)
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRWord,
)
from orbit.runtime.perception.normalization import matches_text, normalize_text
from orbit.runtime.perception.ocr import OCRProvider, WindowsNativeOCRProvider
from orbit.runtime.perception.visual_engine import VisualPerceptionEngine
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchResult,
    VisualTemplate,
)

logger = logging.getLogger(__name__)


class SemanticPerceptionEngine:
    """High-level semantic perception coordinator.

    Responsibilities:
    1. Orchestrate OCR extraction over observation snapshots and images.
    2. Manage visual template matching and template registry via VisualPerceptionEngine.
    3. Coordinate multi-modal perception fusion via MultiModalPerceptionFusionEngine.
    4. Enforce freshness and desktop generation invariants across all perception channels.
    5. Provide deterministic text and visual element search over observation evidence.
    """

    def __init__(
        self,
        ocr_provider: Optional[OCRProvider] = None,
        visual_engine: Optional[VisualPerceptionEngine] = None,
        fusion_engine: Optional[MultiModalPerceptionFusionEngine] = None,
    ) -> None:
        if ocr_provider is not None:
            self._ocr_provider = ocr_provider
        else:
            self._ocr_provider = WindowsNativeOCRProvider()

        self._visual_engine = visual_engine or VisualPerceptionEngine()
        self._fusion_engine = fusion_engine or MultiModalPerceptionFusionEngine()

    @property
    def ocr_provider(self) -> OCRProvider:
        return self._ocr_provider

    @property
    def visual_engine(self) -> VisualPerceptionEngine:
        return self._visual_engine

    @property
    def fusion_engine(self) -> MultiModalPerceptionFusionEngine:
        return self._fusion_engine

    def set_ocr_provider(self, provider: OCRProvider) -> None:
        """Swap OCR provider (e.g. for testing or fallback)."""
        self._ocr_provider = provider

    def set_visual_engine(self, visual_engine: VisualPerceptionEngine) -> None:
        """Swap VisualPerceptionEngine (e.g. for testing)."""
        self._visual_engine = visual_engine

    async def extract_text_from_image(
        self,
        image: Image.Image,
        desktop_generation_id: int = 0,
        observation_id: Optional[str] = None,
        region_offset: Optional[Tuple[int, int]] = None,
    ) -> OCRResult:
        """Extract text from a standalone image."""
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

    def extract_text_from_image_sync(
        self,
        image: Image.Image,
        desktop_generation_id: int = 0,
        observation_id: Optional[str] = None,
        region_offset: Optional[Tuple[int, int]] = None,
    ) -> OCRResult:
        """Synchronously extract text from a standalone image."""
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

        if hasattr(self._ocr_provider, "extract_text_sync"):
            return self._ocr_provider.extract_text_sync(
                image=image,
                desktop_generation_id=desktop_generation_id,
                observation_id=observation_id,
                region_offset=region_offset,
            )

        import asyncio
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self._ocr_provider.extract_text(
                        image=image,
                        desktop_generation_id=desktop_generation_id,
                        observation_id=observation_id,
                        region_offset=region_offset,
                    ),
                )
                return future.result(timeout=10.0)
        except Exception as ex:
            return OCRResult(
                status=OCRStatus.ERROR,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                error_message=f"Synchronous OCR extraction failed: {ex}",
            )

    def scan_observation_sync(
        self,
        snapshot: ObservationSnapshot,
        image: Optional[Image.Image] = None,
        image_bytes: Optional[bytes] = None,
    ) -> OCRResult:
        """Synchronously extract OCR evidence from an ObservationSnapshot and associated image frame."""
        # 1. Freshness Gate
        if snapshot.is_stale or snapshot.freshness_state == FreshnessState.STALE:
            reason = snapshot.invalidation_reason or "Observation snapshot TTL expired or generation invalid"
            logger.warning("OCR scan rejected: snapshot %s is stale (%s)", snapshot.snapshot_id, reason)
            return OCRResult(
                status=OCRStatus.STALE_OBSERVATION,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message=f"Observation snapshot is stale: {reason}",
            )

        # 2. Resolve image
        img: Optional[Image.Image] = None
        if image is not None:
            img = image
        elif image_bytes is not None:
            try:
                img = Image.open(io.BytesIO(image_bytes))
            except Exception as ex:
                logger.error("Failed to decode image_bytes for snapshot %s: %s", snapshot.snapshot_id, ex)
                return OCRResult(
                    status=OCRStatus.INVALID_INPUT,
                    provider_kind=self._ocr_provider.provider_kind,
                    text_regions=[],
                    full_text="",
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    error_message=f"Failed to decode image bytes: {ex}",
                )
        elif snapshot.telemetry:
            raw_img = snapshot.telemetry.get("screenshot") or snapshot.telemetry.get("image")
            if isinstance(raw_img, Image.Image):
                img = raw_img
            elif isinstance(raw_img, bytes):
                try:
                    img = Image.open(io.BytesIO(raw_img))
                except Exception:
                    img = None

        if img is None:
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
            except Exception as grab_err:
                logger.debug("ImageGrab fallback failed: %s", grab_err)

        if img is None:
            logger.error("Cannot perform OCR scan: no image or image_bytes provided for snapshot %s", snapshot.snapshot_id)
            return OCRResult(
                status=OCRStatus.INVALID_INPUT,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message="No image provided for OCR scan",
            )

        region_offset = (
            (snapshot.desktop_geometry.left, snapshot.desktop_geometry.top)
            if snapshot.desktop_geometry
            else (0, 0)
        )
        return self.extract_text_from_image_sync(
            image=img,
            desktop_generation_id=snapshot.generation_id,
            observation_id=snapshot.snapshot_id,
            region_offset=region_offset,
        )

    async def scan_observation(
        self,
        snapshot: ObservationSnapshot,
        image: Optional[Image.Image] = None,
        image_bytes: Optional[bytes] = None,
    ) -> OCRResult:
        """Extract OCR evidence from an ObservationSnapshot and associated image frame."""
        # 1. Freshness Gate
        if snapshot.is_stale or snapshot.freshness_state == FreshnessState.STALE:
            reason = snapshot.invalidation_reason or "Observation snapshot TTL expired or generation invalid"
            logger.warning("OCR scan rejected: snapshot %s is stale (%s)", snapshot.snapshot_id, reason)
            return OCRResult(
                status=OCRStatus.STALE_OBSERVATION,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message=f"Observation snapshot is stale: {reason}",
            )

        # 2. Resolve image
        img: Optional[Image.Image] = None
        if image is not None:
            img = image
        elif image_bytes is not None:
            try:
                img = Image.open(io.BytesIO(image_bytes))
            except Exception as ex:
                logger.error("Failed to decode image_bytes for snapshot %s: %s", snapshot.snapshot_id, ex)
                return OCRResult(
                    status=OCRStatus.INVALID_INPUT,
                    provider_kind=self._ocr_provider.provider_kind,
                    text_regions=[],
                    full_text="",
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    error_message=f"Failed to decode image bytes: {ex}",
                )

        if img is None:
            logger.error("Cannot perform OCR scan: no image or image_bytes provided for snapshot %s", snapshot.snapshot_id)
            return OCRResult(
                status=OCRStatus.INVALID_INPUT,
                provider_kind=self._ocr_provider.provider_kind,
                text_regions=[],
                full_text="",
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message="No image provided for OCR scan",
            )

        # Calculate virtual desktop region offset if image is smaller than virtual desktop
        region_offset = (snapshot.desktop_geometry.left, snapshot.desktop_geometry.top)

        # 3. Extract text via provider
        return await self._ocr_provider.extract_text(
            image=img,
            desktop_generation_id=snapshot.generation_id,
            observation_id=snapshot.snapshot_id,
            region_offset=region_offset,
        )

    def find_text_regions(
        self,
        ocr_result: OCRResult,
        query_text: str,
        *,
        exact_match: bool = True,
        case_sensitive: bool = False,
        min_confidence: Optional[float] = None,
    ) -> List[OCRTextRegion]:
        """Deterministically search for matching text regions in an OCR scan result."""
        if not ocr_result.is_success or not query_text:
            return []

        matches: List[OCRTextRegion] = []
        norm_query = normalize_text(query_text, case_fold=not case_sensitive)

        for region in ocr_result.text_regions:
            # Check line-level match
            line_matched = matches_text(
                candidate=region.text,
                query=query_text,
                exact_match=exact_match,
                case_sensitive=case_sensitive,
            )

            if line_matched:
                if min_confidence is not None and region.confidence is not None and region.confidence < min_confidence:
                    continue
                matches.append(region)
            else:
                # Check individual constituent words if exact match on line failed
                for word in region.words:
                    word_matched = matches_text(
                        candidate=word.text,
                        query=query_text,
                        exact_match=exact_match,
                        case_sensitive=case_sensitive,
                    )
                    if word_matched:
                        if min_confidence is not None and word.confidence is not None and word.confidence < min_confidence:
                            continue
                        # Create a dedicated OCRTextRegion for the matching word
                        word_region = OCRTextRegion(
                            text=word.text,
                            normalized_text=word.normalized_text,
                            bounding_box=word.bounding_box,
                            words=[word],
                            confidence=word.confidence,
                            source_provider=region.source_provider,
                        )
                        matches.append(word_region)

        return matches

    async def find_visual_template(
        self,
        snapshot: ObservationSnapshot,
        template: VisualTemplate,
        image: Optional[Image.Image] = None,
        policy: Optional[VisualMatchPolicy] = None,
    ) -> VisualMatchResult:
        """Find a visual icon or template in an observation snapshot."""
        return await self._visual_engine.find_template(
            snapshot=snapshot,
            template=template,
            image=image,
            policy=policy,
        )

    async def find_template_near_text(
        self,
        snapshot: ObservationSnapshot,
        template: VisualTemplate,
        text_label: str,
        image: Optional[Image.Image] = None,
        max_distance_px: float = 250.0,
        policy: Optional[VisualMatchPolicy] = None,
    ) -> VisualMatchResult:
        """Disambiguate visual template matches by requiring spatial proximity to a confirmed OCR text label."""
        import math
        from orbit.runtime.perception.visual_models import VisualMatchStatus, VisualMatcherKind

        # 1. Acquire OCR evidence
        ocr_res = await self.scan_observation(snapshot, image=image)
        if not ocr_res.is_success:
            return VisualMatchResult(
                status=VisualMatchStatus.NOT_FOUND,
                matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
                template_id=template.template_id,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message=f"OCR scan failed for label '{text_label}': {ocr_res.error_message}",
            )

        text_matches = self.find_text_regions(ocr_res, text_label, exact_match=False)
        if not text_matches:
            return VisualMatchResult(
                status=VisualMatchStatus.NOT_FOUND,
                matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
                template_id=template.template_id,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message=f"No OCR text regions found matching anchor label '{text_label}'",
            )

        # 2. Acquire Visual Template candidates (allowing multiple candidates without auto-failing on ambiguity)
        match_policy = policy or VisualMatchPolicy()
        raw_visual_res = await self._visual_engine.find_template(
            snapshot=snapshot,
            template=template,
            image=image,
            policy=match_policy,
        )

        candidates = raw_visual_res.matches
        if not candidates and raw_visual_res.best_match:
            candidates = [raw_visual_res.best_match]

        if not candidates:
            return raw_visual_res

        # 3. Compute spatial distances from each visual candidate to the nearest matching text label
        scored_candidates: List[Tuple[float, Any]] = []

        for cand in candidates:
            c_center_x = (cand.bounding_box.left + cand.bounding_box.right) / 2.0
            c_center_y = (cand.bounding_box.top + cand.bounding_box.bottom) / 2.0

            min_dist = float("inf")
            for tm in text_matches:
                t_center_x = (tm.bounding_box.left + tm.bounding_box.right) / 2.0
                t_center_y = (tm.bounding_box.top + tm.bounding_box.bottom) / 2.0
                dist = math.hypot(c_center_x - t_center_x, c_center_y - t_center_y)
                if dist < min_dist:
                    min_dist = dist

            if min_dist <= max_distance_px:
                scored_candidates.append((min_dist, cand))

        if not scored_candidates:
            return VisualMatchResult(
                status=VisualMatchStatus.NOT_FOUND,
                matcher_kind=raw_visual_res.matcher_kind,
                matches=[],
                best_match=None,
                template_id=template.template_id,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                error_message=(
                    f"Found {len(candidates)} visual candidate(s), but none were within "
                    f"{max_distance_px}px of anchor text '{text_label}'"
                ),
            )

        # Sort by distance (closest first)
        scored_candidates.sort(key=lambda item: item[0])

        # If exactly 1 candidate is within proximity, or the closest is significantly closer
        best_cand = scored_candidates[0][1]
        if len(scored_candidates) > 1:
            second_dist = scored_candidates[1][0]
            first_dist = scored_candidates[0][0]
            # If two visual candidates are equidistant to the text anchor (< 20px delta), flag as ambiguous
            if abs(second_dist - first_dist) < 20.0:
                return VisualMatchResult(
                    status=VisualMatchStatus.AMBIGUOUS,
                    matcher_kind=raw_visual_res.matcher_kind,
                    matches=[item[1] for item in scored_candidates],
                    best_match=None,
                    template_id=template.template_id,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=snapshot.generation_id,
                    error_message=f"Multiple visual icons equidistant to text anchor '{text_label}'",
                )

        return VisualMatchResult(
            status=VisualMatchStatus.MATCHED,
            matcher_kind=raw_visual_res.matcher_kind,
            matches=[item[1] for item in scored_candidates],
            best_match=best_cand,
            template_id=template.template_id,
            observation_id=snapshot.snapshot_id,
            desktop_generation_id=snapshot.generation_id,
        )

    def fuse_multimodal_observation(
        self,
        snapshot: ObservationSnapshot,
        intent: Any,
        ocr_result: Optional[OCRResult] = None,
        visual_result: Optional[VisualMatchResult] = None,
        policy: Optional[FusionPolicy] = None,
    ) -> MultiModalFusionResult:
        """Execute multi-modal perception fusion across all evidence channels for an observation snapshot."""
        return self._fusion_engine.fuse_multimodal_intent(
            snapshot=snapshot,
            intent=intent,
            ocr_result=ocr_result,
            visual_result=visual_result,
            policy=policy,
        )


