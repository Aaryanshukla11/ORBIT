"""Domain models and contracts for ORBIT visual template and icon perception."""

from __future__ import annotations

from enum import Enum
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
)


class VisualTemplateSource(str, Enum):
    """Trust and provenance boundary classification for visual templates."""

    TRUSTED_REGISTERED_TEMPLATE = "TRUSTED_REGISTERED_TEMPLATE"
    UNTRUSTED_RUNTIME_IMAGE = "UNTRUSTED_RUNTIME_IMAGE"


class VisualMatcherKind(str, Enum):
    """Identifier for the visual matching engine backend."""

    TEMPLATE_NCC = "TEMPLATE_NCC"
    MOCK = "MOCK"
    UNSUPPORTED = "UNSUPPORTED"


class VisualMatchStatus(str, Enum):
    """Explicit outcome status of a visual template matching operation."""

    MATCHED = "MATCHED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    INVALID_TEMPLATE = "INVALID_TEMPLATE"
    COORDINATE_MAPPING_FAILED = "COORDINATE_MAPPING_FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


class VisualTemplate(BaseModel):
    """Immutable representation of a visual icon or UI element template."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    template_id: str = Field(..., description="Unique deterministic template identifier")
    name: str = Field(..., description="Human-readable template name e.g. 'settings_gear_icon'")
    image: Any = Field(..., description="PIL Image or pixel buffer of template")
    width: int = Field(..., ge=1, description="Physical pixel width of template")
    height: int = Field(..., ge=1, description="Physical pixel height of template")
    source: VisualTemplateSource = Field(
        default=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
        description="Trust and provenance classification",
    )
    checksum: Optional[str] = Field(default=None, description="SHA-256 hash of template pixel bytes")
    semantic_intent: Optional[str] = Field(default=None, description="Intended semantic UI meaning")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary provenance metadata")

    @classmethod
    def from_image(
        cls,
        template_id: str,
        name: str,
        image: Image.Image,
        source: VisualTemplateSource = VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
        semantic_intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VisualTemplate:
        """Construct a VisualTemplate from a PIL Image, calculating dimensions and checksum."""
        img_rgb = image.convert("RGB")
        w, h = img_rgb.size
        # Calculate deterministic SHA-256 checksum of raw pixel bytes
        raw_bytes = img_rgb.tobytes()
        checksum = hashlib.sha256(raw_bytes).hexdigest()

        return cls(
            template_id=template_id,
            name=name,
            image=img_rgb,
            width=w,
            height=h,
            source=source,
            checksum=checksum,
            semantic_intent=semantic_intent or name,
            metadata=metadata or {},
        )

    @property
    def is_valid(self) -> bool:
        """Validate template dimensions and non-empty image data."""
        return self.width > 0 and self.height > 0 and self.image is not None


class VisualMatchRegion(BaseModel):
    """Candidate or confirmed visual match region on the virtual desktop."""

    template_id: str = Field(..., description="Matched template identifier")
    template_name: str = Field(..., description="Matched template name")
    bounding_box: OCRBoundingBox = Field(..., description="Bounding box of matched region")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Truthful normalized correlation score")
    scale_factor: float = Field(default=1.0, ge=0.1, le=10.0, description="DPI/geometry scale factor")
    source_provider: str = Field(default="TEMPLATE_NCC", description="Matcher backend identifier")
    coordinate_space: OCRCoordinateSpace = Field(
        default=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
        description="Coordinate space interpretation",
    )


class VisualMatchPolicy(BaseModel):
    """Deterministic policy controlling matching thresholds and ambiguity detection."""

    minimum_confidence: float = Field(default=0.85, ge=0.5, le=1.0, description="Minimum acceptable correlation score")
    ambiguity_margin: float = Field(default=0.05, ge=0.01, le=0.5, description="Margin between top two candidates")
    max_candidates: int = Field(default=5, ge=1, le=50, description="Maximum candidate matches to evaluate")
    allow_multi_scale: bool = Field(default=True, description="Whether to test multiple DPI scale candidates")
    scale_factors: List[float] = Field(
        default_factory=lambda: [1.0, 0.75, 1.25, 1.5, 2.0],
        description="Candidate scale factors",
    )


class VisualMatchResult(BaseModel):
    """Immutable result contract of a visual perception template matching scan."""

    status: VisualMatchStatus = Field(..., description="Explicit outcome status")
    matcher_kind: VisualMatcherKind = Field(..., description="Backend kind")
    matches: List[VisualMatchRegion] = Field(default_factory=list, description="All candidate match regions")
    best_match: Optional[VisualMatchRegion] = Field(default=None, description="Highest-confidence unique match")
    template_id: Optional[str] = Field(default=None, description="Queried template ID")
    observation_id: Optional[str] = Field(default=None, description="Associated ObservationSnapshot ID")
    desktop_generation_id: int = Field(default=0, ge=0, description="Desktop generation at capture time")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Matching duration in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Diagnostic error details if failed")
    timestamp_ns: int = Field(default_factory=time.perf_counter_ns, description="Monotonic timestamp")

    @property
    def is_success(self) -> bool:
        return self.status == VisualMatchStatus.MATCHED and self.best_match is not None

    @property
    def has_matches(self) -> bool:
        return len(self.matches) > 0
