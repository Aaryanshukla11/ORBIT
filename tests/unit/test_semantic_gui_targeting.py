"""Automated test suite verifying Semantic GUI Targeting Integration (TEST 1 to TEST 7).

Tests:
1. TEST 1: UI Automation target is found and normalized correctly.
2. TEST 2: UI Automation fails and OCR fallback resolves the target.
3. TEST 3: Target found outside the expected window is rejected.
4. TEST 4: Multiple possible targets cause safe ambiguity handling.
5. TEST 5: Resolved rectangle produces a valid click point within bounds.
6. TEST 6: Target resolution failure causes task failure, never false completion.
7. TEST 7: Deterministic application launching / window targeting remains unaffected.
"""

from datetime import datetime, timezone
import pytest

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.execution.engine import ClosedLoopExecutionEngine
from orbit.runtime.execution.models import ExecutionPolicy, ExecutionState
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRWord,
)
from orbit.runtime.perception.ocr import MockOCRProvider
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetBoundingBox,
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
    calculate_safe_action_point,
)


def make_snapshot(
    generation_id: int = 1,
    windows=None,
    elements=None,
    foreground_window=None,
    is_stale: bool = False,
    telemetry=None,
) -> ObservationSnapshot:
    """Helper to construct deterministic observation snapshots."""
    fg = foreground_window
    if fg is None and windows:
        fg = next((w for w in windows if w.is_foreground), windows[0])

    return ObservationSnapshot(
        snapshot_id=f"snap_gen_{generation_id}",
        generation_id=generation_id,
        timestamp_ns=1000000,
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        windows=windows or [],
        foreground_window=fg,
        detected_elements=elements or [],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
        is_stale=is_stale,
        telemetry=telemetry or {},
    )


# ============================================================================
# TEST 1: UI Automation target is found and normalized correctly
# ============================================================================

def test_test1_ui_automation_semantic_digit_normalization():
    """TEST 1: Semantic query '7' resolves against UIA element with Name='Seven' or AutomationId='num7Button'."""
    calc_window = ObservedWindow(
        hwnd=1001,
        process_id=555,
        process_name="CalculatorApp.exe",
        window_title="Calculator",
        extended_bounds=BoundingBox(left=100, top=100, width=400, height=600),
        is_foreground=True,
        is_visible=True,
    )
    btn_seven = ObservedElement(
        element_id="el_num7",
        source="UI_AUTOMATION",
        name="Seven",
        role="Button",
        control_type="Button",
        automation_id="num7Button",
        bounds=BoundingBox(left=120, top=300, width=80, height=50),
        is_enabled=True,
        is_focused=False,
        is_offscreen=False,
    )
    snap = make_snapshot(windows=[calc_window], elements=[btn_seven])
    locator = EvidenceBasedTargetLocator()

    # Query with semantic digit "7"
    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="7",
        window_title="Calculator",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.bounding_box.left == 120
    assert res.target.bounding_box.top == 300
    assert res.target.bounding_box.right == 200
    assert res.target.bounding_box.bottom == 350
    assert res.target.evidence.source == "UI_AUTOMATION"
    assert res.target.target_hwnd == 1001
    assert res.target.confidence >= 0.95
    # Safe point is strictly inside button bounds
    assert 120 <= res.target.safe_point.x <= 200
    assert 300 <= res.target.safe_point.y <= 350


# ============================================================================
# TEST 2: UI Automation fails and OCR fallback resolves the target
# ============================================================================

