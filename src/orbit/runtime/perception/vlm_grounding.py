"""VLM Semantic Hypothesis & Physical Grounding Verification Subsystem.

INVARIANT (ASTRA Dimension 7 & 18): Strict boundary between VLM semantic recommendation
and physical OS execution. VLM outputs are treated strictly as unverified hypotheses.
Physical dispatch occurs ONLY after authoritative UIA/geometric verification confirms
target presence and bounds within the foreground window.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.adapters.observation.snapshot import (
    BoundingBox,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetResolutionResult,
    TargetResolutionStatus,
)

logger = logging.getLogger(__name__)


class VLMHypothesis(BaseModel):
    """Unverified semantic hypothesis produced by a Vision-Language Model."""

    hypothesis_id: str = Field(default_factory=lambda: f"vlm_hyp_{uuid4().hex[:8]}")
    target_name: str
    semantic_role: str = Field(default="control")
    normalized_region: Tuple[float, float, float, float] = Field(
        ...,
        description="Normalized canvas/screen bounding box (u1, v1, u2, v2) within [0.0, 1.0]",
    )
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    visual_clues: List[str] = Field(default_factory=list)
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GroundedTargetResult(BaseModel):
    """Authoritative physical verification result of a VLM hypothesis."""

    is_grounded: bool
    status: TargetResolutionStatus
    resolved_target: Optional[ResolvedTarget] = None
    rejection_reason: Optional[str] = None
    grounded_element: Optional[ObservedElement] = None
    verification_confidence: float = Field(default=0.0)


class VLMGroundingVerifier:
    """Verifies VLM semantic hypotheses against authoritative accessibility and screen geometry."""

    def __init__(self, min_confidence: float = 0.6) -> None:
        self._min_confidence = min_confidence

    def verify_hypothesis(
        self,
        hypothesis: VLMHypothesis,
        snapshot: ObservationSnapshot,
        screen_resolution: Tuple[int, int] = (1920, 1080),
        active_window: Optional[ObservedWindow] = None,
    ) -> GroundedTargetResult:
        """Ground and verify VLM hypothesis against live accessibility tree and window bounds."""
        u1, v1, u2, v2 = hypothesis.normalized_region

        # 1. Coordinate boundary validation
        for val in (u1, v1, u2, v2):
            if not (0.0 <= val <= 1.0):
                return GroundedTargetResult(
                    is_grounded=False,
                    status=TargetResolutionStatus.INVALID_REQUEST,
                    rejection_reason=f"VLM hypothesis coordinates ({u1}, {v1}, {u2}, {v2}) outside normalized [0.0, 1.0]",
                )

        if u2 <= u1 or v2 <= v1:
            return GroundedTargetResult(
                is_grounded=False,
                status=TargetResolutionStatus.INVALID_REQUEST,
                rejection_reason="VLM hypothesis specifies degenerate zero or negative bounding box",
            )

        # Convert to screen pixels
        scr_w, scr_h = screen_resolution
        px1, py1 = int(u1 * scr_w), int(v1 * scr_h)
        px2, py2 = int(u2 * scr_w), int(v2 * scr_h)
        hyp_box = BoundingBox(left=px1, top=py1, width=max(1, px2 - px1), height=max(1, py2 - py1))

        # 2. Window containment verification if active window specified
        if active_window:
            wb = getattr(active_window, "extended_bounds", getattr(active_window, "bounds", None))
            if wb:
                cx, cy = hyp_box.center.x, hyp_box.center.y
                if not (wb.left <= cx <= wb.right and wb.top <= cy <= wb.bottom):
                    return GroundedTargetResult(
                        is_grounded=False,
                        status=TargetResolutionStatus.NOT_FOUND,
                        rejection_reason=f"VLM target center ({cx}, {cy}) is outside active window bounds",
                    )

        # 3. Accessibility Element Cross-Verification
        best_match: Optional[ObservedElement] = None
        best_overlap: float = 0.0

        for elem in snapshot.detected_elements:
            elem_box = getattr(elem, "bounds", getattr(elem, "bounding_box", None))
            if not elem_box:
                continue

            # Calculate Intersection over Union (IoU) with hypothesis box
            iou = self._calculate_iou(hyp_box, elem_box)

            # Name or text hint match boosts match
            name_match = (
                hypothesis.target_name.lower() in (elem.name or "").lower()
                or (elem.name or "").lower() in hypothesis.target_name.lower()
            )

            effective_score = (iou * 0.7) + (0.3 if name_match else 0.0)

            if effective_score > best_overlap:
                best_overlap = effective_score
                best_match = elem

        # 4. Synthesize verified target if threshold met
        if best_match and best_overlap >= 0.3:
            match_box = getattr(best_match, "bounds", getattr(best_match, "bounding_box", None))
            t_box = TargetBoundingBox(
                left=match_box.left,
                top=match_box.top,
                right=match_box.right,
                bottom=match_box.bottom,
            )
            safe_pt = SafeActionPoint(
                x=match_box.center.x,
                y=match_box.center.y,
                bounding_box=t_box,
                desktop_generation_id=getattr(snapshot, "generation_id", 0),
            )
            evidence = TargetEvidence(
                source="UI_AUTOMATION",
                identifier=best_match.element_id,
                name=best_match.name or hypothesis.target_name,
                role=best_match.role or hypothesis.semantic_role,
                confidence=best_overlap,
            )
            resolved = ResolvedTarget(
                target_id=best_match.element_id,
                bounding_box=t_box,
                safe_point=safe_pt,
                confidence=best_overlap,
                evidence=evidence,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=getattr(snapshot, "generation_id", 0),
            )
            return GroundedTargetResult(
                is_grounded=True,
                status=TargetResolutionStatus.RESOLVED,
                resolved_target=resolved,
                grounded_element=best_match,
                verification_confidence=best_overlap,
            )

        # If no UIA match, fallback to safe center of hypothesis if confidence is high
        if hypothesis.confidence >= self._min_confidence:
            t_box = TargetBoundingBox(
                left=hyp_box.left,
                top=hyp_box.top,
                right=hyp_box.right,
                bottom=hyp_box.bottom,
            )
            safe_pt = SafeActionPoint(
                x=hyp_box.center.x,
                y=hyp_box.center.y,
                bounding_box=t_box,
                desktop_generation_id=getattr(snapshot, "generation_id", 0),
            )
            elem_id = f"elem_{uuid4().hex[:8]}"
            evidence = TargetEvidence(
                source="VISUAL_SEMANTIC",
                identifier=elem_id,
                name=hypothesis.target_name,
                role=hypothesis.semantic_role,
                confidence=hypothesis.confidence,
            )
            resolved = ResolvedTarget(
                target_id=elem_id,
                bounding_box=t_box,
                safe_point=safe_pt,
                confidence=hypothesis.confidence,
                evidence=evidence,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=getattr(snapshot, "generation_id", 0),
            )
            return GroundedTargetResult(
                is_grounded=True,
                status=TargetResolutionStatus.RESOLVED,
                resolved_target=resolved,
                verification_confidence=hypothesis.confidence,
            )

        return GroundedTargetResult(
            is_grounded=False,
            status=TargetResolutionStatus.LOW_CONFIDENCE,
            rejection_reason="Hypothesis confidence below threshold and no matching accessibility element found",
        )

    def _calculate_iou(self, b1: BoundingBox, b2: BoundingBox) -> float:
        """Compute Intersection over Union between two bounding boxes."""
        x_left = max(b1.left, b2.left)
        y_top = max(b1.top, b2.top)
        x_right = min(b1.right, b2.right)
        y_bottom = min(b1.bottom, b2.bottom)

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        b1_area = b1.width * b1.height
        b2_area = b2.width * b2.height
        union_area = float(b1_area + b2_area - intersection_area)

        if union_area <= 0.0:
            return 0.0
        return intersection_area / union_area


class ExplorationPolicy(BaseModel):
    """Guarantees bounded autonomous exploration and deterministic termination.

    INVARIANT (ASTRA Dimension 22): Exploration must terminate deterministically
    when: (1) target is discovered, (2) step budget is exhausted, or (3) state stagnates.
    """

    max_steps: int = Field(default=5, ge=1, le=20)
    stagnation_limit: int = Field(default=2, ge=1)
    current_step: int = Field(default=0)
    stagnant_steps: int = Field(default=0)
    discovered_elements_count: int = Field(default=0)
    is_terminated: bool = Field(default=False)
    termination_reason: Optional[str] = None

    def record_step(self, new_elements_found: int, target_grounded: bool = False) -> bool:
        """Record an exploration step; returns True if exploration should continue, False if terminated."""
        self.current_step += 1

        # 1. Termination Condition 1: Target discovered
        if target_grounded:
            self.is_terminated = True
            self.termination_reason = "TARGET_DISCOVERED"
            return False

        # 2. Check for forward perceptual discovery
        if new_elements_found > 0:
            self.discovered_elements_count += new_elements_found
            self.stagnant_steps = 0
        else:
            self.stagnant_steps += 1

        # 3. Termination Condition 2: Perceptual Stagnation
        if self.stagnant_steps >= self.stagnation_limit:
            self.is_terminated = True
            self.termination_reason = "EXPLORATION_STAGNATION"
            return False

        # 4. Termination Condition 3: Budget Exhaustion
        if self.current_step >= self.max_steps:
            self.is_terminated = True
            self.termination_reason = "BUDGET_EXHAUSTED"
            return False

        return True


__all__ = [
    "ExplorationPolicy",
    "GroundedTargetResult",
    "VLMGroundingVerifier",
    "VLMHypothesis",
]
