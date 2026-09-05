"""Data translation and model mapping from Prototype D to production ORBIT contracts."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, List, Optional

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedTarget,
    ObservedWindow,
)
from orbit.models.common import BoundingBox

logger = logging.getLogger(__name__)


def map_rect_to_bounding_box(rect: Any) -> BoundingBox:
    """Convert a Prototype D Rect or rect-like object to a production BoundingBox."""
    if rect is None:
        raise ValueError("Cannot map None rect to BoundingBox")

    left = int(getattr(rect, "left", 0))
    top = int(getattr(rect, "top", 0))
    right = int(getattr(rect, "right", left))
    bottom = int(getattr(rect, "bottom", top))

    width = max(1, right - left)
    height = max(1, bottom - top)

    return BoundingBox(left=left, top=top, width=width, height=height)


def map_confidence_level(proto_conf: Any) -> ObservationConfidence:
    """Map Prototype D ConfidenceLevel to production ObservationConfidence."""
    if proto_conf is None:
        return ObservationConfidence.UNAVAILABLE

    conf_str = str(getattr(proto_conf, "value", proto_conf)).upper()
    mapping = {
        "CONFIRMED": ObservationConfidence.CONFIRMED,
        "PARTIALLY_CONFIRMED": ObservationConfidence.PARTIALLY_CONFIRMED,
        "VISUAL_FALLBACK": ObservationConfidence.VISUAL_FALLBACK,
        "CONFLICTING": ObservationConfidence.CONFLICTING,
        "LOW_CONFIDENCE": ObservationConfidence.LOW_CONFIDENCE,
        "STALE": ObservationConfidence.LOW_CONFIDENCE,
        "UNAVAILABLE": ObservationConfidence.UNAVAILABLE,
    }
    return mapping.get(conf_str, ObservationConfidence.LOW_CONFIDENCE)


def map_window_observation(win: Any) -> Optional[ObservedWindow]:
    """Map Prototype D WindowObservation to production ObservedWindow."""
    if win is None:
        return None

    try:
        ext_bounds = map_rect_to_bounding_box(getattr(win, "extended_bounds", None))
        return ObservedWindow(
            hwnd=int(getattr(win, "hwnd", 0)),
            process_id=int(getattr(win, "process_id", 0)),
            process_name=str(getattr(win, "process_name", "unknown.exe")),
            window_title=str(getattr(win, "window_title", "")),
            extended_bounds=ext_bounds,
            is_foreground=bool(getattr(win, "is_foreground", False)),
            is_visible=bool(getattr(win, "is_visible", True)),
            dpi_scaling=float(getattr(win, "dpi_scaling", 1.0)),
        )
    except Exception as ex:
        logger.warning("Failed to map WindowObservation: %s", ex)
        return None


def map_ui_element(elem: Any) -> Optional[ObservedElement]:
    """Map Prototype D UIElementObservation to production ObservedElement."""
    if elem is None:
        return None

    try:
        bounds = map_rect_to_bounding_box(getattr(elem, "bounds", None))
        name = getattr(elem, "name", None)
        auto_id = getattr(elem, "automation_id", None)
        class_name = getattr(elem, "class_name", None)

        return ObservedElement(
            element_id=str(getattr(elem, "element_id", "")),
            source=str(getattr(elem, "evidence_source", "UNKNOWN")),
            name=str(name) if name is not None else None,
            role=str(getattr(elem, "role", "Unknown")),
            control_type=str(getattr(elem, "control_type", "Unknown")),
            automation_id=str(auto_id) if auto_id is not None else None,
            class_name=str(class_name) if class_name is not None else None,
            bounds=bounds,
            coordinate_space=CoordinateSpace.PHYSICAL_PIXELS,
            is_enabled=bool(getattr(elem, "is_enabled", True)),
            is_focused=bool(getattr(elem, "is_focused", False)),
            is_offscreen=bool(getattr(elem, "is_offscreen", False)),
            confidence=map_confidence_level(getattr(elem, "confidence", None)),
        )
    except Exception as ex:
        logger.warning("Failed to map UIElementObservation: %s", ex)
        return None


def map_detected_target(target: Any) -> Optional[ObservedTarget]:
    """Map Prototype D DetectedTarget to production ObservedTarget."""
    if target is None:
        return None

    try:
        phys_bounds = map_rect_to_bounding_box(getattr(target, "physical_bounds", None))
        win_rel = getattr(target, "window_relative_bounds", None)
        win_rel_bounds = map_rect_to_bounding_box(win_rel) if win_rel else None
        name = getattr(target, "name", None)

        return ObservedTarget(
            target_id=str(getattr(target, "target_id", "")),
            name=str(name) if name is not None else None,
            role=str(getattr(target, "role", "Unknown")),
            physical_bounds=phys_bounds,
            window_relative_bounds=win_rel_bounds,
            is_visible=bool(getattr(target, "is_visible_on_screen", True)),
            is_occluded=bool(getattr(target, "is_occluded", False)),
            confidence=map_confidence_level(getattr(target, "confidence", None)),
            provenance_sources=list(getattr(target, "provenance_sources", [])),
            contradiction_notes=getattr(target, "contradiction_notes", None),
        )
    except Exception as ex:
        logger.warning("Failed to map DetectedTarget: %s", ex)
        return None


def map_prototype_snapshot(proto_snap: Any, snapshot_id: str) -> ObservationSnapshot:
    """Map full Prototype D ObservationSnapshot to production ObservationSnapshot."""
    if proto_snap is None:
        raise ValueError("Cannot map None prototype snapshot")

    desktop_geo = map_rect_to_bounding_box(getattr(proto_snap, "desktop_geometry", None))
    fg_win = map_window_observation(getattr(proto_snap, "foreground_window", None))

    mapped_windows: List[ObservedWindow] = []
    for w in getattr(proto_snap, "windows", ()):
        mw = map_window_observation(w)
        if mw:
            mapped_windows.append(mw)

    mapped_elements: List[ObservedElement] = []
    for e in getattr(proto_snap, "accessibility_evidence", ()):
        me = map_ui_element(e)
        if me:
            mapped_elements.append(me)

    mapped_targets: List[ObservedTarget] = []
    for t in getattr(proto_snap, "detected_targets", ()):
        mt = map_detected_target(t)
        if mt:
            mapped_targets.append(mt)

    return ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=int(getattr(proto_snap, "generation_id", 0)),
        timestamp_ns=int(getattr(proto_snap, "timestamp_ns", 0)),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=float(getattr(proto_snap, "capture_duration_ms", 0.0)),
        desktop_geometry=desktop_geo,
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        foreground_window=fg_win,
        windows=mapped_windows,
        detected_elements=mapped_elements,
        detected_targets=mapped_targets,
        confidence=map_confidence_level(getattr(proto_snap, "confidence", None)),
        freshness_state=FreshnessState.FRESH,
        is_stale=bool(getattr(proto_snap, "is_stale", False)),
        invalidation_reason=str(getattr(proto_snap, "invalidation_state", "NONE")),
        telemetry=dict(getattr(proto_snap, "telemetry", {})),
    )
