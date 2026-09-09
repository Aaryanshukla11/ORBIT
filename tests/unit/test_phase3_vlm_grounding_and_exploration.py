"""Phase 3 Unit Tests: VLM Grounding Separation & Bounded Exploration Policy.

Tests adherence to ASTRA evaluation dimensions:
- Dimension 7: Evidence-Based Target Grounding & Bounding Box Verification
- Dimension 18: VLM Semantic Boundary (hypotheses cannot directly dispatch physical actions)
- Dimension 22: Exploration Termination Guarantee (no open-ended infinite loops)
"""

import pytest
from orbit.adapters.observation.snapshot import (
    BoundingBox,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.runtime.perception.vlm_grounding import (
    ExplorationPolicy,
    GroundedTargetResult,
    VLMGroundingVerifier,
    VLMHypothesis,
)
from orbit.runtime.targeting.models import TargetResolutionStatus


def _make_snapshot(elements=None, windows=None, width=1920, height=1080):
    return ObservationSnapshot(
        snapshot_id="snap_test_vlm",
        generation_id=1,
        timestamp_ns=1000000,
        capture_duration_ms=10.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=width, height=height),
        windows=windows or [],
        detected_elements=elements or [],
    )


# ============================================================================
# Dimension 7 & 18: VLM Grounding & Boundary Enforcement
# ============================================================================

def test_vlm_grounding_rejects_unnormalized_hypothesis():
    """Requirement: VLM hypotheses specifying coordinates outside [0.0, 1.0] are rejected."""
    verifier = VLMGroundingVerifier()
    snap = _make_snapshot()

    bad_hyp = VLMHypothesis(
        target_name="Submit",
        normalized_region=(100.0, 200.0, 300.0, 400.0),
    )

    res = verifier.verify_hypothesis(bad_hyp, snap)
    assert res.is_grounded is False
    assert res.status == TargetResolutionStatus.INVALID_REQUEST
    assert "outside normalized [0.0, 1.0]" in res.rejection_reason


def test_vlm_grounding_rejects_target_outside_active_window():
    """Requirement: VLM hypotheses falling outside active window boundary fail verification."""
    verifier = VLMGroundingVerifier()
    snap = _make_snapshot()

    # Active window located at (100, 100, 400, 400)
    win = ObservedWindow(
        hwnd=12345,
        process_id=999,
        process_name="calc.exe",
        window_title="Calculator",
        extended_bounds=BoundingBox(left=100, top=100, width=400, height=400),
    )

    # Hypothesis targeting bottom-right corner of screen (u=0.9, v=0.9 -> ~1728, 972)
    outside_hyp = VLMHypothesis(
        target_name="Equals",
        normalized_region=(0.85, 0.85, 0.95, 0.95),
    )

    res = verifier.verify_hypothesis(outside_hyp, snap, active_window=win)
    assert res.is_grounded is False
    assert res.status == TargetResolutionStatus.NOT_FOUND
    assert "outside active window bounds" in res.rejection_reason


def test_vlm_grounding_cross_verifies_with_accessibility_tree():
    """Requirement: VLM hypothesis overlapping authoritative UIA element yields verified GroundedTarget."""
    verifier = VLMGroundingVerifier()

    # UIA element at (150, 150, 100, 50) -> screen center ~ (200, 175)
    elem = ObservedElement(
        element_id="btn_submit_uia",
        source="UI_AUTOMATION",
        name="Submit Form",
        control_type="Button",
        bounds=BoundingBox(left=150, top=150, width=100, height=50),
        is_enabled=True,
    )
    snap = _make_snapshot(elements=[elem], width=1000, height=1000)

    # VLM hypothesis region ~ (140, 140, 260, 210) normalized in 1000x1000 -> (0.14, 0.14, 0.26, 0.21)
    hyp = VLMHypothesis(
        target_name="Submit",
        normalized_region=(0.14, 0.14, 0.26, 0.21),
        confidence=0.8,
    )

    res = verifier.verify_hypothesis(hyp, snap, screen_resolution=(1000, 1000))
    assert res.is_grounded is True
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.resolved_target is not None
    assert res.resolved_target.safe_point.x == 200
    assert res.resolved_target.safe_point.y == 175
    assert res.resolved_target.evidence.source == "UI_AUTOMATION"


def test_vlm_grounding_fails_closed_without_corroboration():
    """Requirement: Low-confidence VLM hypothesis without UIA evidence fails closed."""
    verifier = VLMGroundingVerifier(min_confidence=0.7)
    snap = _make_snapshot()

    hyp = VLMHypothesis(
        target_name="Ghost Button",
        normalized_region=(0.4, 0.4, 0.5, 0.5),
        confidence=0.4,  # Below 0.7 threshold
    )

    res = verifier.verify_hypothesis(hyp, snap)
    assert res.is_grounded is False
    assert res.status == TargetResolutionStatus.LOW_CONFIDENCE
    assert "below threshold" in res.rejection_reason


# ============================================================================
# Dimension 22: Exploration Termination Guarantee
# ============================================================================

def test_exploration_policy_terminates_on_discovery():
    """Requirement: Exploration halts immediately when target is discovered."""
    policy = ExplorationPolicy(max_steps=5, stagnation_limit=2)

    cont = policy.record_step(new_elements_found=3, target_grounded=False)
    assert cont is True
    assert policy.is_terminated is False

    # Target discovered on step 2
    cont = policy.record_step(new_elements_found=1, target_grounded=True)
    assert cont is False
    assert policy.is_terminated is True
    assert policy.termination_reason == "TARGET_DISCOVERED"


def test_exploration_policy_terminates_on_stagnation():
    """Requirement: Exploration halts if no new elements are discovered within stagnation limit."""
    policy = ExplorationPolicy(max_steps=5, stagnation_limit=2)

    # Step 1: found elements
    policy.record_step(new_elements_found=2)
    assert policy.is_terminated is False

    # Step 2: 0 new elements (stagnant 1)
    policy.record_step(new_elements_found=0)
    assert policy.is_terminated is False

    # Step 3: 0 new elements (stagnant 2 -> limit reached)
    cont = policy.record_step(new_elements_found=0)
    assert cont is False
    assert policy.is_terminated is True
    assert policy.termination_reason == "EXPLORATION_STAGNATION"


def test_exploration_policy_terminates_on_budget_exhaustion():
    """Requirement: Exploration halts deterministically when max_steps budget is reached."""
    policy = ExplorationPolicy(max_steps=3, stagnation_limit=3)

    policy.record_step(new_elements_found=1)
    policy.record_step(new_elements_found=1)
    cont = policy.record_step(new_elements_found=1)  # step 3 == max_steps

    assert cont is False
    assert policy.is_terminated is True
    assert policy.termination_reason == "BUDGET_EXHAUSTED"
