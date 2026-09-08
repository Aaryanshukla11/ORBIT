"""Domain models and contracts for ORBIT multimodal desktop perception (Step 3).

Defines canonical representations for:
- DesktopObservation (the single canonical live computer state snapshot)
- WindowObservation (Win32 window hierarchy, focus, bounds, and process metadata)
- ScreenshotObservation (live visual frame, dimensions, and base64 reference)
- OCRToken (on-screen text tokens and physical bounds)
- UIElementObservation (UI Automation accessibility hierarchy, roles, and states)
- VisualRegion (perceptual/vision regions e.g. canvas, dialogs, buttons)
- PerceivedElement & PerceptionEvidence (fused multi-source semantic UI entities)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4
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
    NO_TEXT = "NO_TEXT_FOUND"  # Alias
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    INVALID_IMAGE = "INVALID_IMAGE"
    INVALID_INPUT = "INVALID_IMAGE"  # Alias
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
        return self.right > self.left and self.bottom > self.top

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def to_bounding_box(self) -> BoundingBox:
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
    confidence: Optional[float] = Field(default=None, description="Confidence score if available")


class OCRTextRegion(BaseModel):
    """Recognized line or cohesive region of text with spatial bounding geometry."""

    text: str = Field(..., description="Original recognized line/region text")
    normalized_text: str = Field(..., description="Deterministically normalized line/region text")
    bounding_box: OCRBoundingBox = Field(..., description="Physical bounding box on virtual desktop")
    words: List[OCRWord] = Field(default_factory=list, description="Constituent words")
    confidence: Optional[float] = Field(default=None, description="Confidence score if available")
    source_provider: str = Field(default="WINDOWS_NATIVE", description="Provider identifier")
    coordinate_space: OCRCoordinateSpace = Field(
        default=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
        description="Coordinate space of bounds",
    )


class OCRResult(BaseModel):
    """Immutable result contract of an OCR perception scan."""

    status: OCRStatus = Field(..., description="Outcome status")
    provider_kind: OCRProviderKind = Field(..., description="Backend kind")
    text_regions: List[OCRTextRegion] = Field(default_factory=list, description="Extracted text regions")
    full_text: str = Field(default="", description="Aggregated full text")
    observation_id: Optional[str] = Field(default=None, description="Associated observation ID")
    desktop_generation_id: int = Field(default=0, ge=0, description="Desktop generation at capture")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Extraction duration in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Diagnostic error if failed")
    timestamp_ns: int = Field(default_factory=time.perf_counter_ns, description="Monotonic timestamp")
    coordinate_space: OCRCoordinateSpace = Field(
        default=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
        description="Default coordinate space",
    )

    @property
    def is_success(self) -> bool:
        return self.status == OCRStatus.SUCCESS

    @property
    def has_text(self) -> bool:
        return self.status == OCRStatus.SUCCESS and len(self.text_regions) > 0


# ==============================================================================
# CANONICAL STEP 3 PERCEPTION DOMAIN MODELS
# ==============================================================================

class VisualRegionType(str, Enum):
    """Classification of visual and spatial regions on screen."""

    APPLICATION_WINDOW = "APPLICATION_WINDOW"
    BUTTON = "BUTTON"
    TEXT_FIELD = "TEXT_FIELD"
    CANVAS = "CANVAS"
    IMAGE = "IMAGE"
    DIALOG = "DIALOG"
    MENU = "MENU"
    TOOLBAR = "TOOLBAR"
    BROWSER_CONTENT = "BROWSER_CONTENT"
    UNKNOWN = "UNKNOWN"


class VisualRegion(BaseModel):
    """A semantically meaningful rectangular region detected visually on screen."""

    region_id: str = Field(default_factory=lambda: f"vreg_{uuid4().hex[:8]}", description="Unique region ID")
    region_type: VisualRegionType = Field(default=VisualRegionType.UNKNOWN, description="Region semantic classification")
    bounds: BoundingBox = Field(..., description="Physical bounding box on virtual desktop")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    description: str = Field(default="", description="Human/model-readable description of region")
    source: str = Field(default="VISUAL_ENGINE", description="Detection source: VISUAL_ENGINE, VISION_MODEL, WIN32")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic region metadata")


class WindowObservation(BaseModel):
    """Live state observation of a single Win32 top-level window."""

    hwnd: int = Field(..., description="Win32 Window Handle")
    title: str = Field(default="", description="Window title / caption text")
    window_class: str = Field(default="", description="Win32 Window Class Name")
    is_foreground: bool = Field(default=False, description="Whether this window is the active foreground window")
    is_visible: bool = Field(default=True, description="Whether the window is visible on desktop")
    is_minimized: bool = Field(default=False, description="Whether window is currently minimized (iconic)")
    is_maximized: bool = Field(default=False, description="Whether window is maximized (zoomed)")
    window_bounds: BoundingBox = Field(..., description="Physical outer window bounding rectangle")
    client_bounds: BoundingBox = Field(..., description="Client area bounding rectangle")
    process_id: Optional[int] = Field(default=None, description="Process identifier (PID)")
    process_name: Optional[str] = Field(default=None, description="Executable process name e.g. 'notepad.exe'")


class ScreenshotObservation(BaseModel):
    """Live desktop visual frame capture."""

    capture_id: str = Field(default_factory=lambda: f"cap_{uuid4().hex[:8]}", description="Unique capture ID")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Capture timestamp")
    width: int = Field(..., ge=1, description="Desktop width in pixels")
    height: int = Field(..., ge=1, description="Desktop height in pixels")
    image_base64: Optional[str] = Field(default=None, description="Base64 encoded JPEG/PNG image string for vision models")
    capture_method: str = Field(default="DXGI", description="Capture adapter backend: DXGI, GDI, PIL, MOCK")
    format: str = Field(default="jpeg", description="Image format")
    raw_bytes: Optional[bytes] = Field(default=None, repr=False, description="Raw image byte buffer if retained in memory")


class OCRToken(BaseModel):
    """A discrete text token extracted from the live desktop by optical character recognition."""

    token_id: str = Field(default_factory=lambda: f"tok_{uuid4().hex[:8]}", description="Unique token ID")
    text: str = Field(..., description="Extracted text string")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="OCR confidence score")
    bounding_box: BoundingBox = Field(..., description="Physical bounding box on virtual desktop")
    source: str = Field(default="WINDOWS_OCR", description="OCR backend engine")


class UIElementObservation(BaseModel):
    """Accessibility element discovered via UI Automation or MSAA."""

    element_id: str = Field(default_factory=lambda: f"uia_{uuid4().hex[:8]}", description="Unique element ID")
    name: Optional[str] = Field(default=None, description="Accessible element label or name")
    control_type: Optional[str] = Field(default=None, description="UIA ControlType e.g. 'Button', 'Edit', 'Document'")
    automation_id: Optional[str] = Field(default=None, description="AutomationId property if present")
    class_name: Optional[str] = Field(default=None, description="Win32/UIA class name")
    is_enabled: bool = Field(default=True, description="Whether element is enabled for interaction")
    is_visible: bool = Field(default=True, description="Whether element is on-screen and visible")
    has_keyboard_focus: bool = Field(default=False, description="Whether element currently has keyboard focus")
    bounding_box: Optional[BoundingBox] = Field(default=None, description="Physical element bounding box")
    parent_context: Optional[str] = Field(default=None, description="Owning window title or parent control label")
    hwnd: Optional[int] = Field(default=None, description="Owning top-level window HWND")


class PerceptionEvidence(BaseModel):
    """Provenance and multi-channel confidence record for a perceived element."""

    evidence_sources: List[str] = Field(default_factory=list, description="Sources: WIN32, UIA, OCR, VISUAL, VISION_MODEL")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Fused confidence score")
    matched_tokens: List[str] = Field(default_factory=list, description="Matched OCR token texts")
    matched_uia_role: Optional[str] = Field(default=None, description="Matched UIA control type")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic evidence metadata")


class PerceivedElement(BaseModel):
    """A unified semantic UI element resulting from multi-modal perception fusion."""

    element_id: str = Field(default_factory=lambda: f"elem_{uuid4().hex[:8]}", description="Unique element ID")
    name: str = Field(..., description="Identified semantic label or name")
    role: str = Field(default="element", description="Identified UI role e.g. button, text_field, canvas, window")
    context: str = Field(default="", description="Surrounding application or window title")
    bounds: Optional[BoundingBox] = Field(default=None, description="Physical screen bounding box")
    evidence: PerceptionEvidence = Field(default_factory=PerceptionEvidence, description="Perception provenance")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall fused confidence")
    uia_element: Optional[UIElementObservation] = Field(default=None, description="Source UIA element if matched")
    ocr_tokens: List[OCRToken] = Field(default_factory=list, description="Associated OCR tokens")
    visual_region: Optional[VisualRegion] = Field(default=None, description="Associated visual region if matched")


class DesktopObservation(BaseModel):
    """The canonical, time-stamped live computer state snapshot provided to the Agent Execution Loop.

    SAFETY INVARIANT:
    Represents an immutable capture of the real desktop at a specific point in time.
    Fresh observations are captured before every decision cycle and immediately after actions.
    """

    observation_id: str = Field(default_factory=lambda: f"obs_{uuid4().hex[:8]}", description="Unique observation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Capture timestamp")
    screen_width: int = Field(default=1920, ge=1, description="Primary screen width in pixels")
    screen_height: int = Field(default=1080, ge=1, description="Primary screen height in pixels")

    foreground_window: Optional[WindowObservation] = Field(default=None, description="Active foreground window")
    visible_windows: List[WindowObservation] = Field(default_factory=list, description="All visible top-level windows")
    screenshot_reference: Optional[ScreenshotObservation] = Field(default=None, description="Visual frame screenshot")

    ocr_tokens: List[OCRToken] = Field(default_factory=list, description="Extracted OCR text tokens")
    uia_elements: List[UIElementObservation] = Field(default_factory=list, description="Accessibility element tree")
    visual_regions: List[VisualRegion] = Field(default_factory=list, description="Detected visual regions e.g. canvas")
    perceived_elements: List[PerceivedElement] = Field(default_factory=list, description="Fused semantic UI elements")
    focused_element: Optional[UIElementObservation] = Field(default=None, description="Currently focused UI control")

    desktop_summary: str = Field(default="", description="Concise structured summary formatted for LLM reasoning")
    canvas_status: Optional[str] = Field(default=None, description="Target canvas status: READY_FOR_DRAWING, MODIFIED, BLANK, UNKNOWN")

    # Modality acquisition status telemetry
    uia_status: str = Field(default="SUCCESS", description="UIA status: SUCCESS, EMPTY, UNAVAILABLE, FAILED")
    ocr_status: str = Field(default="SUCCESS", description="OCR status: SUCCESS, EMPTY, UNAVAILABLE, FAILED")
    screenshot_status: str = Field(default="SUCCESS", description="Screenshot status: SUCCESS, FALLBACK, FAILED")

    # Observation consistency & performance telemetry
    is_consistent: bool = Field(default=True, description="Whether observation maintained state consistency during capture")
    consistency_warnings: List[str] = Field(default_factory=list, description="Warnings if desktop state shifted during capture")
    capture_started_at: Optional[datetime] = Field(default=None, description="Timestamp when capture query started")
    capture_completed_at: Optional[datetime] = Field(default=None, description="Timestamp when capture query finished")
    capture_duration_ms: float = Field(default=0.0, ge=0.0, description="Total capture and fusion duration in milliseconds")
    capture_metadata: Dict[str, Any] = Field(default_factory=dict, description="Sensory backend diagnostic metadata")

    @property
    def active_window_title(self) -> Optional[str]:
        return self.foreground_window.title if self.foreground_window else None

    @property
    def active_window_hwnd(self) -> Optional[int]:
        return self.foreground_window.hwnd if self.foreground_window else None

    @property
    def target_app_exists(self) -> bool:
        return len(self.visible_windows) > 0

    @property
    def target_app_is_active(self) -> bool:
        return self.foreground_window is not None
