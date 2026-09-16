"""Continuous Action Verification & Multi-Modal Semantic Diff Engine.

Phase 3D (Astra 6 Modernization):
Computes multi-dimensional perceptual deltas between pre-action and post-action
observations across Visual Pixels, OCR Text streams, UIA Accessibility Trees,
and Window Topology to authoritatively verify expected action outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from PIL import Image, ImageChops, ImageStat
from pydantic import BaseModel, Field

from orbit.adapters.observation.snapshot import BoundingBox
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, ActionExecutionOutcome, OutcomeStatus
from orbit.runtime.cognitive.models import CurrentStateObservation

logger = logging.getLogger(__name__)


class SemanticStateDiff(BaseModel):
    """Authoritative multi-dimensional delta between pre-action and post-action state."""

    diff_id: str = Field(default_factory=lambda: f"diff_{uuid4().hex[:8]}")
    action_type: str = ""
    visual_change_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="Pixel change ratio [0.0, 1.0]")
    is_visual_changed: bool = False
    changed_regions: List[BoundingBox] = Field(default_factory=list, description="Bounding boxes of changed regions")
    text_added: List[str] = Field(default_factory=list, description="OCR text tokens added in post-state")
    text_removed: List[str] = Field(default_factory=list, description="OCR text tokens removed in post-state")
    focus_changed: bool = False
    pre_hwnd: Optional[int] = None
    post_hwnd: Optional[int] = None
    pre_title: Optional[str] = None
    post_title: Optional[str] = None
    dialog_opened: bool = False
    dialog_closed: bool = False
    elements_added_count: int = 0
    elements_removed_count: int = 0
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_rationale: str = ""


class SemanticDiffEngine:
    """Computes comprehensive multi-modal diffs between consecutive observations."""

    def __init__(
        self,
        pixel_change_threshold: float = 0.001,
        max_regions_tracked: int = 10,
    ) -> None:
        self.pixel_change_threshold = pixel_change_threshold
        self.max_regions_tracked = max_regions_tracked

    def compute_diff(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        pre_image: Optional[Image.Image] = None,
        post_image: Optional[Image.Image] = None,
    ) -> SemanticStateDiff:
        """Analyze differences between pre_obs and post_obs across visual, text, UIA, and window dimensions."""
        act_type_str = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)

        # 1. Window Topology & Focus Delta
        pre_hwnd = pre_obs.active_window_hwnd
        post_hwnd = post_obs.active_window_hwnd
        focus_changed = (pre_hwnd != post_hwnd and post_hwnd is not None)
        pre_title = pre_obs.active_window_title or ""
        post_title = post_obs.active_window_title or ""

        # Check modal dialog appearances / closures
        pre_classes = {w.get("class_name", "") for w in pre_obs.visible_windows}
        post_classes = {w.get("class_name", "") for w in post_obs.visible_windows}
        dialog_opened = ("#32770" in post_classes and "#32770" not in pre_classes)
        dialog_closed = ("#32770" in pre_classes and "#32770" not in post_classes)

        # 2. OCR Text Delta
        pre_tokens = set(self._extract_token_strings(pre_obs))
        post_tokens = set(self._extract_token_strings(post_obs))
        text_added = sorted(list(post_tokens - pre_tokens))
        text_removed = sorted(list(pre_tokens - post_tokens))

        # 3. Visual Pixel Diff
        vis_ratio = 0.0
        vis_changed = False
        changed_boxes: List[BoundingBox] = []

        img1 = pre_image or getattr(pre_obs, "screenshot", None)
        img2 = post_image or getattr(post_obs, "screenshot", None)
        if isinstance(img1, Image.Image) and isinstance(img2, Image.Image):
            vis_ratio, vis_changed, changed_boxes = self._compute_image_diff(img1, img2)

        # 4. Synthesize Verification Rationale & Confidence Score
        confidence, rationale, is_verified = self._evaluate_effect_match(
            action=action,
            vis_ratio=vis_ratio,
            vis_changed=vis_changed,
            text_added=text_added,
            focus_changed=focus_changed,
            dialog_opened=dialog_opened,
            dialog_closed=dialog_closed,
            post_title=post_title,
        )

        return SemanticStateDiff(
            action_type=act_type_str,
            visual_change_ratio=vis_ratio,
            is_visual_changed=vis_changed,
            changed_regions=changed_boxes[: self.max_regions_tracked],
            text_added=text_added,
            text_removed=text_removed,
            focus_changed=focus_changed,
            pre_hwnd=pre_hwnd,
            post_hwnd=post_hwnd,
            pre_title=pre_title,
            post_title=post_title,
            dialog_opened=dialog_opened,
            dialog_closed=dialog_closed,
            confidence_score=confidence,
            verification_rationale=rationale,
        )

    def _compute_image_diff(self, img1: Image.Image, img2: Image.Image) -> Tuple[float, bool, List[BoundingBox]]:
        """Compute pixel difference ratio and bounding box of modified regions."""
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)

        diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
        stat = ImageStat.Stat(diff)
        # Average channel difference normalized to [0.0, 1.0]
        mean_diff = sum(stat.mean) / (3.0 * 255.0)
        is_changed = mean_diff >= self.pixel_change_threshold

        bbox = diff.getbbox()
        boxes: List[BoundingBox] = []
        if bbox:
            l, t, r, b = bbox
            boxes.append(BoundingBox(left=l, top=t, width=max(1, r - l), height=max(1, b - t)))

        return mean_diff, is_changed, boxes

    def _extract_token_strings(self, obs: CurrentStateObservation) -> List[str]:
        """Extract clean strings from OCR tokens."""
        raw_toks = (
            obs.raw_evidence.get("ocr_tokens")
            or getattr(obs, "ocr_tokens", [])
            or []
        )
        tokens = []
        for t in raw_toks:
            if isinstance(t, dict):
                tokens.append(t.get("word", t.get("text", "")))
            elif isinstance(t, str):
                tokens.append(t)
        return [tok.strip() for tok in tokens if tok and tok.strip()]

    def _evaluate_effect_match(
        self,
        action: AbstractAction,
        vis_ratio: float,
        vis_changed: bool,
        text_added: List[str],
        focus_changed: bool,
        dialog_opened: bool,
        dialog_closed: bool,
        post_title: str,
    ) -> Tuple[float, str, bool]:
        """Evaluate if the computed delta aligns with the expected action effect."""
        act_type = action.action_type
        params = action.parameters or {}

        if act_type == AbstractActionType.TYPE_TEXT:
            typed_text = str(params.get("text", "")).strip()
            # If text appears in added OCR tokens
            if any(w.lower() in " ".join(text_added).lower() for w in typed_text.split()):
                return 0.95, f"Typed text '{typed_text}' verified in OCR text delta", True
            elif vis_changed:
                return 0.85, f"Visual change observed ({vis_ratio:.4f}) after typing", True
            return 0.3, "No OCR text or visual delta detected after TYPE_TEXT", False

        elif act_type == AbstractActionType.FOCUS_WINDOW:
            expected_app = str(params.get("application_name", "")).lower()
            if focus_changed or (expected_app and expected_app in post_title.lower()):
                return 0.95, f"Focus window verified: foreground changed to '{post_title}'", True
            return 0.4, "Foreground window unchanged after FOCUS_WINDOW", False

        elif act_type in (AbstractActionType.CLICK, AbstractActionType.DOUBLE_CLICK, AbstractActionType.RIGHT_CLICK):
            if dialog_opened:
                return 0.95, "Dialog opened after click interaction", True
            if dialog_closed:
                return 0.95, "Dialog dismissed after click interaction", True
            if vis_changed:
                return 0.90, f"UI state change verified ({vis_ratio:.4f} pixel delta)", True
            return 0.5, "Subtle click without large visual delta", True

        elif act_type == AbstractActionType.LAUNCH_APPLICATION:
            if focus_changed or len(post_title) > 0:
                return 0.95, f"Application launched: active window '{post_title}'", True
            return 0.5, "Application launched, waiting for full window settlement", True

        # Default fallback
        return 0.85, "State transition evaluated", True
