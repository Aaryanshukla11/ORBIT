"""Unit tests for ORBIT M1.6 Step 2: Post-Action Verification Engine."""

from datetime import datetime, timezone
import pytest
import time

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.models.common import BoundingBox
from orbit.runtime.verification import (
    ActionVerificationResult,
    ActionVerifier,
    ExpectedOutcome,
    ExpectedOutcomeType,
    VerificationOutcome,
    VerificationStrategy,
)


def _make_window(
    hwnd: int,
    title: str = "",
    class_name: str = "TestClass",
    process_id: int = 1234,
    process_name: str = "test.exe",
    bounds: BoundingBox = BoundingBox(left=0, top=0, width=800, height=600),
    is_foreground: bool = False,
    is_visible: bool = True,
) -> ObservedWindow:
    return ObservedWindow(
        hwnd=hwnd,
        process_id=process_id,
        process_name=process_name,
        window_title=title,
        extended_bounds=bounds,
        is_foreground=is_foreground,
        is_visible=is_visible,
        dpi_scaling=1.0,
    )


def _make_snapshot(
    snapshot_id: str,
    generation_id: int = 1,
    windows=None,
    elements=None,
    is_stale: bool = False,
    invalidation_reason=None,
    foreground_window=None,
) -> ObservationSnapshot:
    """Helper to build consistent ObservationSnapshot instances for verification testing."""
    return ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=generation_id,
        timestamp_ns=time.monotonic_ns(),
        timestamp_utc=datetime.now(timezone.utc),
        capture_duration_ms=5.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        windows=windows or [],
        detected_elements=elements or [],
        foreground_window=foreground_window,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
        is_stale=is_stale,
        invalidation_reason=invalidation_reason,
    )


