"""Deterministic visual template matching engine using normalized cross-correlation."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, List, Optional, Protocol, Tuple, runtime_checkable
import numpy as np
from PIL import Image

from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
)
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchRegion,
    VisualMatchResult,
    VisualMatchStatus,
    VisualMatcherKind,
    VisualTemplate,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class VisualMatcher(Protocol):
    """Protocol for visual template and icon matching engines."""

    @property
    def matcher_kind(self) -> VisualMatcherKind:
        ...

    def is_available(self) -> bool:
        ...

    async def match(
        self,
        template: VisualTemplate,
        image: Image.Image,
        policy: Optional[VisualMatchPolicy] = None,
        desktop_generation_id: int = 0,
        observation_id: Optional[str] = None,
    ) -> VisualMatchResult:
        """Find template occurrences within the given screenshot image."""
        ...


class TemplateVisualMatcher:
    """Production visual matcher executing deterministic Normalized Cross-Correlation (NCC)."""

    def __init__(self) -> None:
        self._kind = VisualMatcherKind.TEMPLATE_NCC

    @property
    def matcher_kind(self) -> VisualMatcherKind:
        return self._kind

    def is_available(self) -> bool:
        return True

    async def match(
        self,
        template: VisualTemplate,
        image: Image.Image,
        policy: Optional[VisualMatchPolicy] = None,
        desktop_generation_id: int = 0,
        observation_id: Optional[str] = None,
    ) -> VisualMatchResult:
        """Match template against image in a background thread pool."""
        match_policy = policy or VisualMatchPolicy()
        t0 = time.perf_counter()

        # 1. Validation Gate
        if not template.is_valid:
            return VisualMatchResult(
                status=VisualMatchStatus.INVALID_TEMPLATE,
                matcher_kind=self._kind,
                template_id=template.template_id,
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                error_message="Template is invalid or has empty dimensions",
            )

        if image is None:
            return VisualMatchResult(
                status=VisualMatchStatus.ERROR,
                matcher_kind=self._kind,
                template_id=template.template_id,
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                error_message="Target search image is None",
            )

        # 2. Run matching algorithm in worker thread to prevent event loop stalls
        result = await asyncio.to_thread(
            self._execute_matching,
            template=template,
            image=image,
            policy=match_policy,
            desktop_generation_id=desktop_generation_id,
            observation_id=observation_id,
        )
        return result

    def _execute_matching(
        self,
        template: VisualTemplate,
        image: Image.Image,
        policy: VisualMatchPolicy,
        desktop_generation_id: int,
        observation_id: Optional[str],
    ) -> VisualMatchResult:
        t0 = time.perf_counter()
        img_w, img_h = image.size

        # Convert search image to grayscale float32 array
        img_gray = image.convert("L")
        img_arr = np.asarray(img_gray, dtype=np.float32)

        candidates: List[VisualMatchRegion] = []
        scale_factors = policy.scale_factors if policy.allow_multi_scale else [1.0]

        template_img = template.image.convert("L") if isinstance(template.image, Image.Image) else Image.fromarray(template.image).convert("L")

        for scale in scale_factors:
            tw = int(round(template.width * scale))
            th = int(round(template.height * scale))

            if tw <= 0 or th <= 0 or tw > img_w or th > img_h:
                continue

            # Resize template to scale factor
            if scale == 1.0:
                tpl_resized = template_img
            else:
                tpl_resized = template_img.resize((tw, th), Image.Resampling.BILINEAR)

            tpl_arr = np.asarray(tpl_resized, dtype=np.float32)

            # Compute correlation surface
            peaks = self._compute_ncc_peaks(
                img_arr=img_arr,
                tpl_arr=tpl_arr,
                tw=tw,
                th=th,
                min_score=policy.minimum_confidence,
                max_peaks=policy.max_candidates,
            )

            for score, (px, py) in peaks:
                bbox = OCRBoundingBox(
                    left=px,
                    top=py,
                    right=px + tw,
                    bottom=py + th,
                    coordinate_space=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
                )
                candidates.append(
                    VisualMatchRegion(
                        template_id=template.template_id,
                        template_name=template.name,
                        bounding_box=bbox,
                        confidence=round(float(score), 4),
                        scale_factor=float(scale),
                        source_provider="TEMPLATE_NCC",
                    )
                )

        duration_ms = (time.perf_counter() - t0) * 1000.0

        if not candidates:
            return VisualMatchResult(
                status=VisualMatchStatus.NOT_FOUND,
                matcher_kind=self._kind,
                template_id=template.template_id,
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                duration_ms=duration_ms,
                error_message=f"No visual matches found above confidence threshold {policy.minimum_confidence}",
            )

        # Sort candidates descending by confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        # Apply Non-Maximum Suppression (NMS) to filter spatial overlaps
        nms_candidates = self._non_max_suppression(candidates, iou_threshold=0.3)

        if not nms_candidates:
            return VisualMatchResult(
                status=VisualMatchStatus.NOT_FOUND,
                matcher_kind=self._kind,
                template_id=template.template_id,
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                duration_ms=duration_ms,
            )

        top_match = nms_candidates[0]

        # 3. Check Ambiguity Policy Gate
        if len(nms_candidates) > 1:
            second_match = nms_candidates[1]
            diff = top_match.confidence - second_match.confidence
            if diff < policy.ambiguity_margin:
                logger.warning(
                    "Visual match is ambiguous: top=%0.4f, second=%0.4f (margin=%0.4f < %0.4f)",
                    top_match.confidence,
                    second_match.confidence,
                    diff,
                    policy.ambiguity_margin,
                )
                return VisualMatchResult(
                    status=VisualMatchStatus.AMBIGUOUS,
                    matcher_kind=self._kind,
                    matches=nms_candidates,
                    best_match=None,
                    template_id=template.template_id,
                    observation_id=observation_id,
                    desktop_generation_id=desktop_generation_id,
                    duration_ms=duration_ms,
                    error_message=(
                        f"Ambiguous visual matches: {len(nms_candidates)} candidate regions found "
                        f"with margin delta {diff:.4f} < {policy.ambiguity_margin}"
                    ),
                )

        # Single distinct high-confidence match
        return VisualMatchResult(
            status=VisualMatchStatus.MATCHED,
            matcher_kind=self._kind,
            matches=nms_candidates,
            best_match=top_match,
            template_id=template.template_id,
            observation_id=observation_id,
            desktop_generation_id=desktop_generation_id,
            duration_ms=duration_ms,
        )

    def _compute_ncc_peaks(
        self,
        img_arr: np.ndarray,
        tpl_arr: np.ndarray,
        tw: int,
        th: int,
        min_score: float,
        max_peaks: int,
    ) -> List[Tuple[float, Tuple[int, int]]]:
        """Compute Normalized Cross-Correlation (NCC) using FFT and integral images."""
        ih, iw = img_arr.shape

        if th > ih or tw > iw:
            return []

        # 1. Normalize template: zero-mean and unit norm
        tpl_mean = float(np.mean(tpl_arr))
        tpl_norm = (tpl_arr - tpl_mean).astype(np.float32)
        tpl_std = float(np.linalg.norm(tpl_norm))
        if tpl_std <= 1e-6:
            # Solid color template has zero variance; matching is undefined
            return []

        # 2. Integral images in float64 for exact sliding-window variance without cancellation
        pad_img = np.pad(img_arr.astype(np.float64), ((1, 0), (1, 0)), mode="constant")
        ii = np.cumsum(np.cumsum(pad_img, axis=0), axis=1)
        ii2 = np.cumsum(np.cumsum(pad_img**2, axis=0), axis=1)

        N = th * tw
        s_i = ii[th:, tw:] - ii[:-th, tw:] - ii[th:, :-tw] + ii[:-th, :-tw]
        s_i2 = ii2[th:, tw:] - ii2[:-th, tw:] - ii2[th:, :-tw] + ii2[:-th, :-tw]

        var_i = s_i2 - (s_i**2) / N
        std_i = np.sqrt(np.maximum(0.0, var_i)).astype(np.float32)

        # 3. FFT-based 2D cross correlation
        h_pad = ih + th - 1
        w_pad = iw + tw - 1
        f_img = np.fft.rfft2(img_arr, s=(h_pad, w_pad))
        f_tpl = np.fft.rfft2(tpl_norm[::-1, ::-1], s=(h_pad, w_pad))
        cross_full = np.fft.irfft2(f_img * f_tpl, s=(h_pad, w_pad))
        cross_terms = cross_full[th - 1 : ih, tw - 1 : iw]

        # 4. Normalized cross-correlation map with zero-variance masking
        valid_mask = (std_i > 1e-4) & (tpl_std > 1e-4)
        ncc_map = np.zeros_like(cross_terms, dtype=np.float32)
        ncc_map[valid_mask] = cross_terms[valid_mask] / (std_i[valid_mask] * tpl_std)
        ncc_map = np.clip(ncc_map, -1.0, 1.0)

        # 5. Extract local maximum peaks >= min_score
        padded_ncc = np.pad(ncc_map, 1, mode="constant", constant_values=-1.0)
        is_peak = (
            (ncc_map >= min_score)
            & (ncc_map >= padded_ncc[:-2, 1:-1])
            & (ncc_map >= padded_ncc[2:, 1:-1])
            & (ncc_map >= padded_ncc[1:-1, :-2])
            & (ncc_map >= padded_ncc[1:-1, 2:])
            & (ncc_map >= padded_ncc[:-2, :-2])
            & (ncc_map >= padded_ncc[:-2, 2:])
            & (ncc_map >= padded_ncc[2:, :-2])
            & (ncc_map >= padded_ncc[2:, 2:])
        )
        peak_y, peak_x = np.where(is_peak)

        if len(peak_y) == 0:
            return []

        peaks = []
        for py, px in zip(peak_y, peak_x):
            score = float(ncc_map[py, px])
            peaks.append((score, (int(px), int(py))))

        # Sort descending by score
        peaks.sort(key=lambda p: p[0], reverse=True)
        return peaks[:max_peaks]

    def _non_max_suppression(
        self,
        candidates: List[VisualMatchRegion],
        iou_threshold: float = 0.3,
    ) -> List[VisualMatchRegion]:
        """Filter spatially overlapping bounding boxes keeping highest score."""
        if not candidates:
            return []

        selected: List[VisualMatchRegion] = []
        for cand in candidates:
            box_a = cand.bounding_box
            keep = True
            for sel in selected:
                box_b = sel.bounding_box
                iou = self._compute_iou(box_a, box_b)
                if iou >= iou_threshold:
                    keep = False
                    break
            if keep:
                selected.append(cand)
        return selected

    def _compute_iou(self, box_a: OCRBoundingBox, box_b: OCRBoundingBox) -> float:
        """Compute Intersection over Union between two bounding boxes."""
        inter_left = max(box_a.left, box_b.left)
        inter_top = max(box_a.top, box_b.top)
        inter_right = min(box_a.right, box_b.right)
        inter_bottom = min(box_a.bottom, box_b.bottom)

        if inter_right <= inter_left or inter_bottom <= inter_top:
            return 0.0

        inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
        union_area = box_a.area + box_b.area - inter_area
        if union_area <= 0:
            return 0.0
        return inter_area / union_area


class MockVisualMatcher:
    """Mock visual matcher for deterministic test scenarios and offline testing."""

    def __init__(
        self,
        injected_status: VisualMatchStatus = VisualMatchStatus.MATCHED,
        injected_matches: Optional[List[VisualMatchRegion]] = None,
        is_available_flag: bool = True,
    ) -> None:
        self._injected_status = injected_status
        self._injected_matches = injected_matches or []
        self._is_available = is_available_flag
        self._kind = VisualMatcherKind.MOCK

    @property
    def matcher_kind(self) -> VisualMatcherKind:
        return self._kind

    def is_available(self) -> bool:
        return self._is_available

    async def match(
        self,
        template: VisualTemplate,
        image: Image.Image,
        policy: Optional[VisualMatchPolicy] = None,
        desktop_generation_id: int = 0,
        observation_id: Optional[str] = None,
    ) -> VisualMatchResult:
        if not self._is_available:
            return VisualMatchResult(
                status=VisualMatchStatus.UNSUPPORTED,
                matcher_kind=self._kind,
                template_id=template.template_id,
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                error_message="Mock visual matcher unavailable",
            )

        if not template.is_valid:
            return VisualMatchResult(
                status=VisualMatchStatus.INVALID_TEMPLATE,
                matcher_kind=self._kind,
                template_id=template.template_id,
                observation_id=observation_id,
                desktop_generation_id=desktop_generation_id,
                error_message="Invalid template",
            )

        best = self._injected_matches[0] if self._injected_matches else None
        return VisualMatchResult(
            status=self._injected_status,
            matcher_kind=self._kind,
            matches=self._injected_matches,
            best_match=best,
            template_id=template.template_id,
            observation_id=observation_id,
            desktop_generation_id=desktop_generation_id,
            duration_ms=1.5,
        )
