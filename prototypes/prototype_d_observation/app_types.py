"""
Core Data Types, Enums, and Contract Models for ORBIT Prototype D v1.3.1.
(Screen Observation & Evidence Fusion Engine)
Strictly enforces separation of ProviderStatus from ProviderErrorReason,
and maintains independent EvidenceSource channels.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, Optional, Dict, Any, List


# ----------------------------------------------------------------------
# 1. Core Enumerations
# ----------------------------------------------------------------------

class CoordinateFrame(str, Enum):
    """Coordinate reference frames."""
    PHYSICAL_PIXELS = "PHYSICAL_PIXELS"
    LOGICAL_DIP = "LOGICAL_DIP"
    VIRTUAL_DESKTOP = "VIRTUAL_DESKTOP"
    WINDOW_EXTENDED_FRAME = "WINDOW_EXTENDED_FRAME"
    CLIENT_COORDINATES = "CLIENT_COORDINATES"


class EvidenceSource(str, Enum):
    """Independent observation evidence channels."""
    WIN32_CONTROL = "WIN32_CONTROL"
    MSAA = "MSAA"
    UI_AUTOMATION = "UI_AUTOMATION"
    VISUAL_ANALYSIS = "VISUAL_ANALYSIS"
    OCR = "OCR"


class ProviderStatus(str, Enum):
    """Execution status of an observation provider."""
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"


class ProviderErrorReason(str, Enum):
    """Specific diagnostic reason when a provider fails or degrades."""
    NONE = "NONE"
    ACCESS_DENIED = "ACCESS_DENIED"
    UIPI_RESTRICTED = "UIPI_RESTRICTED"
    COM_FAILURE = "COM_FAILURE"
    INVALID_HWND = "INVALID_HWND"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_EXCEPTION = "PROVIDER_EXCEPTION"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(str, Enum):
    """Multi-source fused target confidence classifications."""
    CONFIRMED = "CONFIRMED"
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
    VISUAL_FALLBACK = "VISUAL_FALLBACK"
    CONFLICTING = "CONFLICTING"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class InvalidationReason(str, Enum):
    """Physical desktop state triggers that invalidate existing observation snapshots."""
    NONE = "NONE"
    TTL_EXPIRED = "TTL_EXPIRED"
    FOREGROUND_CHANGED = "FOREGROUND_CHANGED"
    WINDOW_MOVED_OR_RESIZED = "WINDOW_MOVED_OR_RESIZED"
    WINDOW_MINIMIZED_OR_HIDDEN = "WINDOW_MINIMIZED_OR_HIDDEN"
    TARGET_DESTROYED = "TARGET_DESTROYED"
    USER_TAKEOVER = "USER_TAKEOVER"
    DISPLAY_TOPOLOGY_CHANGED = "DISPLAY_TOPOLOGY_CHANGED"


class ProviderHealthState(str, Enum):
    """Circuit breaker health states for accessibility worker threads."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    QUARANTINED = "QUARANTINED"
    RECOVERING = "RECOVERING"


class WorkerLifecycleState(str, Enum):
    """Explicit lifecycle states for native provider workers."""
    WORKER_STARTED = "WORKER_STARTED"
    TIMEOUT_WAITING_FOR_RESULT = "TIMEOUT_WAITING_FOR_RESULT"
    ABANDONED_RESULT = "ABANDONED_RESULT"
    WORKER_STILL_ACTIVE = "WORKER_STILL_ACTIVE"
    WORKER_EXIT_CONFIRMED = "WORKER_EXIT_CONFIRMED"


class OcclusionState(str, Enum):
    """Distinguishes geometric overlap from screen-confirmed visual occlusion."""
    NOT_OCCLUDED = "NOT_OCCLUDED"
    GEOMETRIC_OVERLAP = "GEOMETRIC_OVERLAP"
    OBSERVED_PIXEL_CHANGE = "OBSERVED_PIXEL_CHANGE"
    OBSERVED_VISUAL_OCCLUSION = "OBSERVED_VISUAL_OCCLUSION"
    CONFLICTING = "CONFLICTING"


