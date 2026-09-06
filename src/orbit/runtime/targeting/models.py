"""Domain models and contracts for semantic target resolution and safe action points."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.models.common import BoundingBox


class TargetResolutionStatus(str, Enum):
    """Explicit outcome status of target localization against observation data."""

    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    CONTRADICTORY = "CONTRADICTORY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED = "UNSUPPORTED"


class TargetStrategy(str, Enum):
    """Strategy category for resolving a UI target."""

    ACCESSIBILITY_ELEMENT = "ACCESSIBILITY_ELEMENT"  # MSAA / UI Automation / Win32 control
    WINDOW_TITLE = "WINDOW_TITLE"                    # Window title / Process name matching
    COORDINATE_REGION = "COORDINATE_REGION"          # Explicit bounding box / declared safe region
    VISUAL_SEMANTIC = "VISUAL_SEMANTIC"              # Visual feature / template matching (legacy alias)
    VISUAL_TEMPLATE = "VISUAL_TEMPLATE"              # Visual icon / template matching
    ICON_TEMPLATE = "ICON_TEMPLATE"                  # Explicit icon template matching
    IMAGE_REGION = "IMAGE_REGION"                    # Image region matching
    OCR_TEXT = "OCR_TEXT"                            # Optical Character Recognition on screen pixels
    MULTIMODAL = "MULTIMODAL"                        # Multi-modal evidence fusion (UIA + OCR + Visual)
    FUSED_MULTIMODAL = "FUSED_MULTIMODAL"            # Alias for MULTIMODAL fusion strategy


class TargetIntent(BaseModel):
    """Declared operator intent describing a desired interaction target."""

    strategy: TargetStrategy = Field(
        default=TargetStrategy.ACCESSIBILITY_ELEMENT,
        description="Target resolution strategy",
    )
    name: Optional[str] = Field(default=None, description="Accessible name or label to match")
    text: Optional[str] = Field(default=None, description="Exact or normalized text to match via OCR")
    template_id: Optional[str] = Field(default=None, description="Registered visual template identifier")
    template: Optional[Any] = Field(default=None, description="VisualTemplate instance or raw template image/spec")
    exact_match: bool = Field(default=True, description="Whether to require exact text match (default True)")
    case_sensitive: bool = Field(default=False, description="Whether text matching is case sensitive")
    min_confidence: Optional[float] = Field(default=None, description="Minimum confidence threshold if available")
    role: Optional[str] = Field(default=None, description="Accessible role e.g. push button, edit, tab")
    automation_id: Optional[str] = Field(default=None, description="AutomationId property if defined")
    class_name: Optional[str] = Field(default=None, description="Win32 window class name if known")
    window_title: Optional[str] = Field(default=None, description="Target window title substring or exact match")
    process_name: Optional[str] = Field(default=None, description="Target executable name e.g. notepad.exe")
    target_hwnd: Optional[int] = Field(default=None, description="Win32 Window Handle to scope element search")
    explicit_bounds: Optional[BoundingBox] = Field(default=None, description="Explicit bounding box if strategy=COORDINATE_REGION")
    expected_outcome: Optional[Any] = Field(default=None, description="Optional expected outcome for post-action verification")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary targeting hints")


class TargetBoundingBox(BaseModel):
    """Immutable physical bounding box with validation and dimension accessors."""

    left: int = Field(..., description="Left pixel coordinate (inclusive)")
    top: int = Field(..., description="Top pixel coordinate (inclusive)")
    right: int = Field(..., description="Right pixel coordinate (exclusive)")
    bottom: int = Field(..., description="Bottom pixel coordinate (exclusive)")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @property
    def is_valid(self) -> bool:
        """Verify bounding box has positive dimensions and valid orientation."""
        return self.right > self.left and self.bottom > self.top

    def to_bounding_box(self) -> BoundingBox:
        """Convert to canonical ORBIT BoundingBox model."""
        return BoundingBox(
            left=self.left,
            top=self.top,
            width=max(0, self.width),
            height=max(0, self.height),
        )

    @classmethod
    def from_bounding_box(cls, box: BoundingBox) -> TargetBoundingBox:
        """Construct from canonical BoundingBox (left, top, width, height)."""
        return cls(
            left=box.left,
            top=box.top,
            right=box.left + box.width,
            bottom=box.top + box.height,
        )


class SafeActionPoint(BaseModel):
    """Calculated safe interior action point within a resolved target bounding box."""

    x: int = Field(..., description="Physical virtual desktop X coordinate")
    y: int = Field(..., description="Physical virtual desktop Y coordinate")
    bounding_box: TargetBoundingBox = Field(..., description="Source target bounding box")
    relative_x: float = Field(default=0.5, ge=0.0, le=1.0, description="Normalized horizontal offset")
    relative_y: float = Field(default=0.5, ge=0.0, le=1.0, description="Normalized vertical offset")
    desktop_generation_id: int = Field(..., ge=0, description="Authoritative desktop generation under which point was computed")
    calculated_at_ns: int = Field(default_factory=time.monotonic_ns)


class TargetEvidence(BaseModel):
    """Provenance record connecting a resolved target to underlying observation sources."""

    source: str = Field(..., description="Evidence channel: MSAA, UI_AUTOMATION, WIN32_WINDOW, OCR_TEXT, VISUAL_TEMPLATE, EXPLICIT_BOUNDS")
    identifier: Optional[str] = Field(default=None, description="Source element ID or window handle")
    name: Optional[str] = Field(default=None, description="Matched accessible name, title, or template ID")
    role: Optional[str] = Field(default=None, description="Matched role or control type")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Resolution confidence score")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Source-specific diagnostic metadata")


class ResolvedTarget(BaseModel):
    """Fully resolved UI target bound to a specific observation snapshot and desktop generation."""

    target_id: str = Field(..., description="Unique target identifier")
    bounding_box: TargetBoundingBox = Field(..., description="Physical bounding box on virtual desktop")
    safe_point: SafeActionPoint = Field(..., description="Validated safe interior action point")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Resolution confidence score")
    evidence: TargetEvidence = Field(..., description="Observation provenance record")
    observation_id: str = Field(..., description="Parent ObservationSnapshot snapshot_id")
    desktop_generation_id: int = Field(..., ge=0, description="Desktop generation ID at observation time")
    target_hwnd: Optional[int] = Field(default=None, description="Owning top-level window handle if applicable")
    resolved_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TargetResolutionResult(BaseModel):
    """Structured response from target locator containing outcome status and resolved target."""

    status: TargetResolutionStatus = Field(..., description="Outcome status of target resolution")
    target: Optional[ResolvedTarget] = Field(default=None, description="Resolved target if status is RESOLVED")
    candidates_count: int = Field(default=0, ge=0, description="Number of candidate elements discovered")
    diagnostic_message: Optional[str] = Field(default=None, description="Human/machine readable diagnostic explanation")
    observation_id: Optional[str] = Field(default=None, description="Observation snapshot ID evaluated")
    desktop_generation_id: Optional[int] = Field(default=None, description="Desktop generation evaluated")
    is_stale_observation: bool = Field(default=False, description="True if resolution failed due to stale observation")
