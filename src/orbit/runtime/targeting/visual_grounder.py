"""Dense Visual Region & Set-of-Marks Target Grounder.

Phase 2G.3 (DIMENSION 18 - Visual Grounding & Set-of-Marks):
Resolves visual mark identifiers, bounding box coordinates, and visual regions
into physically verified SafeActionPoints and ResolvedTargets.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orbit.adapters.observation.snapshot import BoundingBox, ObservedWindow
from orbit.runtime.agent.contracts import SemanticTarget
from orbit.runtime.perception.set_of_marks import SOMMark, SOMResult
from orbit.runtime.targeting.action_point import calculate_safe_action_point
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetResolutionResult,
    TargetResolutionStatus,
)

logger = logging.getLogger(__name__)


class VisualRegionGrounder:
    """Authoritative grounder for Set-of-Marks identifiers and dense visual bounding coordinates."""

    def __init__(self) -> None:
        pass

    def resolve_from_som(
        self,
        target: SemanticTarget,
        som_result: SOMResult,
        active_window: Optional[ObservedWindow] = None,
        desktop_generation_id: int = 0,
        observation_id: str = "",
    ) -> TargetResolutionResult:
        """Resolve a semantic target referencing a Set-of-Marks identifier or label."""
        mark_id = self._extract_mark_id(target)
        matched_mark: Optional[SOMMark] = None

        if mark_id is not None:
            matched_mark = som_result.get_mark(mark_id)
            if not matched_mark:
                return TargetResolutionResult(
                    status=TargetResolutionStatus.NOT_FOUND,
                    rejection_reason=f"SOM mark [{mark_id}] does not exist in current observation mark map (total {len(som_result.marks)} marks)",
                )
        else:
            # Match by label or semantic name if no explicit mark_id integer
            matched_mark = self._match_mark_by_name(target.name, som_result.marks)

        if not matched_mark:
            return TargetResolutionResult(
                status=TargetResolutionStatus.NOT_FOUND,
                rejection_reason=f"No visual mark found matching target '{target.name}'",
            )

        box = matched_mark.bounding_box

        # Validate against active window containment if active_window provided
        if active_window and hasattr(active_window, "bounds") and active_window.bounds:
            win_box = active_window.bounds
            if not self._is_contained_or_overlapping(box, win_box):
                logger.warning(
                    "SOM mark [%d] at (%d, %d, %d, %d) outside active window %s bounds (%d, %d, %d, %d)",
                    matched_mark.mark_id,
                    box.left,
                    box.top,
                    box.right,
                    box.bottom,
                    active_window.title,
                    win_box.left,
                    win_box.top,
                    win_box.right,
                    win_box.bottom,
                )

        # Compute safe action point inside mark bounding box
        safe_pt = SafeActionPoint(
            x=matched_mark.center_point[0],
            y=matched_mark.center_point[1],
            bounding_box=box,
            desktop_generation_id=desktop_generation_id,
        )

        resolved = ResolvedTarget(
            target_id=f"som_tgt_{uuid4().hex[:8]}",
            bounding_box=box,
            safe_point=safe_pt,
            confidence=matched_mark.confidence,
            evidence=TargetEvidence(
                source="VISUAL_SOM",
                identifier=f"mark_{matched_mark.mark_id}",
                name=matched_mark.label or f"Mark {matched_mark.mark_id}",
                confidence=matched_mark.confidence,
                raw_metadata={
                    "mark_id": matched_mark.mark_id,
                    "role": matched_mark.role,
                    "original_source": matched_mark.source,
                },
            ),
            observation_id=observation_id,
            desktop_generation_id=desktop_generation_id,
        )

        return TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=resolved,
            evidence=[resolved.evidence],
        )

    def resolve_from_box_coordinates(
        self,
        normalized_box: Tuple[float, float, float, float],
        screen_dimensions: Tuple[int, int],
        target_name: str = "visual_region",
        active_window: Optional[ObservedWindow] = None,
        desktop_generation_id: int = 0,
        observation_id: str = "",
        confidence: float = 0.8,
    ) -> TargetResolutionResult:
        """Resolve a direct normalized 2D bounding box [u1, v1, u2, v2] into a physical target."""
        u1, v1, u2, v2 = normalized_box
        for val in (u1, v1, u2, v2):
            if not (0.0 <= val <= 1.0):
                return TargetResolutionResult(
                    status=TargetResolutionStatus.INVALID_REQUEST,
                    rejection_reason=f"Box coordinates ({u1}, {v1}, {u2}, {v2}) outside normalized range [0.0, 1.0]",
                )

        if u2 <= u1 or v2 <= v1:
            return TargetResolutionResult(
                status=TargetResolutionStatus.INVALID_REQUEST,
                rejection_reason="Degenerate zero or negative bounding box",
            )

        scr_w, scr_h = screen_dimensions
        px1, py1 = int(u1 * scr_w), int(v1 * scr_h)
        px2, py2 = int(u2 * scr_w), int(v2 * scr_h)

        box = TargetBoundingBox(left=px1, top=py1, right=px2, bottom=py2)
        cx = (px1 + px2) // 2
        cy = (py1 + py2) // 2

        safe_pt = SafeActionPoint(
            x=cx,
            y=cy,
            bounding_box=box,
            desktop_generation_id=desktop_generation_id,
        )

        resolved = ResolvedTarget(
            target_id=f"vis_tgt_{uuid4().hex[:8]}",
            bounding_box=box,
            safe_point=safe_pt,
            confidence=confidence,
            evidence=TargetEvidence(
                source="VISUAL_BBOX",
                identifier=f"box_{px1}_{py1}_{px2}_{py2}",
                name=target_name,
                confidence=confidence,
                raw_metadata={"normalized_box": [u1, v1, u2, v2]},
            ),
            observation_id=observation_id,
            desktop_generation_id=desktop_generation_id,
        )

        return TargetResolutionResult(
            status=TargetResolutionStatus.RESOLVED,
            target=resolved,
            evidence=[resolved.evidence],
        )

    def _extract_mark_id(self, target: SemanticTarget) -> Optional[int]:
        """Extract numeric mark index from target parameters, role, or name."""
        # 1. Direct parameter
        if hasattr(target, "parameters") and target.parameters:
            if "mark_id" in target.parameters:
                try:
                    return int(target.parameters["mark_id"])
                except (ValueError, TypeError):
                    pass
            if "mark" in target.parameters:
                try:
                    return int(target.parameters["mark"])
                except (ValueError, TypeError):
                    pass

        # 2. Bracketed regex in target name e.g. "Save [3]", "[12]", "Mark #5", "mark 4"
        if target.name:
            match = re.search(r"\[(\d+)\]", target.name)
            if match:
                return int(match.group(1))
            match = re.search(r"(?:mark|tag|badge)\s*#?\s*(\d+)", target.name, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return None

    def _match_mark_by_name(self, name: Optional[str], marks: List[SOMMark]) -> Optional[SOMMark]:
        """Match mark by exact or case-insensitive label substring."""
        if not name:
            return None
        clean_name = name.strip().lower()

        # Exact label match
        for m in marks:
            if m.label and m.label.strip().lower() == clean_name:
                return m

        # Substring label match
        for m in marks:
            if m.label and clean_name in m.label.strip().lower():
                return m

        return None

    def _is_contained_or_overlapping(self, box: TargetBoundingBox, win_box: Any) -> bool:
        """Check if box overlaps with window bounding box."""
        w_left = getattr(win_box, "left", 0)
        w_top = getattr(win_box, "top", 0)
        w_right = getattr(win_box, "right", 0) or (w_left + getattr(win_box, "width", 0))
        w_bottom = getattr(win_box, "bottom", 0) or (w_top + getattr(win_box, "height", 0))

        return not (
            box.right < w_left
            or box.left > w_right
            or box.bottom < w_top
            or box.top > w_bottom
        )
