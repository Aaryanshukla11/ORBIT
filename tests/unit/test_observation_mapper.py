"""Unit tests for Prototype D to production ORBIT model mapper."""

import time
import pytest

from orbit.adapters.observation.mapper import (
    map_confidence_level,
    map_detected_target,
    map_prototype_snapshot,
    map_rect_to_bounding_box,
    map_ui_element,
    map_window_observation,
)
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
)
from prototypes.prototype_d_observation.app_types import (
    ConfidenceLevel,
    DetectedTarget,
    InvalidationReason,
    ObservationSnapshot as ProtoSnapshot,
    Rect,
    UIElementObservation,
    WindowObservation,
)


def test_map_rect_to_bounding_box():
    rect = Rect(left=100, top=200, right=500, bottom=600)
    bbox = map_rect_to_bounding_box(rect)
    assert bbox.left == 100
    assert bbox.top == 200
    assert bbox.width == 400
    assert bbox.height == 400
    assert bbox.right == 500
    assert bbox.bottom == 600


def test_map_confidence_level():
    assert map_confidence_level(ConfidenceLevel.CONFIRMED) == ObservationConfidence.CONFIRMED
    assert map_confidence_level(ConfidenceLevel.PARTIALLY_CONFIRMED) == ObservationConfidence.PARTIALLY_CONFIRMED
    assert map_confidence_level(ConfidenceLevel.VISUAL_FALLBACK) == ObservationConfidence.VISUAL_FALLBACK
    assert map_confidence_level(ConfidenceLevel.CONFLICTING) == ObservationConfidence.CONFLICTING
    assert map_confidence_level(ConfidenceLevel.UNAVAILABLE) == ObservationConfidence.UNAVAILABLE
    assert map_confidence_level(None) == ObservationConfidence.UNAVAILABLE


def test_map_window_observation():
    proto_win = WindowObservation(
        hwnd=0x1234,
        process_id=5678,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        extended_bounds=Rect(100, 100, 900, 700),
        client_bounds=Rect(108, 130, 892, 692),
        is_visible=True,
        is_minimized=False,
        is_maximized=False,
        is_foreground=True,
        z_order_rank=1,
        dpi_scaling=1.25,
    )
    mapped = map_window_observation(proto_win)
    assert mapped is not None
    assert mapped.hwnd == 0x1234
    assert mapped.process_id == 5678
    assert mapped.process_name == "notepad.exe"
    assert mapped.window_title == "Untitled - Notepad"
    assert mapped.extended_bounds.width == 800
    assert mapped.extended_bounds.height == 600
    assert mapped.is_foreground is True
    assert mapped.dpi_scaling == 1.25


def test_map_ui_element_missing_fields_preserved():
    proto_elem = UIElementObservation(
        element_id="elem_001",
        evidence_source="UI_AUTOMATION",
        name=None,  # Intentionally None
        role="button",
        control_type="Button",
        automation_id=None,  # Intentionally None
        bounds=Rect(200, 300, 300, 340),
        is_enabled=True,
        is_focused=False,
        is_offscreen=False,
        timestamp_ns=time.perf_counter_ns(),
        generation_id=1,
        confidence=ConfidenceLevel.CONFIRMED,
        class_name=None,
    )
    mapped = map_ui_element(proto_elem)
    assert mapped is not None
    assert mapped.element_id == "elem_001"
    assert mapped.name is None  # Epistemic honesty: missing field preserved
    assert mapped.automation_id is None
    assert mapped.class_name is None
    assert mapped.bounds.width == 100
    assert mapped.bounds.height == 40
    assert mapped.coordinate_space == CoordinateSpace.PHYSICAL_PIXELS
    assert mapped.confidence == ObservationConfidence.CONFIRMED


def test_map_detected_target():
    proto_target = DetectedTarget(
        target_id="target_btn",
        name="Submit",
        role="Button",
        physical_bounds=Rect(400, 500, 520, 540),
        window_relative_bounds=Rect(50, 60, 170, 100),
        is_visible_on_screen=True,
        is_occluded=False,
        spatial_agreement_iou=0.95,
        semantic_agreement_match=True,
        confidence=ConfidenceLevel.CONFIRMED,
        provenance_sources=("MSAA", "UI_AUTOMATION"),
        contradiction_notes=None,
    )
    mapped = map_detected_target(proto_target)
    assert mapped is not None
    assert mapped.target_id == "target_btn"
    assert mapped.name == "Submit"
    assert mapped.physical_bounds.width == 120
    assert mapped.physical_bounds.height == 40
    assert mapped.window_relative_bounds is not None
    assert mapped.window_relative_bounds.width == 120
    assert mapped.provenance_sources == ["MSAA", "UI_AUTOMATION"]


def test_map_full_prototype_snapshot():
    proto_snap = ProtoSnapshot(
        generation_id=42,
        timestamp_ns=time.perf_counter_ns(),
        capture_duration_ms=18.5,
        desktop_geometry=Rect(0, 0, 1920, 1080),
        foreground_window=WindowObservation(
            hwnd=0x999,
            process_id=111,
            process_name="code.exe",
            window_title="ORBIT",
            extended_bounds=Rect(0, 0, 1920, 1080),
            client_bounds=Rect(0, 0, 1920, 1080),
            is_visible=True,
            is_minimized=False,
            is_maximized=True,
            is_foreground=True,
            z_order_rank=1,
        ),
        windows=(),
        visual_evidence=(),
        accessibility_evidence=(),
        detected_targets=(),
        confidence=ConfidenceLevel.CONFIRMED,
        conflicts=(),
        invalidation_state=InvalidationReason.NONE,
        is_stale=False,
        telemetry={"provider": "PrototypeD"},
    )
    mapped = map_prototype_snapshot(proto_snap, snapshot_id="snap_test_001")
    assert mapped.snapshot_id == "snap_test_001"
    assert mapped.generation_id == 42
    assert mapped.capture_duration_ms == 18.5
    assert mapped.desktop_geometry.width == 1920
    assert mapped.desktop_geometry.height == 1080
    assert mapped.foreground_window is not None
    assert mapped.foreground_window.process_name == "code.exe"
    assert mapped.telemetry["provider"] == "PrototypeD"
