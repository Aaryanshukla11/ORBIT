"""Domain models and contracts for multi-modal perception fusion and confidence grounding."""

from __future__ import annotations

from enum import Enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.targeting.models import TargetBoundingBox


class EvidenceChannel(str, Enum):
    """Perception evidence channels available in ORBIT."""

    ACCESSIBILITY = "ACCESSIBILITY"        # UI Automation / MSAA element tree
    WIN32_WINDOW = "WIN32_WINDOW"          # Win32 top-level window structures
    OCR_TEXT = "OCR_TEXT"                  # Windows Native OCR / screen text recognition
    VISUAL_TEMPLATE = "VISUAL_TEMPLATE"    # 2D FFT Normalized Cross-Correlation visual template match


class SpatialRelation(str, Enum):
    """Geometric relationship between two spatial bounding boxes."""

    OVERLAPPING = "OVERLAPPING"            # Significant IoU overlap
    CONTAINED = "CONTAINED"                # One box completely inside the other
    ADJACENT_NEARBY = "ADJACENT_NEARBY"    # Non-overlapping but within spatial proximity threshold
    DISJOINT = "DISJOINT"                  # Far apart, no spatial relationship


class FusionStatus(str, Enum):
    """Outcome status of multi-modal evidence fusion."""

    RESOLVED = "RESOLVED"                  # Target uniquely resolved with validated agreement
    NOT_FOUND = "NOT_FOUND"                # Insufficient evidence discovered
    AMBIGUOUS = "AMBIGUOUS"                # Multiple candidate targets with similar evidence scores
    CONTRADICTORY = "CONTRADICTORY"        # Conflicting evidence from independent primary channels
    STALE_OBSERVATION = "STALE_OBSERVATION"# Evidence is stale or desktop generation mismatch
    LOW_CONFIDENCE = "LOW_CONFIDENCE"      # Evidence found but confidence below policy threshold
    UNSUPPORTED = "UNSUPPORTED"            # Requested fusion modality or channel unsupported


class PerceptionEvidence(BaseModel):
    """Standardized representation of evidence emitted by a single perception channel."""

    channel: EvidenceChannel = Field(..., description="Source perception channel")
    bounding_box: TargetBoundingBox = Field(..., description="Physical bounding box in virtual desktop coordinates")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Source-level confidence score")
    text_label: Optional[str] = Field(default=None, description="Extracted or matched text label")
    identifier: Optional[str] = Field(default=None, description="Unique element/window/template identifier")
    role: Optional[str] = Field(default=None, description="Control role or type (e.g. button, icon, text_region)")
    desktop_generation_id: int = Field(default=0, ge=0, description="Desktop generation ID at acquisition time")
    timestamp_ns: int = Field(default_factory=time.monotonic_ns, description="Monotonic acquisition timestamp")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Channel-specific diagnostic metadata")


class SpatialAgreement(BaseModel):
    """Evaluation of spatial consistency between two or more evidence bounding boxes."""

    iou: float = Field(default=0.0, ge=0.0, le=1.0, description="Intersection over Union score")
    centroid_distance_px: float = Field(default=0.0, ge=0.0, description="Distance between bounding box centroids")
    relation: SpatialRelation = Field(default=SpatialRelation.DISJOINT, description="Classified spatial relationship")
    is_aligned: bool = Field(default=False, description="True if spatial agreement criteria are satisfied")


class SemanticAgreement(BaseModel):
    """Evaluation of textual/semantic consistency across evidence channels."""

    is_matched: bool = Field(default=False, description="True if semantic criteria match")
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Normalized string/semantic similarity")
    matched_terms: List[str] = Field(default_factory=list, description="List of corroborated terms")


class FusionPolicy(BaseModel):
    """Configurable policy controlling multi-modal fusion rules and fail-closed gates."""

    min_individual_confidence: float = Field(default=0.60, ge=0.0, le=1.0, description="Minimum individual channel confidence")
    min_fused_confidence: float = Field(default=0.80, ge=0.0, le=1.0, description="Minimum overall fused confidence required for RESOLVED")
    max_spatial_distance_px: float = Field(default=120.0, ge=0.0, description="Max centroid distance for adjacent spatial corroboration")
    min_iou: float = Field(default=0.20, ge=0.0, le=1.0, description="Minimum IoU for overlapping spatial agreement")
    contradiction_distance_px: float = Field(default=150.0, ge=0.0, description="Centroid distance threshold triggering CONTRADICTORY failure")
    ambiguity_distance_margin_px: float = Field(default=20.0, ge=0.0, description="Distance margin between nearest and second nearest candidate")
    require_cross_modal_agreement: bool = Field(default=False, description="Whether at least 2 distinct channels must agree")


class FusedEvidence(BaseModel):
    """Corroborated evidence record combining multiple perception channels."""

    primary_channel: EvidenceChannel = Field(..., description="Primary channel providing spatial anchoring")
    supporting_channels: List[EvidenceChannel] = Field(default_factory=list, description="Channels corroborating the target")
    evidence_items: List[PerceptionEvidence] = Field(default_factory=list, description="All constituent evidence items")
    spatial_agreement: Optional[SpatialAgreement] = Field(default=None, description="Spatial agreement metrics")
    semantic_agreement: Optional[SemanticAgreement] = Field(default=None, description="Semantic agreement metrics")
    fused_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Grounded, non-inflated fused confidence score")
    is_contradictory: bool = Field(default=False, description="True if conflicting evidence was detected")
    contradiction_reason: Optional[str] = Field(default=None, description="Diagnostic explanation if contradictory")


class FusedTargetMatch(BaseModel):
    """A resolved candidate target backed by multi-modal fused evidence."""

    bounding_box: TargetBoundingBox = Field(..., description="Canonical bounding box in virtual desktop space")
    fused_evidence: FusedEvidence = Field(..., description="Corroborated multi-modal evidence")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall match confidence")
    primary_identifier: Optional[str] = Field(default=None, description="Matched primary identifier")
    primary_label: Optional[str] = Field(default=None, description="Matched primary label or text")


class MultiModalFusionResult(BaseModel):
    """Structured result of multi-modal evidence fusion."""

    status: FusionStatus = Field(..., description="Outcome status of fusion evaluation")
    fused_target: Optional[FusedTargetMatch] = Field(default=None, description="Resolved target if status is RESOLVED")
    candidates: List[FusedTargetMatch] = Field(default_factory=list, description="All evaluated candidate matches")
    evidence_count: int = Field(default=0, ge=0, description="Total individual evidence items processed")
    observation_id: Optional[str] = Field(default=None, description="Observation snapshot ID")
    desktop_generation_id: int = Field(default=0, ge=0, description="Desktop generation evaluated")
    diagnostic_message: Optional[str] = Field(default=None, description="Human/machine readable diagnostic explanation")

    @property
    def is_resolved(self) -> bool:
        return self.status == FusionStatus.RESOLVED and self.fused_target is not None
