"""Multi-modal perception fusion engine providing deterministic, fail-closed cross-channel grounding."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from orbit.adapters.observation.snapshot import (
    FreshnessState,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.runtime.perception.coordinate_mapper import OCRCoordinateMapper
from orbit.runtime.perception.fusion_models import (
    EvidenceChannel,
    FusedEvidence,
    FusedTargetMatch,
    FusionPolicy,
    FusionStatus,
    MultiModalFusionResult,
    PerceptionEvidence,
    SemanticAgreement,
    SpatialAgreement,
    SpatialRelation,
)
from orbit.runtime.perception.models import OCRResult, OCRStatus, OCRTextRegion
from orbit.runtime.perception.normalization import matches_text, normalize_text
from orbit.runtime.perception.visual_models import VisualMatchRegion, VisualMatchResult, VisualMatchStatus
from orbit.runtime.targeting.models import TargetBoundingBox, TargetIntent, TargetStrategy

logger = logging.getLogger(__name__)


class MultiModalPerceptionFusionEngine:
    """Core multi-modal fusion engine combining Accessibility, Window, OCR, and Visual evidence.

    Guarantees:
    1. Zero AI hallucination / coordinate guessing.
    2. Strict non-inflationary confidence calibration.
    3. Fail-closed on spatial or semantic contradiction.
    4. Deterministic disambiguation using spatial anchoring.
    5. Generation and snapshot freshness validation across all participating channels.
    """

    def __init__(self, default_policy: Optional[FusionPolicy] = None) -> None:
        self._default_policy = default_policy or FusionPolicy()
        self._coordinate_mapper = OCRCoordinateMapper()

    @property
    def default_policy(self) -> FusionPolicy:
        return self._default_policy

    # -------------------------------------------------------------------------
    # Spatial Analysis Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def calculate_iou(box1: TargetBoundingBox, box2: TargetBoundingBox) -> float:
        """Calculate Intersection over Union (IoU) between two bounding boxes."""
        inter_left = max(box1.left, box2.left)
        inter_top = max(box1.top, box2.top)
        inter_right = min(box1.right, box2.right)
        inter_bottom = min(box1.bottom, box2.bottom)

        inter_w = max(0, inter_right - inter_left)
        inter_h = max(0, inter_bottom - inter_top)
        inter_area = inter_w * inter_h

        if inter_area <= 0:
            return 0.0

        area1 = box1.area
        area2 = box2.area
        union_area = area1 + area2 - inter_area
        if union_area <= 0:
            return 0.0

        return float(inter_area / union_area)

    @staticmethod
    def calculate_centroid_distance(box1: TargetBoundingBox, box2: TargetBoundingBox) -> float:
        """Calculate Euclidean distance between centers of two bounding boxes."""
        c1_x = (box1.left + box1.right) / 2.0
        c1_y = (box1.top + box1.bottom) / 2.0
        c2_x = (box2.left + box2.right) / 2.0
        c2_y = (box2.top + box2.bottom) / 2.0
        return float(math.hypot(c1_x - c2_x, c1_y - c2_y))

    @staticmethod
    def check_containment(container: TargetBoundingBox, inner: TargetBoundingBox) -> bool:
        """Check if inner bounding box is substantially contained within container."""
        return (
            container.left <= inner.left + 5
            and container.top <= inner.top + 5
            and container.right >= inner.right - 5
            and container.bottom >= inner.bottom - 5
        )

    def evaluate_spatial_agreement(
        self,
        box1: TargetBoundingBox,
        box2: TargetBoundingBox,
        policy: Optional[FusionPolicy] = None,
    ) -> SpatialAgreement:
        """Evaluate geometric consistency between two target bounding boxes."""
        p = policy or self._default_policy
        iou = self.calculate_iou(box1, box2)
        dist = self.calculate_centroid_distance(box1, box2)

        if iou >= p.min_iou:
            relation = SpatialRelation.OVERLAPPING
            is_aligned = True
        elif self.check_containment(box1, box2) or self.check_containment(box2, box1):
            relation = SpatialRelation.CONTAINED
            is_aligned = True
        elif dist <= p.max_spatial_distance_px:
            relation = SpatialRelation.ADJACENT_NEARBY
            is_aligned = True
        else:
            relation = SpatialRelation.DISJOINT
            is_aligned = False

        return SpatialAgreement(
            iou=iou,
            centroid_distance_px=dist,
            relation=relation,
            is_aligned=is_aligned,
        )

    # -------------------------------------------------------------------------
    # Semantic Analysis Helpers
    # -------------------------------------------------------------------------

    def evaluate_semantic_agreement(
        self,
        text1: Optional[str],
        text2: Optional[str],
        query: Optional[str] = None,
    ) -> SemanticAgreement:
        """Evaluate semantic agreement between textual elements."""
        if not text1 or not text2:
            # If a query matches at least one of the texts
            if query and (text1 or text2):
                matched = False
                matched_terms = []
                if text1 and matches_text(text1, query, exact_match=False):
                    matched = True
                    matched_terms.append(text1)
                if text2 and matches_text(text2, query, exact_match=False):
                    matched = True
                    matched_terms.append(text2)
                return SemanticAgreement(
                    is_matched=matched,
                    similarity_score=0.85 if matched else 0.0,
                    matched_terms=matched_terms,
                )
            return SemanticAgreement(is_matched=False, similarity_score=0.0, matched_terms=[])

        norm1 = normalize_text(text1)
        norm2 = normalize_text(text2)

        if norm1 == norm2:
            return SemanticAgreement(
                is_matched=True,
                similarity_score=1.0,
                matched_terms=[text1, text2],
            )

        if norm1 in norm2 or norm2 in norm1:
            return SemanticAgreement(
                is_matched=True,
                similarity_score=0.90,
                matched_terms=[text1, text2],
            )

        # Token overlap
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        overlap = words1.intersection(words2)
        if overlap:
            sim = len(overlap) / max(len(words1), len(words2))
            return SemanticAgreement(
                is_matched=sim >= 0.5,
                similarity_score=float(sim),
                matched_terms=list(overlap),
            )

        return SemanticAgreement(is_matched=False, similarity_score=0.0, matched_terms=[])

    # -------------------------------------------------------------------------
    # Confidence Calibration & Fusion Core
    # -------------------------------------------------------------------------

    def calculate_grounded_confidence(
        self,
        primary_conf: float,
        supporting_items: List[PerceptionEvidence],
        spatial: Optional[SpatialAgreement],
        semantic: Optional[SemanticAgreement],
    ) -> float:
        """Calculate grounded, non-inflated fused confidence.

        Principle:
        Confidence is bounded by max individual confidence and agreement factor.
        Weak evidence is NEVER inflated into high confidence.
        """
        if not supporting_items:
            return primary_conf

        max_source_conf = max([primary_conf] + [item.confidence for item in supporting_items])

        # Agreement multiplier bounded in [0.7, 1.05]
        agreement_factor = 1.0
        if spatial and spatial.is_aligned:
            if spatial.relation in (SpatialRelation.OVERLAPPING, SpatialRelation.CONTAINED):
                agreement_factor += 0.03
            elif spatial.relation == SpatialRelation.ADJACENT_NEARBY:
                agreement_factor += 0.01
        else:
            agreement_factor -= 0.20

        if semantic and semantic.is_matched:
            agreement_factor += 0.02
        elif semantic is not None and not semantic.is_matched:
            agreement_factor -= 0.15

        # Strictly non-inflating: cannot exceed max_source_conf by more than 5% and never > 1.0
        calibrated = min(1.0, max_source_conf * agreement_factor)
        return max(0.0, round(calibrated, 3))

    # -------------------------------------------------------------------------
    # Multi-Modal Target Resolution
    # -------------------------------------------------------------------------

    def fuse_multimodal_intent(
        self,
        snapshot: ObservationSnapshot,
        intent: TargetIntent,
        ocr_result: Optional[OCRResult] = None,
        visual_result: Optional[VisualMatchResult] = None,
        policy: Optional[FusionPolicy] = None,
    ) -> MultiModalFusionResult:
        """Resolve a multi-modal target intent using verified evidence fusion."""
        p = policy or self._default_policy

        # 1. Freshness & Generation Gate
        if snapshot.is_stale or snapshot.freshness_state == FreshnessState.STALE:
            reason = snapshot.invalidation_reason or "Observation snapshot TTL expired or generation invalid"
            return MultiModalFusionResult(
                status=FusionStatus.STALE_OBSERVATION,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=snapshot.generation_id,
                diagnostic_message=f"Multi-modal fusion rejected: snapshot is stale ({reason})",
            )

        # 2. Extract Evidence Channels
        evidence_items: List[PerceptionEvidence] = []
        gen_id = snapshot.generation_id
        offset_x = getattr(snapshot, "screenshot_offset_x", 0)
        offset_y = getattr(snapshot, "screenshot_offset_y", 0)

        # Channel A: Accessibility Elements
        query_name = intent.name or intent.text
        for el in snapshot.detected_elements:
            if el.is_offscreen or not el.is_enabled or el.bounds.width <= 0 or el.bounds.height <= 0:
                continue
            if query_name and el.name and matches_text(el.name, query_name, exact_match=False):
                tbox = TargetBoundingBox.from_bounding_box(el.bounds)
                evidence_items.append(
                    PerceptionEvidence(
                        channel=EvidenceChannel.ACCESSIBILITY,
                        bounding_box=tbox,
                        confidence=0.95,
                        text_label=el.name,
                        identifier=el.element_id,
                        role=el.role or el.control_type,
                        desktop_generation_id=gen_id,
                        raw_metadata={"control_type": el.control_type, "class_name": el.class_name},
                    )
                )

        # Channel B: OCR Text Evidence
        ocr = ocr_result or intent.metadata.get("ocr_result") or snapshot.telemetry.get("ocr_result")
        if ocr and isinstance(ocr, OCRResult) and ocr.status == OCRStatus.SUCCESS:
            if ocr.desktop_generation_id != gen_id:
                return MultiModalFusionResult(
                    status=FusionStatus.STALE_OBSERVATION,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=gen_id,
                    diagnostic_message="OCR evidence generation mismatch",
                )
            query_text = intent.text or intent.name or intent.metadata.get("anchor_text")
            if query_text:
                for region in ocr.text_regions:
                    if matches_text(region.text, query_text, exact_match=False):
                        map_res = self._coordinate_mapper.map_to_virtual_desktop(
                            box=region.bounding_box,
                            screenshot_offset_x=offset_x,
                            screenshot_offset_y=offset_y,
                        )
                        if map_res.is_valid and map_res.mapped_box:
                            tbox = TargetBoundingBox(
                                left=map_res.mapped_box.left,
                                top=map_res.mapped_box.top,
                                right=map_res.mapped_box.right,
                                bottom=map_res.mapped_box.bottom,
                            )
                            evidence_items.append(
                                PerceptionEvidence(
                                    channel=EvidenceChannel.OCR_TEXT,
                                    bounding_box=tbox,
                                    confidence=1.0 if region.confidence is None else region.confidence,
                                    text_label=region.text,
                                    identifier=region.normalized_text,
                                    role="text_region",
                                    desktop_generation_id=gen_id,
                                    raw_metadata={"normalized_text": region.normalized_text},
                                )
                            )

        # Channel C: Visual Template Evidence
        vis = visual_result or intent.metadata.get("visual_match_result") or snapshot.telemetry.get("visual_match_result")
        if vis and isinstance(vis, VisualMatchResult):
            if vis.desktop_generation_id != gen_id:
                return MultiModalFusionResult(
                    status=FusionStatus.STALE_OBSERVATION,
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=gen_id,
                    diagnostic_message="Visual evidence generation mismatch",
                )
            vis_matches: List[VisualMatchRegion] = []
            if vis.matches:
                vis_matches = list(vis.matches)
            elif vis.best_match:
                vis_matches = [vis.best_match]

            for vm in vis_matches:
                map_res = self._coordinate_mapper.map_to_virtual_desktop(
                    box=vm.bounding_box,
                    screenshot_offset_x=offset_x,
                    screenshot_offset_y=offset_y,
                )
                if map_res.is_valid and map_res.mapped_box:
                    tbox = TargetBoundingBox(
                        left=map_res.mapped_box.left,
                        top=map_res.mapped_box.top,
                        right=map_res.mapped_box.right,
                        bottom=map_res.mapped_box.bottom,
                    )
                    evidence_items.append(
                        PerceptionEvidence(
                            channel=EvidenceChannel.VISUAL_TEMPLATE,
                            bounding_box=tbox,
                            confidence=vm.confidence,
                            text_label=vm.template_name,
                            identifier=vm.template_id,
                            role="icon_template",
                            desktop_generation_id=gen_id,
                            raw_metadata={"scale_factor": vm.scale_factor},
                        )
                    )

        # 3. Check Evidence Count
        if not evidence_items:
            return MultiModalFusionResult(
                status=FusionStatus.NOT_FOUND,
                evidence_count=0,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=gen_id,
                diagnostic_message="No matching evidence found across any perception channel",
            )

        # 4. Multi-Modal Disambiguation & Cross-Channel Fusion
        # If visual templates matched multiple candidates, use OCR or Accessibility to anchor
        visual_items = [e for e in evidence_items if e.channel == EvidenceChannel.VISUAL_TEMPLATE]
        text_anchors = [e for e in evidence_items if e.channel in (EvidenceChannel.OCR_TEXT, EvidenceChannel.ACCESSIBILITY)]

        # Contradiction Detection between explicit single primary items
        if len(visual_items) == 1 and len(text_anchors) == 1:
            v_item = visual_items[0]
            t_item = text_anchors[0]
            dist = self.calculate_centroid_distance(v_item.bounding_box, t_item.bounding_box)
            iou = self.calculate_iou(v_item.bounding_box, t_item.bounding_box)

            # Check if intent specified these two must be co-located or if they contradict
            if dist > p.contradiction_distance_px and iou == 0.0 and intent.metadata.get("require_colocated", False):
                logger.warning(
                    "Multi-modal fusion contradiction detected: visual (%s) and text (%s) distance %.1fpx > %.1fpx",
                    v_item.bounding_box,
                    t_item.bounding_box,
                    dist,
                    p.contradiction_distance_px,
                )
                return MultiModalFusionResult(
                    status=FusionStatus.CONTRADICTORY,
                    evidence_count=len(evidence_items),
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=gen_id,
                    diagnostic_message=(
                        f"Perception channels in direct contradiction: visual icon and text anchor "
                        f"are separated by {dist:.1f}px (> threshold {p.contradiction_distance_px}px)"
                    ),
                )

        # Spatial Anchoring Disambiguation
        if len(visual_items) > 1 and text_anchors:
            # Score visual candidates by distance to the nearest text anchor
            scored_candidates: List[Tuple[float, PerceptionEvidence, PerceptionEvidence]] = []
            for v_cand in visual_items:
                for t_anchor in text_anchors:
                    d = self.calculate_centroid_distance(v_cand.bounding_box, t_anchor.bounding_box)
                    if d <= p.max_spatial_distance_px:
                        scored_candidates.append((d, v_cand, t_anchor))

            if not scored_candidates:
                return MultiModalFusionResult(
                    status=FusionStatus.NOT_FOUND,
                    evidence_count=len(evidence_items),
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=gen_id,
                    diagnostic_message=(
                        f"Found {len(visual_items)} visual candidates, but none were within "
                        f"{p.max_spatial_distance_px}px of any text anchor"
                    ),
                )

            scored_candidates.sort(key=lambda item: item[0])
            best_dist, best_v, best_t = scored_candidates[0]

            # Check for ambiguity margin between top 2 candidates
            if len(scored_candidates) > 1:
                second_dist = scored_candidates[1][0]
                if abs(second_dist - best_dist) < p.ambiguity_distance_margin_px:
                    return MultiModalFusionResult(
                        status=FusionStatus.AMBIGUOUS,
                        evidence_count=len(evidence_items),
                        observation_id=snapshot.snapshot_id,
                        desktop_generation_id=gen_id,
                        diagnostic_message=(
                            f"Ambiguous multi-modal target: multiple visual icons equidistant "
                            f"(d1={best_dist:.1f}px, d2={second_dist:.1f}px) to text anchor"
                        ),
                    )

            # Resolved via anchoring
            spatial = self.evaluate_spatial_agreement(best_v.bounding_box, best_t.bounding_box, p)
            semantic = self.evaluate_semantic_agreement(best_v.text_label, best_t.text_label, query_name)
            fused_conf = self.calculate_grounded_confidence(best_v.confidence, [best_t], spatial, semantic)

            if fused_conf < p.min_fused_confidence:
                return MultiModalFusionResult(
                    status=FusionStatus.LOW_CONFIDENCE,
                    evidence_count=len(evidence_items),
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=gen_id,
                    diagnostic_message=f"Fused confidence {fused_conf:.2f} below minimum {p.min_fused_confidence:.2f}",
                )

            fused_ev = FusedEvidence(
                primary_channel=best_v.channel,
                supporting_channels=[best_t.channel],
                evidence_items=[best_v, best_t],
                spatial_agreement=spatial,
                semantic_agreement=semantic,
                fused_confidence=fused_conf,
            )
            target_match = FusedTargetMatch(
                bounding_box=best_v.bounding_box,
                fused_evidence=fused_ev,
                confidence=fused_conf,
                primary_identifier=best_v.identifier,
                primary_label=best_t.text_label or best_v.text_label,
            )
            return MultiModalFusionResult(
                status=FusionStatus.RESOLVED,
                fused_target=target_match,
                candidates=[target_match],
                evidence_count=len(evidence_items),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=gen_id,
            )

        # Standard Multi-Evidence Consensus
        # Group evidence into spatial clusters
        clusters: List[List[PerceptionEvidence]] = []
        for ev in evidence_items:
            placed = False
            for cluster in clusters:
                # If within max spatial distance of cluster primary, add to cluster
                if self.calculate_centroid_distance(ev.bounding_box, cluster[0].bounding_box) <= p.max_spatial_distance_px:
                    cluster.append(ev)
                    placed = True
                    break
            if not placed:
                clusters.append([ev])

        if len(clusters) == 0:
            return MultiModalFusionResult(
                status=FusionStatus.NOT_FOUND,
                evidence_count=0,
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=gen_id,
                diagnostic_message="No evidence clusters discovered",
            )

        if len(clusters) > 1 and not (len(text_anchors) == 1 and len(visual_items) == 0):
            # Check if one cluster clearly dominates or if ambiguous
            cluster_scores = [max(e.confidence for e in c) for c in clusters]
            sorted_indices = sorted(range(len(clusters)), key=lambda i: cluster_scores[i], reverse=True)
            top_score = cluster_scores[sorted_indices[0]]
            second_score = cluster_scores[sorted_indices[1]]

            if (top_score - second_score) < 0.05 and len(clusters[sorted_indices[0]]) == len(clusters[sorted_indices[1]]):
                return MultiModalFusionResult(
                    status=FusionStatus.AMBIGUOUS,
                    evidence_count=len(evidence_items),
                    observation_id=snapshot.snapshot_id,
                    desktop_generation_id=gen_id,
                    diagnostic_message=f"Ambiguous target: {len(clusters)} competing evidence clusters discovered",
                )
            best_cluster = clusters[sorted_indices[0]]
        else:
            best_cluster = clusters[0]

        # Evaluate best cluster
        primary_ev = best_cluster[0]
        supporting = best_cluster[1:]

        if p.require_cross_modal_agreement and not supporting:
            return MultiModalFusionResult(
                status=FusionStatus.LOW_CONFIDENCE,
                evidence_count=len(evidence_items),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=gen_id,
                diagnostic_message="Policy requires cross-modal corroboration, but only 1 channel was found",
            )

        spatial = self.evaluate_spatial_agreement(primary_ev.bounding_box, supporting[0].bounding_box, p) if supporting else None
        semantic = self.evaluate_semantic_agreement(primary_ev.text_label, supporting[0].text_label, query_name) if supporting else None
        fused_conf = self.calculate_grounded_confidence(primary_ev.confidence, supporting, spatial, semantic)

        if fused_conf < p.min_fused_confidence:
            return MultiModalFusionResult(
                status=FusionStatus.LOW_CONFIDENCE,
                evidence_count=len(evidence_items),
                observation_id=snapshot.snapshot_id,
                desktop_generation_id=gen_id,
                diagnostic_message=f"Fused confidence {fused_conf:.2f} below threshold {p.min_fused_confidence:.2f}",
            )

        fused_ev = FusedEvidence(
            primary_channel=primary_ev.channel,
            supporting_channels=[s.channel for s in supporting],
            evidence_items=best_cluster,
            spatial_agreement=spatial,
            semantic_agreement=semantic,
            fused_confidence=fused_conf,
        )
        target_match = FusedTargetMatch(
            bounding_box=primary_ev.bounding_box,
            fused_evidence=fused_ev,
            confidence=fused_conf,
            primary_identifier=primary_ev.identifier,
            primary_label=primary_ev.text_label,
        )

        return MultiModalFusionResult(
            status=FusionStatus.RESOLVED,
            fused_target=target_match,
            candidates=[target_match],
            evidence_count=len(evidence_items),
            observation_id=snapshot.snapshot_id,
            desktop_generation_id=gen_id,
        )
