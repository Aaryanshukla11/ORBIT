"""Domain models and contracts for ORBIT semantic perception, OCR, and coordinate mapping."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.models.common import BoundingBox


class OCRCoordinateSpace(str, Enum):
    """Explicit coordinate space interpretation for an OCR bounding box."""

    SCREENSHOT_PIXEL_SPACE = "SCREENSHOT_PIXEL_SPACE"
    WINDOW_CLIENT_SPACE = "WINDOW_CLIENT_SPACE"
    VIRTUAL_DESKTOP_SPACE = "VIRTUAL_DESKTOP_SPACE"
    LOGICAL_DPI_SPACE = "LOGICAL_DPI_SPACE"


class OCRStatus(str, Enum):
    """Explicit outcome status of an OCR extraction or coordinate mapping operation."""

    SUCCESS = "SUCCESS"
    NO_TEXT_FOUND = "NO_TEXT_FOUND"
    NO_TEXT = "NO_TEXT_FOUND"  # Alias for backward compatibility
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    INVALID_IMAGE = "INVALID_IMAGE"
    INVALID_INPUT = "INVALID_IMAGE"  # Alias for backward compatibility
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    COORDINATE_MAPPING_FAILED = "COORDINATE_MAPPING_FAILED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class OCRProviderKind(str, Enum):
    """Identifier for the OCR extraction engine backend."""

    WINDOWS_NATIVE = "WINDOWS_NATIVE"
    MOCK = "MOCK"
    UNSUPPORTED = "UNSUPPORTED"


class OCRBoundingBox(BaseModel):
    """Physical bounding box of a detected text region on screen or virtual desktop."""

    left: int = Field(..., description="Left pixel coordinate (inclusive)")
    top: int = Field(..., description="Top pixel coordinate (inclusive)")
    right: int = Field(..., description="Right pixel coordinate (exclusive)")
    bottom: int = Field(..., description="Bottom pixel coordinate (exclusive)")
    coordinate_space: OCRCoordinateSpace = Field(
        default=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
        description="Explicit coordinate space interpretation",
    )

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

    @property
    def center(self) -> Tuple[int, int]:
        """Calculates center coordinates."""
        return (self.left + self.width // 2, self.top + self.height // 2)

    def to_bounding_box(self) -> BoundingBox:
        """Convert to canonical ORBIT BoundingBox model."""
        return BoundingBox(
            left=self.left,
            top=self.top,
            width=max(0, self.width),
            height=max(0, self.height),
        )

    @classmethod
    def from_bounding_box(
        cls,
        box: BoundingBox,
        coordinate_space: OCRCoordinateSpace = OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
    ) -> OCRBoundingBox:
        """Construct from canonical BoundingBox."""
        return cls(
            left=box.left,
            top=box.top,
            right=box.left + box.width,
            bottom=box.top + box.height,
            coordinate_space=coordinate_space,
        )

    @classmethod
    def from_rect(
        cls,
        x: float,
        y: float,
        width: float,
        height: float,
        offset_x: int = 0,
        offset_y: int = 0,
        coordinate_space: OCRCoordinateSpace = OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
    ) -> OCRBoundingBox:
        """Construct from floating-point rectangle with origin offset."""
        left = int(round(x)) + offset_x
        top = int(round(y)) + offset_y
        right = int(round(x + width)) + offset_x
        bottom = int(round(y + height)) + offset_y
        return cls(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            coordinate_space=coordinate_space,
        )


class OCRWord(BaseModel):
    """Individual recognized word within a text line."""

    text: str = Field(..., description="Original recognized word text")
    normalized_text: str = Field(..., description="Deterministically normalized word text")
    bounding_box: OCRBoundingBox = Field(..., description="Physical bounding box of word")
    confidence: Optional[float] = Field(default=None, description="Truthful confidence score if available, else None")


class OCRTextRegion(BaseModel):
    """Recognized line or cohesive region of text with spatial bounding geometry."""

    text: str = Field(..., description="Original recognized line/region text")
    normalized_text: str = Field(..., description="Deterministically normalized line/region text")
    bounding_box: OCRBoundingBox = Field(..., description="Physical bounding box on virtual desktop")
    words: List[OCRWord] = Field(default_factory=list, description="Constituent words if line-level segmentation")
    confidence: Optional[float] = Field(default=None, description="Truthful confidence score if available, else None")
    source_provider: str = Field(default="WINDOWS_NATIVE", description="Provider identifying string")
    coordinate_space: OCRCoordinateSpace = Field(
        default=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
        description="Explicit coordinate space interpretation",
    )


class OCRResult(BaseModel):
    """Immutable result contract of an OCR perception scan."""

    status: OCRStatus = Field(..., description="Explicit outcome status")
    provider_kind: OCRProviderKind = Field(..., description="Backend kind")
    text_regions: List[OCRTextRegion] = Field(default_factory=list, description="Extracted text lines and regions")
    full_text: str = Field(default="", description="Aggregated full text of the observation")
    observation_id: Optional[str] = Field(default=None, description="Associated ObservationSnapshot ID")
    desktop_generation_id: int = Field(default=0, ge=0, description="Desktop generation at capture time")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Extraction duration in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Diagnostic error details if failed")
    timestamp_ns: int = Field(default_factory=time.perf_counter_ns, description="Monotonic timestamp")
    coordinate_space: OCRCoordinateSpace = Field(
        default=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
        description="Default coordinate space of text regions",
    )

    @property
    def is_success(self) -> bool:
        return self.status == OCRStatus.SUCCESS

    @property
    def has_text(self) -> bool:
        return self.status == OCRStatus.SUCCESS and len(self.text_regions) > 0
