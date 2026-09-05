"""Production domain models for UI and screen observation snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.models.common import BoundingBox, Resolution, ScreenPoint


class CoordinateSpace(str, Enum):
    """Reference coordinate system for bounding geometries."""

    PHYSICAL_PIXELS = "PHYSICAL_PIXELS"       # Native hardware monitor pixels
    VIRTUAL_DESKTOP = "VIRTUAL_DESKTOP"       # Unified desktop spanning all displays
    WINDOW_RELATIVE = "WINDOW_RELATIVE"       # Relative to top-left of target window
    LOGICAL_DIP = "LOGICAL_DIP"               # Device Independent Pixels (DPI scaled)


class FreshnessState(str, Enum):
    """Observation temporal freshness classification."""

    FRESH = "FRESH"       # Captured <250ms ago; high confidence
    AGING = "AGING"       # Captured 250-500ms ago; usable with caution
    STALE = "STALE"       # Captured >500ms ago or desktop changed; must recapture
    UNKNOWN = "UNKNOWN"   # Timestamp unavailable or invalid


class ObservationConfidence(str, Enum):
    """Multi-source evidence fusion confidence level."""

    CONFIRMED = "CONFIRMED"                     # Multi-provider spatial & semantic agreement
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED" # Single-source reliable accessibility element
    VISUAL_FALLBACK = "VISUAL_FALLBACK"         # Visual feature only without accessibility tree
    CONFLICTING = "CONFLICTING"                 # Spatial/semantic contradiction across providers
    LOW_CONFIDENCE = "LOW_CONFIDENCE"           # Low signal or occluded target
    UNAVAILABLE = "UNAVAILABLE"                 # Target not found or provider failed


class ObservedWindow(BaseModel):
    """Immutable record of a desktop top-level window."""

    hwnd: int = Field(..., description="Win32 Window Handle")
    process_id: int = Field(..., description="Owning Process ID")
    process_name: str = Field(..., description="Executable name e.g. notepad.exe")
    window_title: str = Field(default="", description="Window title text")
    extended_bounds: BoundingBox = Field(..., description="DWM extended frame physical bounds")
    is_foreground: bool = Field(default=False, description="Whether window currently has foreground focus")
    is_visible: bool = Field(default=True, description="Whether window is visible on desktop")
    dpi_scaling: float = Field(default=1.0, description="DPI scale factor e.g. 1.0, 1.25, 1.5, 2.0")


class ObservedElement(BaseModel):
    """Immutable record of an individual UI control or accessible element."""

    element_id: str = Field(..., description="Unique element identifier")
    source: str = Field(..., description="Evidence channel: WIN32_CONTROL, MSAA, UI_AUTOMATION, VISUAL")
    name: Optional[str] = Field(default=None, description="Accessible name if available")
    role: str = Field(default="Unknown", description="Accessible role e.g. push button, text, edit")
    control_type: str = Field(default="Unknown", description="UIA ControlType name e.g. Button, Edit")
    automation_id: Optional[str] = Field(default=None, description="AutomationId property if defined")
    class_name: Optional[str] = Field(default=None, description="Win32 window class name")
    bounds: BoundingBox = Field(..., description="Physical bounding box on virtual desktop")
    coordinate_space: CoordinateSpace = Field(default=CoordinateSpace.PHYSICAL_PIXELS)
    is_enabled: bool = Field(default=True)
    is_focused: bool = Field(default=False)
    is_offscreen: bool = Field(default=False)
    confidence: ObservationConfidence = Field(default=ObservationConfidence.PARTIALLY_CONFIRMED)


class ObservedTarget(BaseModel):
    """Fused UI target combining multi-source evidence channels."""

    target_id: str = Field(..., description="Unique target identifier")
    name: Optional[str] = Field(default=None)
    role: str = Field(default="Unknown")
    physical_bounds: BoundingBox = Field(..., description="Target physical bounding box on virtual desktop")
    window_relative_bounds: Optional[BoundingBox] = None
    is_visible: bool = Field(default=True)
    is_occluded: bool = Field(default=False)
    confidence: ObservationConfidence = Field(default=ObservationConfidence.CONFIRMED)
    provenance_sources: List[str] = Field(default_factory=list)
    contradiction_notes: Optional[str] = None


class ObservationSnapshot(BaseModel):
    """Complete desktop state capture frozen at a specific point in time."""

    snapshot_id: str = Field(..., description="Unique snapshot identifier")
    generation_id: int = Field(default=0, ge=0, description="Monotonic desktop state generation")
    timestamp_ns: int = Field(..., description="Monotonic timestamp in nanoseconds")
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    capture_duration_ms: float = Field(default=0.0, ge=0.0)
    desktop_geometry: BoundingBox = Field(..., description="Unified virtual screen bounding box")
    coordinate_space: CoordinateSpace = Field(default=CoordinateSpace.VIRTUAL_DESKTOP)
    foreground_window: Optional[ObservedWindow] = None
    windows: List[ObservedWindow] = Field(default_factory=list)
    detected_elements: List[ObservedElement] = Field(default_factory=list)
    detected_targets: List[ObservedTarget] = Field(default_factory=list)
    confidence: ObservationConfidence = Field(default=ObservationConfidence.CONFIRMED)
    freshness_state: FreshnessState = Field(default=FreshnessState.FRESH)
    is_stale: bool = Field(default=False)
    invalidation_reason: Optional[str] = None
    telemetry: Dict[str, Any] = Field(default_factory=dict)
