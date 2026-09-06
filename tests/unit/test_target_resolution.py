"""Unit tests for semantic target resolution, safe action points, and locator strategies."""

import pytest
from datetime import datetime, timezone

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetBoundingBox,
    TargetIntent,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetStrategy,
    calculate_safe_action_point,
)


def make_test_snapshot(
    is_stale: bool = False,
    generation_id: int = 1,
    windows=None,
    elements=None,
) -> ObservationSnapshot:
    return ObservationSnapshot(
        snapshot_id="snap_test_01",
        generation_id=generation_id,
        timestamp_ns=1000000,
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=10.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        windows=windows or [],
        detected_elements=elements or [],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
        is_stale=is_stale,
    )


# ============================================================================
# 1. Safe Action Point Tests
# ============================================================================

def test_safe_action_point_deterministic_interior():
    tbox = TargetBoundingBox(left=100, top=200, right=300, bottom=400)
    pt = calculate_safe_action_point(tbox, desktop_generation_id=5)

    assert pt.desktop_generation_id == 5
    assert tbox.left <= pt.x < tbox.right
    assert tbox.top <= pt.y < tbox.bottom
    # Center point for 200x200 box: 100 + int(199*0.5) = 199
    assert pt.x == 199
    assert pt.y == 299


def test_safe_action_point_zero_area_rejected():
    # Width 0
    tbox = TargetBoundingBox(left=100, top=100, right=100, bottom=200)
    with pytest.raises(ValueError, match="strictly positive dimensions"):
        calculate_safe_action_point(tbox, desktop_generation_id=1)

    # Height 0
    tbox2 = TargetBoundingBox(left=100, top=100, right=200, bottom=100)
    with pytest.raises(ValueError, match="strictly positive dimensions"):
        calculate_safe_action_point(tbox2, desktop_generation_id=1)


def test_safe_action_point_inverted_bounds_rejected():
    tbox = TargetBoundingBox(left=300, top=400, right=100, bottom=200)
    with pytest.raises(ValueError, match="strictly positive dimensions"):
        calculate_safe_action_point(tbox, desktop_generation_id=1)


def test_safe_action_point_out_of_integer_bounds_rejected():
    tbox = TargetBoundingBox(left=32760, top=32760, right=32780, bottom=32780)
    with pytest.raises(ValueError, match="exceeds Win32 integer bounds"):
        calculate_safe_action_point(tbox, desktop_generation_id=1)


# ============================================================================
# 2. Target Locator Tests
# ============================================================================

def test_target_resolution_accessibility_element_success():
    element = ObservedElement(
        element_id="el_btn_submit",
        source="UI_AUTOMATION",
        name="Submit Form",
        role="Button",
        control_type="Button",
        automation_id="btn_submit_id",
        bounds=BoundingBox(left=500, top=400, width=120, height=40),
        is_enabled=True,
        is_focused=False,
        is_offscreen=False,
    )
    snap = make_test_snapshot(elements=[element])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="Submit Form",
        role="Button",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.evidence.name == "Submit Form"
    assert res.target.evidence.source == "UI_AUTOMATION"
    assert res.target.safe_point.x >= 500
    assert res.target.safe_point.y >= 400
    assert res.target.desktop_generation_id == snap.generation_id


def test_target_resolution_missing_target_returns_not_found():
    snap = make_test_snapshot(elements=[])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="NonExistentControl",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.NOT_FOUND
    assert res.candidates_count == 0
    assert res.target is None


def test_target_resolution_ambiguous_target_returns_ambiguous():
    el1 = ObservedElement(
        element_id="el_1",
        source="UI_AUTOMATION",
        name="Save",
        role="Button",
        control_type="Button",
        bounds=BoundingBox(left=100, top=100, width=80, height=30),
        is_enabled=True,
    )
    el2 = ObservedElement(
        element_id="el_2",
        source="UI_AUTOMATION",
        name="Save",
        role="Button",
        control_type="Button",
        bounds=BoundingBox(left=300, top=100, width=80, height=30),
        is_enabled=True,
    )
    snap = make_test_snapshot(elements=[el1, el2])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="Save",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.AMBIGUOUS
    assert res.candidates_count == 2
    assert res.target is None


def test_target_resolution_window_title_success():
    win = ObservedWindow(
        hwnd=12345,
        process_id=999,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        extended_bounds=BoundingBox(left=200, top=150, width=800, height=600),
        is_foreground=True,
        is_visible=True,
    )
    snap = make_test_snapshot(windows=[win])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.WINDOW_TITLE,
        window_title="Notepad",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.target_hwnd == 12345
    assert res.target.evidence.source == "WIN32_WINDOW"


def test_target_resolution_stale_observation_fails_closed():
    element = ObservedElement(
        element_id="el_btn",
        source="UI_AUTOMATION",
        name="OK",
        role="Button",
        control_type="Button",
        bounds=BoundingBox(left=100, top=100, width=50, height=25),
    )
    snap = make_test_snapshot(is_stale=True, elements=[element])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="OK",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.STALE_OBSERVATION
    assert res.is_stale_observation is True
    assert res.target is None


def test_target_resolution_visual_semantic_without_template_fails_closed():
    snap = make_test_snapshot()
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        name="blue search icon",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.INVALID_REQUEST
    assert "requires a valid visualtemplate" in res.diagnostic_message.lower()
    assert res.target is None


def test_target_resolution_coordinate_region_success():
    snap = make_test_snapshot()
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.COORDINATE_REGION,
        explicit_bounds=BoundingBox(left=400, top=300, width=200, height=100),
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.safe_point.x == 400 + int(199 * 0.5)
    assert res.target.safe_point.y == 300 + int(99 * 0.5)
