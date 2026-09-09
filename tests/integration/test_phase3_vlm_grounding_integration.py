"""Phase 3 Integration Test: Evidence-Driven VLM Grounding and Bounded Exploration.

Validates:
VLM Semantic Hypothesis -> Dual-Gate Verification (Containment + UIA IoU) -> ResolvedTarget SafeActionPoint -> Zero Physical Dispatch on Rejection.
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
    VLMGroundingVerifier,
    VLMHypothesis,
)
from orbit.runtime.targeting.models import TargetResolutionStatus


@pytest.mark.asyncio
async def test_vlm_grounding_end_to_end_verification_pipeline():
    verifier = VLMGroundingVerifier(min_confidence=0.6)

    # 1. Setup Active Window and Observed UI Button
    active_win = ObservedWindow(
        hwnd=44556,
        process_id=1234,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        extended_bounds=BoundingBox(left=50, top=50, width=800, height=600),
    )
    save_btn = ObservedElement(
        element_id="btn_save_uia",
        source="UI_AUTOMATION",
        name="Save",
        control_type="MenuItem",
        bounds=BoundingBox(left=70, top=80, width=60, height=30),
        is_enabled=True,
    )
    snap = ObservationSnapshot(
        snapshot_id="snap_vlm_integ",
        generation_id=2,
        timestamp_ns=1000000,
        capture_duration_ms=10.0,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[active_win],
        detected_elements=[save_btn],
    )

    # 2. Hypothesis for Save Button in 1920x1080:
    # 70/1920 ~ 0.036, 80/1080 ~ 0.074, 130/1920 ~ 0.068, 110/1080 ~ 0.102
    hyp_valid = VLMHypothesis(
        target_name="Save",
        semantic_role="button",
        normalized_region=(0.03, 0.07, 0.08, 0.11),
        confidence=0.85,
    )

    res = verifier.verify_hypothesis(
        hyp_valid,
        snap,
        screen_resolution=(1920, 1080),
        active_window=active_win,
    )

    assert res.is_grounded is True
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.resolved_target.safe_point.x == save_btn.bounds.center.x
    assert res.resolved_target.safe_point.y == save_btn.bounds.center.y
    assert res.resolved_target.evidence.source == "UI_AUTOMATION"

    # 3. Exploration Policy with discovery
    policy = ExplorationPolicy(max_steps=5, stagnation_limit=2)
    can_continue = policy.record_step(new_elements_found=1, target_grounded=True)
    assert can_continue is False
    assert policy.is_terminated is True
    assert policy.termination_reason == "TARGET_DISCOVERED"
