"""Set-of-Marks (SOM) Visual Overlay Generator & Multi-Modal Grounding Subsystem.

Phase 2G.3 (DIMENSION 18 - Visual Grounding & Set-of-Marks):
Provides dense visual mark tagging for screen images, enabling Vision-Language Models
and decision engines to ground actions against non-standard, custom-drawn, canvas,
or legacy UI components where accessibility trees are incomplete or missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont

from orbit.adapters.observation.snapshot import BoundingBox, ObservedElement
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetResolutionResult,
    TargetResolutionStatus,
)

logger = logging.getLogger(__name__)

# High-contrast color palette for visual mark tags
SOM_PALETTE = [
    "#FF0055",  # Neon Crimson
    "#00E5FF",  # Electric Cyan
    "#76FF03",  # Bright Lime
    "#FFD600",  # Vivid Gold
    "#D500F9",  # Neon Purple
    "#FF6D00",  # Bright Orange
    "#00E676",  # Emerald Green
    "#2979FF",  # Vivid Blue
    "#FF1744",  # Coral Red
    "#00B0FF",  # Sky Blue
]


@dataclass
class SOMMark:
    """A single numbered visual mark tagged on a UI surface."""

    mark_id: int
    bounding_box: TargetBoundingBox
    center_point: Tuple[int, int]
    label: Optional[str] = None
    role: Optional[str] = None
    source: str = "UIA"  # "UIA", "OCR", "VISUAL_CONTOUR", "HYPOTHESIS"
    confidence: float = 0.9
    color_hex: str = "#FF0055"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mark_id": self.mark_id,
            "bounding_box": {
                "left": self.bounding_box.left,
                "top": self.bounding_box.top,
                "right": self.bounding_box.right,
                "bottom": self.bounding_box.bottom,
                "width": self.bounding_box.width,
                "height": self.bounding_box.height,
            },
            "center_point": self.center_point,
            "label": self.label,
            "role": self.role,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class SOMResult:
    """Result of generating a Set-of-Marks overlay on a screenshot."""

    annotated_image: Image.Image
    marks: List[SOMMark] = field(default_factory=list)
    mark_map: Dict[int, SOMMark] = field(default_factory=dict)
    image_dimensions: Tuple[int, int] = (1920, 1080)
    session_id: str = field(default_factory=lambda: f"som_{uuid4().hex[:8]}")

    def get_mark(self, mark_id: int) -> Optional[SOMMark]:
        return self.mark_map.get(mark_id)

    def to_summary_text(self, max_marks: int = 50) -> str:
        """Generate structured text description of marks for multi-modal prompts."""
        lines = [f"Set-of-Marks contains {len(self.marks)} visual elements:"]
        for m in self.marks[:max_marks]:
            lbl = f" '{m.label}'" if m.label else ""
            role = f" ({m.role})" if m.role else ""
            lines.append(
                f"[{m.mark_id}]{lbl}{role} at ({m.bounding_box.left}, {m.bounding_box.top}, "
                f"{m.bounding_box.right}, {m.bounding_box.bottom}) via {m.source}"
            )
        if len(self.marks) > max_marks:
            lines.append(f"... and {len(self.marks) - max_marks} more marks.")
        return "\n".join(lines)


class SetOfMarksGenerator:
    """Generates visual mark overlays on screenshots and builds bidirectional mark index mappings."""

    def __init__(
        self,
        min_mark_size: int = 12,
        max_marks: int = 150,
        iou_overlap_threshold: float = 0.70,
        badge_font_size: int = 14,
    ) -> None:
        self.min_mark_size = min_mark_size
        self.max_marks = max_marks
        self.iou_overlap_threshold = iou_overlap_threshold
        self.badge_font_size = badge_font_size

    def generate_som(
        self,
        image: Image.Image,
        uia_elements: Optional[Sequence[Any]] = None,
        ocr_tokens: Optional[Sequence[Dict[str, Any]]] = None,
        active_window_bounds: Optional[Tuple[int, int, int, int]] = None,
        draw_labels: bool = True,
    ) -> SOMResult:
        """Produce an annotated Set-of-Marks image and structured mark index."""
        w, h = image.size
        candidate_boxes: List[Tuple[TargetBoundingBox, Optional[str], Optional[str], str, float]] = []

        # 1. Harvest UIA interactable elements
        if uia_elements:
            for elem in uia_elements:
                bbox = self._extract_uia_bbox(elem)
                if not bbox:
                    continue
                # Skip tiny degenerate elements
                if bbox.width < self.min_mark_size or bbox.height < self.min_mark_size:
                    continue
                name = getattr(elem, "name", "") or getattr(elem, "control_name", "") or None
                role = getattr(elem, "control_type", "") or getattr(elem, "role", "") or "control"
                # Filter out container roots that span the entire screen
                if bbox.width > w * 0.95 and bbox.height > h * 0.95:
                    continue
                candidate_boxes.append((bbox, name, role, "UIA", 0.95))

        # 2. Harvest OCR tokens
        if ocr_tokens:
            for token in ocr_tokens:
                bbox = self._extract_ocr_bbox(token)
                if not bbox:
                    continue
                if bbox.width < self.min_mark_size or bbox.height < self.min_mark_size:
                    continue
                text = token.get("text") or token.get("word") or token.get("content") or None
                candidate_boxes.append((bbox, text, "text", "OCR", 0.85))

        # 3. Filter by active window bounds if provided
        if active_window_bounds:
            win_l, win_t, win_r, win_b = active_window_bounds
            filtered_candidates = []
            for box, name, role, source, conf in candidate_boxes:
                # Include if box overlaps substantially with active window
                if (
                    box.right > win_l
                    and box.left < win_r
                    and box.bottom > win_t
                    and box.top < win_b
                ):
                    filtered_candidates.append((box, name, role, source, conf))
            candidate_boxes = filtered_candidates

        # 4. Deduplicate overlapping marks via Non-Maximum Suppression (IoU filter)
        deduped = self._deduplicate_boxes(candidate_boxes, self.iou_overlap_threshold)

        # Cap to max marks
        deduped = deduped[: self.max_marks]

        # 5. Build SOMMark objects
        marks: List[SOMMark] = []
        mark_map: Dict[int, SOMMark] = {}
        for idx, (box, name, role, source, conf) in enumerate(deduped, start=1):
            cx = (box.left + box.right) // 2
            cy = (box.top + box.bottom) // 2
            palette_color = SOM_PALETTE[(idx - 1) % len(SOM_PALETTE)]
            mark = SOMMark(
                mark_id=idx,
                bounding_box=box,
                center_point=(cx, cy),
                label=name,
                role=role,
                source=source,
                confidence=conf,
                color_hex=palette_color,
            )
            marks.append(mark)
            mark_map[idx] = mark

        # 6. Render annotations on image copy
        annotated = image.copy().convert("RGB")
        if draw_labels and marks:
            self._render_overlay(annotated, marks)

        return SOMResult(
            annotated_image=annotated,
            marks=marks,
            mark_map=mark_map,
            image_dimensions=(w, h),
        )

    def _render_overlay(self, image: Image.Image, marks: List[SOMMark]) -> None:
        """Draw bounding boxes and mark number badges on image."""
        draw = ImageDraw.Draw(image, "RGBA")
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        for mark in marks:
            box = mark.bounding_box
            color = mark.color_hex

            # Draw outer box border
            draw.rectangle(
                [(box.left, box.top), (box.right, box.bottom)],
                outline=color,
                width=2,
            )

            # Draw badge tag at top-left of box
            tag_text = str(mark.mark_id)
            badge_w = max(18, len(tag_text) * 9 + 8)
            badge_h = 16

            badge_x1 = max(0, box.left)
            badge_y1 = max(0, box.top - badge_h)
            badge_x2 = badge_x1 + badge_w
            badge_y2 = badge_y1 + badge_h

            # Draw solid background badge
            draw.rectangle(
                [(badge_x1, badge_y1), (badge_x2, badge_y2)],
                fill=color,
            )

            # Draw text inside badge in black
            text_x = badge_x1 + 4
            text_y = badge_y1 + 1
            if font:
                draw.text((text_x, text_y), tag_text, fill="#000000", font=font)
            else:
                draw.text((text_x, text_y), tag_text, fill="#000000")

    def _deduplicate_boxes(
        self,
        candidates: List[Tuple[TargetBoundingBox, Optional[str], Optional[str], str, float]],
        iou_thresh: float,
    ) -> List[Tuple[TargetBoundingBox, Optional[str], Optional[str], str, float]]:
        """Deduplicate bounding boxes that overlap significantly, prioritizing UIA over OCR."""
        # Sort candidates: UIA first, then by confidence descending, then by area ascending
        def sort_key(item: Tuple[TargetBoundingBox, Optional[str], Optional[str], str, float]):
            box, _, _, source, conf = item
            src_prio = 0 if source == "UIA" else 1
            area = box.width * box.height
            return (src_prio, -conf, area)

        sorted_cands = sorted(candidates, key=sort_key)
        kept: List[Tuple[TargetBoundingBox, Optional[str], Optional[str], str, float]] = []

        for cand in sorted_cands:
            box_a = cand[0]
            overlap = False
            for existing in kept:
                box_b = existing[0]
                iou = self._calculate_iou(box_a, box_b)
                if iou >= iou_thresh:
                    overlap = True
                    break
            if not overlap:
                kept.append(cand)

        return kept

    def _calculate_iou(self, box_a: TargetBoundingBox, box_b: TargetBoundingBox) -> float:
        """Compute Intersection over Union (IoU) between two bounding boxes."""
        x_left = max(box_a.left, box_b.left)
        y_top = max(box_a.top, box_b.top)
        x_right = min(box_a.right, box_b.right)
        y_bottom = min(box_a.bottom, box_b.bottom)

        if x_right <= x_left or y_bottom <= y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        area_a = max(1, (box_a.right - box_a.left) * (box_a.bottom - box_a.top))
        area_b = max(1, (box_b.right - box_b.left) * (box_b.bottom - box_b.top))
        union_area = area_a + area_b - intersection_area

        if union_area <= 0:
            return 0.0
        return intersection_area / union_area

    def _extract_uia_bbox(self, elem: Any) -> Optional[TargetBoundingBox]:
        """Extract TargetBoundingBox from UIA element/snapshot representation."""
        if hasattr(elem, "bounding_box"):
            bb = elem.bounding_box
            if hasattr(bb, "left") and hasattr(bb, "top") and hasattr(bb, "right") and hasattr(bb, "bottom"):
                return TargetBoundingBox(left=int(bb.left), top=int(bb.top), right=int(bb.right), bottom=int(bb.bottom))
            if hasattr(bb, "left") and hasattr(bb, "top") and hasattr(bb, "width") and hasattr(bb, "height"):
                return TargetBoundingBox(
                    left=int(bb.left),
                    top=int(bb.top),
                    right=int(bb.left + bb.width),
                    bottom=int(bb.top + bb.height),
                )
        if hasattr(elem, "bounds") and isinstance(elem.bounds, (list, tuple)) and len(elem.bounds) == 4:
            l, t, r, b = elem.bounds
            return TargetBoundingBox(left=int(l), top=int(t), right=int(r), bottom=int(b))
        return None

    def _extract_ocr_bbox(self, token: Dict[str, Any]) -> Optional[TargetBoundingBox]:
        """Extract TargetBoundingBox from OCR token dictionary."""
        if "bbox" in token and isinstance(token["bbox"], (list, tuple)) and len(token["bbox"]) == 4:
            l, t, r, b = token["bbox"]
            return TargetBoundingBox(left=int(l), top=int(t), right=int(r), bottom=int(b))
        if "left" in token and "top" in token and "right" in token and "bottom" in token:
            return TargetBoundingBox(
                left=int(token["left"]),
                top=int(token["top"]),
                right=int(token["right"]),
                bottom=int(token["bottom"]),
            )
        if "left" in token and "top" in token and "width" in token and "height" in token:
            return TargetBoundingBox(
                left=int(token["left"]),
                top=int(token["top"]),
                right=int(token["left"] + token["width"]),
                bottom=int(token["top"] + token["height"]),
            )
        return None
