"""Production domain models for UI and screen observation snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
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
    client_bounds: Optional[BoundingBox] = Field(default=None, description="Client area physical bounds")


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

    @classmethod
    def from_desktop_observation(cls, obs: Any) -> ObservationSnapshot:
        """Construct an ObservationSnapshot from a canonical DesktopObservation."""
        windows: List[ObservedWindow] = []
        for w in getattr(obs, "visible_windows", []):
            if isinstance(w, dict):
                hwnd = w.get("hwnd", 0)
                pid = w.get("process_id", 0) or 0
                pname = w.get("process_name", "") or ""
                wtitle = w.get("title", "") or w.get("window_title", "") or ""
                wb_raw = w.get("window_bounds")
                wb = wb_raw if (wb_raw and hasattr(wb_raw, "width") and wb_raw.width > 0) else BoundingBox(left=0, top=0, width=1920, height=1080)
                is_fg = w.get("is_foreground", False)
                is_vis = w.get("is_visible", True)
                cb_raw = w.get("client_bounds")
                cb = cb_raw if (cb_raw and hasattr(cb_raw, "width") and cb_raw.width > 0) else None
            else:
                hwnd = getattr(w, "hwnd", 0)
                pid = getattr(w, "process_id", 0) or 0
                pname = getattr(w, "process_name", "") or ""
                wtitle = getattr(w, "title", "") or getattr(w, "window_title", "") or ""
                wb = w.window_bounds if (hasattr(w, "window_bounds") and w.window_bounds and w.window_bounds.width > 0 and w.window_bounds.height > 0) else BoundingBox(left=0, top=0, width=1920, height=1080)
                is_fg = getattr(w, "is_foreground", False)
                is_vis = getattr(w, "is_visible", True)
                cb = w.client_bounds if (hasattr(w, "client_bounds") and w.client_bounds and w.client_bounds.width > 0 and w.client_bounds.height > 0) else None

            windows.append(
                ObservedWindow(
                    hwnd=hwnd,
                    process_id=pid,
                    process_name=pname,
                    window_title=wtitle,
                    extended_bounds=wb,
                    is_foreground=is_fg,
                    is_visible=is_vis,
                    dpi_scaling=1.0,
                    client_bounds=cb,
                )
            )

        fg_win: Optional[ObservedWindow] = None
        fg_obs = getattr(obs, "foreground_window", None)
        if fg_obs:
            if isinstance(fg_obs, dict):
                hwnd = fg_obs.get("hwnd", 0)
                pid = fg_obs.get("process_id", 0) or 0
                pname = fg_obs.get("process_name", "") or ""
                wtitle = fg_obs.get("title", "") or fg_obs.get("window_title", "") or ""
                wb_raw = fg_obs.get("window_bounds")
                wb = wb_raw if (wb_raw and hasattr(wb_raw, "width") and wb_raw.width > 0) else BoundingBox(left=0, top=0, width=1920, height=1080)
                is_vis = fg_obs.get("is_visible", True)
                cb_raw = fg_obs.get("client_bounds")
                cb = cb_raw if (cb_raw and hasattr(cb_raw, "width") and cb_raw.width > 0) else None
            else:
                hwnd = getattr(fg_obs, "hwnd", 0)
                pid = getattr(fg_obs, "process_id", 0) or 0
                pname = getattr(fg_obs, "process_name", "") or ""
                wtitle = getattr(fg_obs, "title", "") or getattr(fg_obs, "window_title", "") or ""
                wb = fg_obs.window_bounds if (hasattr(fg_obs, "window_bounds") and fg_obs.window_bounds and fg_obs.window_bounds.width > 0 and fg_obs.window_bounds.height > 0) else BoundingBox(left=0, top=0, width=1920, height=1080)
                is_vis = getattr(fg_obs, "is_visible", True)
                cb = fg_obs.client_bounds if (hasattr(fg_obs, "client_bounds") and fg_obs.client_bounds and fg_obs.client_bounds.width > 0 and fg_obs.client_bounds.height > 0) else None

            fg_win = ObservedWindow(
                hwnd=hwnd,
                process_id=pid,
                process_name=pname,
                window_title=wtitle,
                extended_bounds=wb,
                is_foreground=True,
                is_visible=is_vis,
                dpi_scaling=1.0,
                client_bounds=cb,
            )

        elements: List[ObservedElement] = []
        for e in getattr(obs, "uia_elements", []):
            if isinstance(e, dict):
                el_id = e.get("element_id", f"el_{uuid4().hex[:6]}")
                ename = e.get("name")
                erole = e.get("role") or e.get("control_type") or "Unknown"
                ectype = e.get("control_type") or "Unknown"
                eautoid = e.get("automation_id")
                ecls = e.get("class_name")
                eb_raw = e.get("bounding_box")
                eb = eb_raw if (eb_raw and hasattr(eb_raw, "width") and eb_raw.width > 0) else BoundingBox(left=0, top=0, width=1, height=1)
                e_en = e.get("is_enabled", True)
                e_foc = e.get("is_focused", False)
                e_vis = e.get("is_visible", True)
            else:
                el_id = getattr(e, "element_id", f"el_{uuid4().hex[:6]}")
                ename = getattr(e, "name", None)
                erole = getattr(e, "control_type", "Unknown") or "Unknown"
                ectype = getattr(e, "control_type", "Unknown") or "Unknown"
                eautoid = getattr(e, "automation_id", None)
                ecls = getattr(e, "class_name", None)
                eb = e.bounding_box if (hasattr(e, "bounding_box") and e.bounding_box and e.bounding_box.width > 0 and e.bounding_box.height > 0) else BoundingBox(left=0, top=0, width=1, height=1)
                e_en = getattr(e, "is_enabled", True)
                e_foc = getattr(e, "has_keyboard_focus", False)
                e_vis = getattr(e, "is_visible", True)

            elements.append(
                ObservedElement(
                    element_id=el_id,
                    source="UI_AUTOMATION",
                    name=ename,
                    role=erole,
                    control_type=ectype,
                    automation_id=eautoid,
                    class_name=ecls,
                    bounds=eb,
                    is_enabled=e_en,
                    is_focused=e_foc,
                    is_offscreen=not e_vis,
                    confidence=ObservationConfidence.CONFIRMED,
                )
            )

        sw = getattr(obs, "screen_width", 1920) or 1920
        sh = getattr(obs, "screen_height", 1080) or 1080
        ts = getattr(obs, "timestamp", datetime.now(timezone.utc))
        obs_id = getattr(obs, "observation_id", f"obs_{uuid4().hex[:8]}")
        dur = getattr(obs, "capture_duration_ms", 0.0)

        return cls(
            snapshot_id=obs_id,
            generation_id=1,
            timestamp_ns=int(ts.timestamp() * 1e9),
            timestamp_utc=ts,
            capture_duration_ms=dur,
            desktop_geometry=BoundingBox(left=0, top=0, width=sw, height=sh),
            coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
            foreground_window=fg_win,
            windows=windows,
            detected_elements=elements,
            confidence=ObservationConfidence.CONFIRMED,
            freshness_state=FreshnessState.FRESH,
            is_stale=False,
            telemetry={"is_consistent": getattr(obs, "is_consistent", True)},
        )