class TestActionVerifierEvidenceHygiene:
    """Tests verifying evidence hygiene rules (staleness, generation parity, identical snapshot rejection)."""

    def test_missing_pre_action_snapshot_returns_inconclusive(self):
        verifier = ActionVerifier()
        post_snap = _make_snapshot("snap_post")
        res = verifier.verify(pre_snapshot=None, post_snapshot=post_snap)
        assert res.outcome == VerificationOutcome.INCONCLUSIVE
        assert res.confidence == 0.0
        assert "Missing pre-action observation snapshot" in (res.failure_reason or "")
        assert not res.is_success

    def test_missing_post_action_snapshot_returns_inconclusive(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre")
        res = verifier.verify(pre_snapshot=pre_snap, post_snapshot=None)
        assert res.outcome == VerificationOutcome.INCONCLUSIVE
        assert res.confidence == 0.0
        assert "Missing post-action observation snapshot" in (res.failure_reason or "")
        assert not res.is_success

    def test_identical_snapshot_reuse_rejected_fail_closed(self):
        verifier = ActionVerifier()
        snap = _make_snapshot("snap_identical")
        res = verifier.verify(pre_snapshot=snap, post_snapshot=snap)
        assert res.outcome == VerificationOutcome.STALE_EVIDENCE
        assert res.confidence == 0.0
        assert "identical to pre-action snapshot" in (res.failure_reason or "")
        assert not res.is_success

    def test_stale_post_action_snapshot_rejected(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre")
        post_snap = _make_snapshot(
            "snap_post",
            is_stale=True,
            invalidation_reason="TTL expired during action dispatch",
        )
        res = verifier.verify(pre_snapshot=pre_snap, post_snapshot=post_snap)
        assert res.outcome == VerificationOutcome.STALE_EVIDENCE
        assert res.confidence == 0.0
        assert "marked stale" in (res.failure_reason or "")
        assert not res.is_success

    def test_desktop_generation_mismatch_rejected(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre", generation_id=1)
        post_snap = _make_snapshot("snap_post", generation_id=2)
        res = verifier.verify(pre_snapshot=pre_snap, post_snapshot=post_snap)
        assert res.outcome == VerificationOutcome.STALE_EVIDENCE
        assert res.confidence == 0.0
        assert "Desktop generation changed across action dispatch" in (res.failure_reason or "")
        assert not res.is_success

    def test_unsupported_visual_semantic_strategy_rejected(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre")
        post_snap = _make_snapshot("snap_post")
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
            strategy=VerificationStrategy.VISUAL_SEMANTIC,
        )
        res = verifier.verify(pre_snapshot=pre_snap, post_snapshot=post_snap, expected_outcome=expected)
        assert res.outcome == VerificationOutcome.UNSUPPORTED
        assert res.confidence == 0.0
        assert "VISUAL_SEMANTIC strategy is unsupported" in (res.failure_reason or "")


class TestWindowStateVerification:
    """Tests evaluating window state transitions (appearance, closure, focus)."""

    def test_window_appeared_success(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre", windows=[])
        new_win = _make_window(
            hwnd=12345,
            title="Settings - ORBIT Test",
            class_name="OrbitSettingsClass",
            bounds=BoundingBox(left=100, top=100, width=800, height=600),
        )
        post_snap = _make_snapshot("snap_post", windows=[new_win])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.WINDOW_APPEARED,
            strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            window_title="Settings",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert res.confidence == 0.95
        assert len(res.detected_changes) > 0
        assert res.failure_reason is None

    def test_window_appeared_failure_when_missing(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre", windows=[])
        post_snap = _make_snapshot("snap_post", windows=[])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.WINDOW_APPEARED,
            strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            window_title="Notepad",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_FAILURE
        assert res.confidence == 0.90
        assert "did not appear" in (res.failure_reason or "")

    def test_window_closed_success(self):
        verifier = ActionVerifier()
        win = _make_window(
            hwnd=54321,
            title="Document - WordPad",
            class_name="WordPadClass",
            bounds=BoundingBox(left=100, top=100, width=600, height=400),
        )
        pre_snap = _make_snapshot("snap_pre", windows=[win])
        post_snap = _make_snapshot("snap_post", windows=[])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.WINDOW_CLOSED,
            strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            target_hwnd=54321,
            window_title="WordPad",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert res.confidence == 0.95
        assert "closed successfully" in res.detected_changes[0]

    def test_window_closed_failure_when_still_open(self):
        verifier = ActionVerifier()
        win = _make_window(
            hwnd=54321,
            title="Document - WordPad",
            class_name="WordPadClass",
            bounds=BoundingBox(left=100, top=100, width=600, height=400),
        )
        pre_snap = _make_snapshot("snap_pre", windows=[win])
        post_snap = _make_snapshot("snap_post", windows=[win])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.WINDOW_CLOSED,
            strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            target_hwnd=54321,
            window_title="WordPad",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_FAILURE
        assert "remains open" in (res.failure_reason or "")

    def test_window_focused_success(self):
        verifier = ActionVerifier()
        target_win = _make_window(
            hwnd=9999,
            title="Terminal",
            class_name="CASCADIA_HOSTING_WINDOW_CLASS",
            bounds=BoundingBox(left=0, top=0, width=800, height=600),
            is_foreground=True,
        )
        pre_snap = _make_snapshot("snap_pre", foreground_window=None)
        post_snap = _make_snapshot("snap_post", foreground_window=target_win)
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.WINDOW_FOCUSED,
            strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            target_hwnd=9999,
            window_title="Terminal",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert res.confidence == 0.95
        assert "foreground focus" in res.detected_changes[0]


class TestAccessibilityStateVerification:
    """Tests evaluating accessibility control state transitions (appearance, dismissal, property changes)."""

    def test_target_disappeared_success(self):
        verifier = ActionVerifier()
        dialog_el = ObservedElement(
            element_id="el_dialog_box",
            source="MSAA",
            name="Confirm Delete",
            role="Dialog",
            bounds=BoundingBox(left=400, top=300, width=300, height=150),
        )
        pre_snap = _make_snapshot("snap_pre", elements=[dialog_el])
        post_snap = _make_snapshot("snap_post", elements=[])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.TARGET_DISAPPEARED,
            strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            target_id="el_dialog_box",
            target_name="Confirm Delete",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert res.confidence == 0.95
        assert "disappeared" in res.detected_changes[0]

    def test_target_disappeared_failure_when_still_present(self):
        verifier = ActionVerifier()
        dialog_el = ObservedElement(
            element_id="el_dialog_box",
            source="MSAA",
            name="Confirm Delete",
            role="Dialog",
            bounds=BoundingBox(left=400, top=300, width=300, height=150),
        )
        pre_snap = _make_snapshot("snap_pre", elements=[dialog_el])
        post_snap = _make_snapshot("snap_post", elements=[dialog_el])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.TARGET_DISAPPEARED,
            strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            target_id="el_dialog_box",
            target_name="Confirm Delete",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_FAILURE
        assert "remains present" in (res.failure_reason or "")

    def test_target_appeared_success(self):
        verifier = ActionVerifier()
        toast_el = ObservedElement(
            element_id="el_toast",
            source="UI_AUTOMATION",
            name="Download Completed",
            role="Notification",
            bounds=BoundingBox(left=1500, top=900, width=300, height=100),
        )
        pre_snap = _make_snapshot("snap_pre", elements=[])
        post_snap = _make_snapshot("snap_post", elements=[toast_el])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.TARGET_APPEARED,
            strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            target_name="Download Completed",
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert res.confidence == 0.95
        assert "appeared" in res.detected_changes[0]

    def test_element_state_property_change_success(self):
        verifier = ActionVerifier()
        pre_el = ObservedElement(
            element_id="el_input_01",
            source="MSAA",
            name="Search Input",
            role="Edit",
            bounds=BoundingBox(left=200, top=100, width=300, height=30),
            is_focused=False,
        )
        post_el = ObservedElement(
            element_id="el_input_01",
            source="MSAA",
            name="Search Input",
            role="Edit",
            bounds=BoundingBox(left=200, top=100, width=300, height=30),
            is_focused=True,
        )
        pre_snap = _make_snapshot("snap_pre", elements=[pre_el])
        post_snap = _make_snapshot("snap_post", elements=[post_el])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
            strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            target_id="el_input_01",
            expected_property="is_focused",
            expected_value=True,
        )
        res = verifier.verify(pre_snap, post_snap, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert res.confidence == 0.95
        assert "changed to expected value" in res.detected_changes[0]


class TestObservationDeltaVerification:
    """Tests evaluating general observation delta verification."""

    def test_observable_delta_detected_success(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre", windows=[])
        new_win = _make_window(
            hwnd=777,
            title="New Window",
            class_name="SampleClass",
            bounds=BoundingBox(left=0, top=0, width=400, height=300),
        )
        post_snap = _make_snapshot("snap_post", windows=[new_win])
        res = verifier.verify(pre_snap, post_snap)
        assert res.outcome == VerificationOutcome.VERIFIED_SUCCESS
        assert res.confidence == 0.80
        assert len(res.detected_changes) == 1

    def test_zero_delta_without_expectation_returns_inconclusive(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre", windows=[])
        post_snap = _make_snapshot("snap_post", windows=[])
        res = verifier.verify(pre_snap, post_snap, expected_outcome=None)
        assert res.outcome == VerificationOutcome.INCONCLUSIVE
        assert res.confidence == 0.30
        assert "Zero observable UI state changes detected" in (res.failure_reason or "")

    def test_zero_delta_with_expected_change_returns_failure(self):
        verifier = ActionVerifier()
        pre_snap = _make_snapshot("snap_pre", windows=[])
        post_snap = _make_snapshot("snap_post", windows=[])
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
            strategy=VerificationStrategy.OBSERVATION_STATE_DELTA,
        )
        res = verifier.verify(pre_snap, post_snap, expected_outcome=expected)
        assert res.outcome == VerificationOutcome.VERIFIED_FAILURE
        assert res.confidence == 0.80
        assert "Zero observable UI state changes detected" in (res.failure_reason or "")


class TestConfidenceAndEvidenceSafety:
    """Tests enforcing deterministic confidence calculation, conflicting evidence, and no fake success."""

    def test_deterministic_confidence_calculation(self):
        verifier = ActionVerifier()
        # Unsupported strategy -> confidence must be 0.0
        pre = _make_snapshot("p1")
        post = _make_snapshot("p2")
        res_unsupported = verifier.verify(pre, post, ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.ANY_OBSERVABLE_CHANGE,
            strategy=VerificationStrategy.VISUAL_SEMANTIC,
        ))
        assert res_unsupported.confidence == 0.0

        # Stale evidence -> confidence must be 0.0
        res_stale = verifier.verify(pre, _make_snapshot("p3", is_stale=True))
        assert res_stale.confidence == 0.0

        # Confirmed window closure -> confidence must be 0.95
        win = _make_window(hwnd=101, title="App Window")
        res_win = verifier.verify(
            _make_snapshot("p4", windows=[win]),
            _make_snapshot("p5", windows=[]),
            ExpectedOutcome(
                outcome_type=ExpectedOutcomeType.WINDOW_CLOSED,
                strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
                target_hwnd=101,
            ),
        )
        assert res_win.confidence == 0.95

    def test_no_fake_success_when_evidence_is_absent(self):
        verifier = ActionVerifier()
        # Empty windows and empty elements
        pre = _make_snapshot("p1", windows=[], elements=[])
        post = _make_snapshot("p2", windows=[], elements=[])

        # Expecting element to change state when element does not even exist
        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.ELEMENT_STATE_CHANGED,
            strategy=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
            target_id="missing_button",
            expected_property="is_focused",
            expected_value=True,
        )
        res = verifier.verify(pre, post, expected)
        assert res.outcome == VerificationOutcome.INCONCLUSIVE
        assert not res.is_success
        assert res.confidence == 0.5
        assert "could not be compared" in (res.failure_reason or "")

    def test_conflicting_evidence_rejected_safely(self):
        verifier = ActionVerifier()
        # Window claimed to be closed, but still present in post_snapshot
        win = _make_window(hwnd=500, title="Important Notice")
        pre = _make_snapshot("p1", windows=[win])
        post = _make_snapshot("p2", windows=[win])

        expected = ExpectedOutcome(
            outcome_type=ExpectedOutcomeType.WINDOW_CLOSED,
            strategy=VerificationStrategy.WINDOW_STATE_CHANGE,
            target_hwnd=500,
        )
        res = verifier.verify(pre, post, expected)
        assert res.outcome == VerificationOutcome.VERIFIED_FAILURE
        assert not res.is_success
        assert "remains open" in (res.failure_reason or "")