def test_test2_uia_fails_and_ocr_fallback_resolves():
    """TEST 2: Accessibility elements list is empty; Tier 2 OCR fallback resolves the target."""
    win = ObservedWindow(
        hwnd=2002,
        process_id=666,
        process_name="custom_app.exe",
        window_title="Custom App",
        extended_bounds=BoundingBox(left=100, top=100, width=600, height=500),
        is_foreground=True,
        is_visible=True,
    )

    ocr_box = OCRBoundingBox(
        left=250,
        top=300,
        right=350,
        bottom=340,
        coordinate_space=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
    )
    ocr_word = OCRWord(
        text="Save",
        normalized_text="save",
        bounding_box=ocr_box,
        confidence=0.96,
    )
    ocr_region = OCRTextRegion(
        text="Save",
        normalized_text="save",
        bounding_box=ocr_box,
        words=[ocr_word],
        confidence=0.96,
        source_provider="WINDOWS_NATIVE_WINRT",
    )
    mock_ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        full_text="Save",
        observation_id="snap_gen_1",
        desktop_generation_id=1,
    )

    # Snapshot with NO accessibility elements, but with OCR evidence in telemetry
    snap = make_snapshot(
        generation_id=1,
        windows=[win],
        elements=[],
        telemetry={"ocr_result": mock_ocr_result},
    )

    ocr_provider = MockOCRProvider(injected_regions=[ocr_region])
    perception_engine = SemanticPerceptionEngine(ocr_provider=ocr_provider)
    locator = EvidenceBasedTargetLocator(perception_engine=perception_engine)

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="Save",
        window_title="Custom App",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.evidence.source == "OCR_TEXT"
    assert res.target.evidence.name == "Save"
    assert res.target.bounding_box.left == 250
    assert res.target.bounding_box.top == 300
    assert res.target.target_hwnd == 2002
    assert 250 <= res.target.safe_point.x <= 350
    assert 300 <= res.target.safe_point.y <= 340


# ============================================================================
# TEST 3: Target found outside the expected window is rejected
# ============================================================================

def test_test3_target_outside_expected_window_rejected():
    """TEST 3: Target element located outside target window bounds is rejected."""
    target_win = ObservedWindow(
        hwnd=3003,
        process_id=777,
        process_name="calc.exe",
        window_title="Calculator",
        extended_bounds=BoundingBox(left=100, top=100, width=300, height=400),
        is_foreground=True,
        is_visible=True,
    )
    # Element located at (800, 800) which is completely outside Calculator window (100..400, 100..500)
    outside_element = ObservedElement(
        element_id="el_outside",
        source="UI_AUTOMATION",
        name="Seven",
        role="Button",
        control_type="Button",
        automation_id="num7Button",
        bounds=BoundingBox(left=800, top=800, width=50, height=50),
        is_enabled=True,
    )
    snap = make_snapshot(windows=[target_win], elements=[outside_element])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="7",
        window_title="Calculator",
    )
    res = locator.locate_target(snap, intent)

    # Must NOT resolve the element outside the window
    assert res.status == TargetResolutionStatus.NOT_FOUND
    assert res.target is None


# ============================================================================
# TEST 4: Multiple possible targets cause safe ambiguity handling
# ============================================================================

def test_test4_multiple_targets_cause_ambiguity():
    """TEST 4: Multiple identical candidates within the window trigger AMBIGUOUS status."""
    win = ObservedWindow(
        hwnd=4004,
        process_id=888,
        process_name="app.exe",
        window_title="Duplicate App",
        extended_bounds=BoundingBox(left=50, top=50, width=800, height=600),
        is_foreground=True,
        is_visible=True,
    )
    btn_save_1 = ObservedElement(
        element_id="el_save_1",
        source="UI_AUTOMATION",
        name="Save",
        role="Button",
        control_type="Button",
        automation_id="btnSave1",
        bounds=BoundingBox(left=100, top=100, width=80, height=30),
        is_enabled=True,
    )
    btn_save_2 = ObservedElement(
        element_id="el_save_2",
        source="UI_AUTOMATION",
        name="Save",
        role="Button",
        control_type="Button",
        automation_id="btnSave2",
        bounds=BoundingBox(left=100, top=200, width=80, height=30),
        is_enabled=True,
    )
    snap = make_snapshot(windows=[win], elements=[btn_save_1, btn_save_2])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="Save",
        window_title="Duplicate App",
    )
    res = locator.locate_target(snap, intent)

    assert res.status == TargetResolutionStatus.AMBIGUOUS
    assert res.candidates_count == 2
    assert res.target is None
    assert "Ambiguous accessibility target" in res.diagnostic_message