# ----------------------------------------------------------------------
# 2. Geometry & Bounding Primitives
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Rect:
    """Inclusive-exclusive physical pixel bounding rectangle."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def contains(self, other: "Rect") -> bool:
        """Returns True if self completely contains other."""
        return (self.left <= other.left and self.top <= other.top and
                self.right >= other.right and self.bottom >= other.bottom)

    def intersects(self, other: "Rect") -> bool:
        """Returns True if self intersects with other."""
        return not (self.right <= other.left or self.left >= other.right or
                    self.bottom <= other.top or self.top >= other.bottom)

    def intersection(self, other: "Rect") -> Optional["Rect"]:
        """Calculates intersecting sub-rectangle."""
        if not self.intersects(other):
            return None
        return Rect(
            left=max(self.left, other.left),
            top=max(self.top, other.top),
            right=min(self.right, other.right),
            bottom=min(self.bottom, other.bottom)
        )

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


# ----------------------------------------------------------------------
# 3. Observation Evidence Data Structures
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class WindowObservation:
    """Immutable record of a desktop top-level window."""
    hwnd: int
    process_id: int
    process_name: str
    window_title: str
    extended_bounds: Rect
    client_bounds: Rect
    is_visible: bool
    is_minimized: bool
    is_maximized: bool
    is_foreground: bool
    z_order_rank: int
    dpi_scaling: float = 1.0


@dataclass(frozen=True)
class UIElementObservation:
    """Immutable record of a control or accessible element."""
    element_id: str
    evidence_source: str  # WIN32_CONTROL, MSAA, UI_AUTOMATION
    name: Optional[str]
    role: str
    control_type: str
    automation_id: Optional[str]
    bounds: Rect
    is_enabled: bool
    is_focused: bool
    is_offscreen: bool
    timestamp_ns: int
    generation_id: int
    confidence: ConfidenceLevel = ConfidenceLevel.PARTIALLY_CONFIRMED
    class_name: Optional[str] = None
    native_hwnd: Optional[int] = None


@dataclass(frozen=True)
class VisualFeatureObservation:
    """Immutable record of a regional visual feature extracted from screenshot."""
    feature_id: str
    bounds: Rect
    detected_text: Optional[str]
    ocr_confidence: float
    perceptual_hash: str
    color_variance: float
    contrast_ratio: float
    timestamp_ns: int
    generation_id: int


@dataclass(frozen=True)
class ProviderResult:
    """Standardized output from an independent observation provider."""
    provider_name: str
    status: ProviderStatus
    error_reason: ProviderErrorReason
    elements: Tuple[UIElementObservation, ...]
    is_partial: bool
    duration_ms: float
    timeout_occurred: bool
    error_message: Optional[str] = None
    worker_state: str = "WORKER_EXIT_CONFIRMED"


@dataclass(frozen=True)
class DetectedTarget:
    """Multi-source fused target ready for downstream consumption."""
    target_id: str
    name: Optional[str]
    role: str
    physical_bounds: Rect
    window_relative_bounds: Rect
    is_visible_on_screen: bool
    is_occluded: bool
    spatial_agreement_iou: float
    semantic_agreement_match: bool
    confidence: ConfidenceLevel
    provenance_sources: Tuple[str, ...]
    contradiction_notes: Optional[str] = None
    occlusion_state: OcclusionState = OcclusionState.NOT_OCCLUDED


@dataclass(frozen=True)
class ObservationSnapshot:
    """Complete desktop state capture frozen at a specific point in time."""
    generation_id: int
    timestamp_ns: int
    capture_duration_ms: float
    desktop_geometry: Rect
    foreground_window: Optional[WindowObservation]
    windows: Tuple[WindowObservation, ...]
    visual_evidence: Tuple[VisualFeatureObservation, ...]
    accessibility_evidence: Tuple[UIElementObservation, ...]
    detected_targets: Tuple[DetectedTarget, ...]
    confidence: ConfidenceLevel
    conflicts: Tuple[str, ...]
    invalidation_state: InvalidationReason = InvalidationReason.NONE
    is_stale: bool = False
    telemetry: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerLifecycleRecord:
    """Diagnostics for a single provider worker thread."""
    provider_name: str
    worker_started_ns: int
    worker_timeout_declared_ns: Optional[int] = None
    worker_abandoned_ns: Optional[int] = None
    worker_still_active: bool = True
    worker_exit_confirmed: bool = False
    worker_exit_after_timeout_ns: Optional[int] = None
    provider_quarantine_entered_ns: Optional[int] = None
    provider_quarantine_released_ns: Optional[int] = None


# ----------------------------------------------------------------------
# 4. Standard UI Automation Control Type ID Mapping
# ----------------------------------------------------------------------

UIA_CONTROL_TYPE_NAMES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
    50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator",
}
