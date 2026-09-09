"""Capability Matcher mapping structured objectives to capabilities and evaluating limitations."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from orbit.runtime.capabilities.models import (
    Capability,
    CapabilityLimitation,
)
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.cognitive.models import StructuredObjective
from orbit.runtime.task_understanding.models import TaskUnderstandingResult

logger = logging.getLogger(__name__)


class CapabilityMatchReport:
    """Report detailing capability matching outcome and limitation violations."""

    def __init__(
        self,
        required_capability_ids: List[str],
        available_matched_capabilities: List[Capability],
        missing_capability_ids: List[str],
        triggered_limitations: List[CapabilityLimitation],
        semantic_target_type: str,
        is_fully_supported: bool,
    ) -> None:
        self.required_capability_ids = required_capability_ids
        self.available_matched_capabilities = available_matched_capabilities
        self.missing_capability_ids = missing_capability_ids
        self.triggered_limitations = triggered_limitations
        self.semantic_target_type = semantic_target_type
        self.is_fully_supported = is_fully_supported


class CapabilityMatcher:
    """Matches task objectives against registry capabilities, detecting missing skills or limitation violations."""

    # Keywords that indicate complex semantic/artistic visual content rather than basic geometry
    COMPLEX_VISUAL_KEYWORDS = {
        "portrait", "face", "boy", "girl", "man", "woman", "person",
        "human", "dog", "cat", "animal", "landscape", "scenery",
        "painting", "photo", "photograph", "realistic", "character", "tree", "car"
    }

    # Standard geometric shapes known to be natively supported by basic geometry routines
    BASIC_GEOMETRY_KEYWORDS = {
        "cube", "square", "circle", "rectangle", "triangle", "star",
        "line", "box", "polygon", "oval", "cube_3d", "diamond"
    }

    def __init__(self, registry: Optional[CapabilityRegistry] = None) -> None:
        self._registry = registry or CapabilityRegistry()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def match_objective(self, objective: StructuredObjective) -> CapabilityMatchReport:
        """Analyze a StructuredObjective and determine required capabilities and limitation violations."""
        prompt = getattr(objective, "raw_prompt", str(objective.user_goal or "")).lower()
        action_type = str(objective.parameters.get("action_type", "")).lower()
        target_app = str(objective.parameters.get("app_name", "")).lower()

        required_ids: List[str] = []
        triggered_limitations: List[CapabilityLimitation] = []
        semantic_target_type = "standard"

        # 1. Base Desktop Controls
        if target_app or "open" in prompt or "launch" in prompt:
            required_ids.append("LAUNCH_APPLICATION")
            required_ids.append("FOCUS_WINDOW")

        # 2. Text Entry
        if action_type == "type" or "type" in prompt or "write" in prompt:
            required_ids.append("TYPE_TEXT")

        # 3. Drawing & Visual Content
        if action_type == "draw" or "draw" in prompt or "paint" in prompt or "sketch" in prompt:
            # Determine whether the drawing goal is basic geometry or complex visual content
            is_complex = any(re.search(rf"\b{kw}\b", prompt) for kw in self.COMPLEX_VISUAL_KEYWORDS)
            is_basic = any(re.search(rf"\b{kw}\b", prompt) for kw in self.BASIC_GEOMETRY_KEYWORDS)

            if is_complex and not is_basic:
                semantic_target_type = "complex_artistic_visual"
                # Complex visual content requires IMAGE_GENERATE_AND_INSERT or specialized generative portrait skill
                required_ids.append("IMAGE_GENERATE_AND_INSERT")
            else:
                semantic_target_type = "geometric_primitive"
                required_ids.append("DRAW_BASIC_GEOMETRY")

        # Fallback if no specific action detected but has target entities
        if not required_ids:
            required_ids.append("CLICK_ELEMENT")

        # Deduplicate while preserving order
        seen: Set[str] = set()
        dedup_required: List[str] = []
        for rid in required_ids:
            if rid not in seen:
                seen.add(rid)
                dedup_required.append(rid)
        required_ids = dedup_required

        # 4. Check against registry availability & limitations
        available_matched: List[Capability] = []
        missing_ids: List[str] = []

        for cap_id in required_ids:
            cap = self._registry.get(cap_id)
            if cap is None or not cap.is_available:
                missing_ids.append(cap_id)
            else:
                available_matched.append(cap)
                # Check if this capability's explicit limitations are violated by the prompt
                lim = cap.violates_limitation(prompt)
                if lim:
                    triggered_limitations.append(lim)

        is_fully_supported = (len(missing_ids) == 0 and len(triggered_limitations) == 0)

        return CapabilityMatchReport(
            required_capability_ids=required_ids,
            available_matched_capabilities=available_matched,
            missing_capability_ids=missing_ids,
            triggered_limitations=triggered_limitations,
            semantic_target_type=semantic_target_type,
            is_fully_supported=is_fully_supported,
        )
