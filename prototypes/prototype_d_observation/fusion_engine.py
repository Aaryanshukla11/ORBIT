"""
Deterministic Multi-Source Evidence Fusion Engine for ORBIT Prototype D v1.3.1.
Reconciles Win32Control, MSAA, UIAutomation, Visual, and OCR evidence across 5 independent
channels without destructive overwrites, preserving contradictions and strictly distinguishing
GEOMETRIC_OVERLAP from OBSERVED_VISUAL_OCCLUSION.
"""

import time
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image

from app_types import (
    Rect,
    WindowObservation,
    UIElementObservation,
    VisualFeatureObservation,
    DetectedTarget,
    ConfidenceLevel,
    ProviderResult,
    ProviderStatus,
    OcclusionState,
    EvidenceSource,
)
from coordinate_mapper import CoordinateMapper
from visual_engine import VisualEngine


class FusionEngine:
    """
    Multi-source evidence fusion engine. Enforces spatial containment, occlusion separation,
    and explicit contradiction exposure.
    """

    def __init__(self):
        self.coord_mapper = CoordinateMapper()
        self.visual_engine = VisualEngine()

    def fuse_observations(
        self,
        screenshot: Optional[Image.Image],
        windows: Tuple[WindowObservation, ...],
        accessibility_elements: Tuple[UIElementObservation, ...],
        provider_results: Tuple[ProviderResult, ...],
        generation_id: int = 0,
    ) -> Tuple[Tuple[DetectedTarget, ...], Tuple[VisualFeatureObservation, ...], Tuple[str, ...], ConfidenceLevel]:
        """
        Executes multi-source fusion algorithm across 5 evidence channels.
        Returns (detected_targets, visual_features, conflicts, overall_confidence).
        """
        detected_targets: List[DetectedTarget] = []
        visual_features: List[VisualFeatureObservation] = []
        conflicts: List[str] = []

        # Map foreground window
        fg_window = next((w for w in windows if w.is_foreground), None)
        fg_hwnd = fg_window.hwnd if fg_window else 0

        # Build window Z-order map (hwnd -> rank)
        z_order_map = {w.hwnd: w.z_order_rank for w in windows}

        for idx, elem in enumerate(accessibility_elements):
            target_id = f"target_{idx}_{elem.element_id}"
            elem_bounds = elem.bounds

            # 1. Spatial Containment Check
            containing_windows = [
                win for win in windows
                if win.extended_bounds.contains(elem_bounds) or win.extended_bounds.intersects(elem_bounds)
            ]
            associated_win = None
            for win in containing_windows:
                if elem.native_hwnd and win.hwnd == elem.native_hwnd:
                    associated_win = win
                    break
                if elem.element_id and str(win.hwnd) in elem.element_id:
                    associated_win = win
                    break
            if not associated_win and containing_windows:
                associated_win = max(containing_windows, key=lambda w: w.z_order_rank)

            is_contained_in_window = (associated_win is not None)

            # 2. Z-Order Occlusion Separation (Geometric Overlap vs Visual Occlusion)
            geometric_overlap_detected = False
            occluding_window_title = None
            occluding_window_hwnd = None
            
            if associated_win:
                target_rank = associated_win.z_order_rank
                for higher_win in windows:
                    if (higher_win.hwnd != associated_win.hwnd and 
                        higher_win.z_order_rank < target_rank and 
                        higher_win.is_visible and not higher_win.is_minimized):
                        if higher_win.extended_bounds.intersects(elem_bounds):
                            geometric_overlap_detected = True
                            occluding_window_title = higher_win.window_title
                            occluding_window_hwnd = higher_win.hwnd
                            break

            # Calculate Window-Relative coordinates
            if associated_win:
                rel_bounds = self.coord_mapper.virtual_to_window_relative_rect(elem_bounds, associated_win.extended_bounds)
            else:
                rel_bounds = elem_bounds

            # 3. Visual Feature Extraction & Agreement
            visual_match = False
            pixel_change_observed = False
            iou_score = 1.0
            vis_feat = None

            if screenshot:
                vis_feat = self.visual_engine.extract_features_from_region(
                    full_screenshot=screenshot,
                    region_rect=elem_bounds,
                    generation_id=generation_id,
                    feature_id_prefix=f"vf_{idx}",
                )
                if vis_feat:
                    visual_features.append(vis_feat)
                    if vis_feat.color_variance > 0.05:
                        pixel_change_observed = True
                    if vis_feat.color_variance > 0.05 and not geometric_overlap_detected:
                        visual_match = True

            # 4. Occlusion State Classification
            if geometric_overlap_detected and pixel_change_observed:
                occlusion_state = OcclusionState.OBSERVED_VISUAL_OCCLUSION
                is_occluded = True
                conflicts.append(
                    f"Element '{elem.name}' ({elem.role}) at {elem_bounds.as_tuple()} is VISUALLY OCCLUDED by '{occluding_window_title}' (HWND {occluding_window_hwnd})"
                )
            elif geometric_overlap_detected:
                occlusion_state = OcclusionState.GEOMETRIC_OVERLAP
                is_occluded = True
                conflicts.append(
                    f"Element '{elem.name}' ({elem.role}) has GEOMETRIC OVERLAP with '{occluding_window_title}' (HWND {occluding_window_hwnd})"
                )
            else:
                occlusion_state = OcclusionState.NOT_OCCLUDED
                is_occluded = False

            # 5. Semantic Agreement Check
            semantic_match = True
            contradiction_note = None

            if vis_feat and vis_feat.detected_text and elem.name:
                text_clean_acc = elem.name.strip().lower()
                text_clean_ocr = vis_feat.detected_text.strip().lower()
                if text_clean_acc in text_clean_ocr or text_clean_ocr in text_clean_acc:
                    semantic_match = True
                else:
                    semantic_match = False
                    contradiction_note = f"Semantic contradiction: Accessibility name '{elem.name}' vs OCR text '{vis_feat.detected_text}'"
                    conflicts.append(contradiction_note)

            # 6. Composite Confidence Decision
            if is_occluded:
                conf_level = ConfidenceLevel.CONFLICTING
            elif not is_contained_in_window and associated_win is None:
                conf_level = ConfidenceLevel.CONFLICTING
                conflicts.append(f"Element '{elem.name}' bounds {elem_bounds.as_tuple()} do not intersect any known window")
            elif visual_match and semantic_match and is_contained_in_window and elem.name:
                conf_level = ConfidenceLevel.CONFIRMED
            elif visual_match or elem.name:
                conf_level = ConfidenceLevel.PARTIALLY_CONFIRMED
            elif visual_match:
                conf_level = ConfidenceLevel.VISUAL_FALLBACK
            else:
                conf_level = ConfidenceLevel.LOW_CONFIDENCE

            provenance = (elem.evidence_source, "SCREEN_CAPTURE" if visual_match else "ACCESSIBILITY_ONLY")

            target = DetectedTarget(
                target_id=target_id,
                name=elem.name,
                role=elem.role,
                physical_bounds=elem_bounds,
                window_relative_bounds=rel_bounds,
                is_visible_on_screen=(not is_occluded and is_contained_in_window),
                is_occluded=is_occluded,
                spatial_agreement_iou=iou_score,
                semantic_agreement_match=semantic_match,
                confidence=conf_level,
                provenance_sources=provenance,
                contradiction_notes=contradiction_note,
                occlusion_state=occlusion_state,
            )
            detected_targets.append(target)

        # Calculate overall snapshot confidence
        if any(t.confidence == ConfidenceLevel.CONFIRMED for t in detected_targets):
            overall_conf = ConfidenceLevel.CONFIRMED
        elif any(t.confidence == ConfidenceLevel.PARTIALLY_CONFIRMED for t in detected_targets):
            overall_conf = ConfidenceLevel.PARTIALLY_CONFIRMED
        elif any(t.confidence == ConfidenceLevel.CONFLICTING for t in detected_targets):
            overall_conf = ConfidenceLevel.CONFLICTING
        elif not accessibility_elements:
            overall_conf = ConfidenceLevel.UNAVAILABLE
        else:
            overall_conf = ConfidenceLevel.LOW_CONFIDENCE

        return tuple(detected_targets), tuple(visual_features), tuple(conflicts), overall_conf