# ============================================================================
# TEST 5: Resolved rectangle produces a valid click point
# ============================================================================

def test_test5_resolved_rectangle_produces_valid_click_point():
    """TEST 5: Click point derived from resolved bounding rectangle is strictly inside element and desktop bounds."""
    tbox = TargetBoundingBox(left=200, top=300, right=350, bottom=380)
    safe_pt = calculate_safe_action_point(tbox, desktop_generation_id=42)

    assert safe_pt.desktop_generation_id == 42
    assert 200 <= safe_pt.x < 350
    assert 300 <= safe_pt.y < 380
    # Strict center point calculation
    assert safe_pt.x == 200 + int((350 - 200 - 1) * 0.5)
    assert safe_pt.y == 300 + int((380 - 300 - 1) * 0.5)


# ============================================================================
# TEST 6: Target resolution failure causes task failure, never false completion
# ============================================================================

@pytest.mark.asyncio
async def test_test6_resolution_failure_causes_truthful_task_failure():
    """TEST 6: When target cannot be resolved, execution engine halts with FAILED state and truthful failure code."""
    snap = make_snapshot(elements=[])
    locator = EvidenceBasedTargetLocator()

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="NonExistentButton999",
    )

    class DummyObservationAdapter:
        async def capture_snapshot(self, target_hwnd=None):
            return snap

    engine = ClosedLoopExecutionEngine(
        observation=DummyObservationAdapter(),
        target_locator=locator,
    )

    policy = ExecutionPolicy(
        max_attempts=1,
        max_recoveries=0,
        retry_delay_seconds=0.01,
    )

    result = await engine.execute_task_action(
        session_id="test_sess",
        task_id="test_task",
        prompt="Click NonExistentButton999",
        target_intent=intent,
        policy=policy,
    )

    assert result.is_success is False
    assert result.final_state == ExecutionState.FAILED
    assert result.failure_code == "TARGET_NOT_FOUND"
    assert "Target resolution failed" in result.failure_reason


# ============================================================================
# TEST 7: Existing deterministic app launching remains unaffected
# ============================================================================

def test_test7_deterministic_window_resolution_unaffected():
    """TEST 7: Deterministic WINDOW_TITLE strategy resolves target window and HWND accurately."""
    notepad_win = ObservedWindow(
        hwnd=5005,
        process_id=999,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        extended_bounds=BoundingBox(left=150, top=150, width=700, height=500),
        is_foreground=True,
        is_visible=True,
    )
    calc_win = ObservedWindow(
        hwnd=6006,
        process_id=888,
        process_name="CalculatorApp.exe",
        window_title="Calculator",
        extended_bounds=BoundingBox(left=900, top=150, width=400, height=600),
        is_foreground=False,
        is_visible=True,
    )
    snap = make_snapshot(windows=[notepad_win, calc_win])
    locator = EvidenceBasedTargetLocator()

    # Query Notepad
    intent_notepad = TargetIntent(
        strategy=TargetStrategy.WINDOW_TITLE,
        window_title="Notepad",
    )
    res_notepad = locator.locate_target(snap, intent_notepad)

    assert res_notepad.status == TargetResolutionStatus.RESOLVED
    assert res_notepad.target is not None
    assert res_notepad.target.target_hwnd == 5005
    assert res_notepad.target.evidence.source == "WIN32_WINDOW"

    # Query Calculator
    intent_calc = TargetIntent(
        strategy=TargetStrategy.WINDOW_TITLE,
        window_title="Calculator",
    )
    res_calc = locator.locate_target(snap, intent_calc)

    assert res_calc.status == TargetResolutionStatus.RESOLVED
    assert res_calc.target is not None
    assert res_calc.target.target_hwnd == 6006
