"""Unit tests for Phase 3: GroundingValidator and coordinate boundary enforcement."""

import pytest
from orbit.runtime.agent.contracts import SemanticTarget
from orbit.runtime.agent.grounding_validator import GroundingValidator, GroundingValidationResult
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
)


def test_grounding_validator_accepts_valid_grounded_target():
    validator = GroundingValidator(desktop_width=1920, desktop_height=1080)
    target = SemanticTarget(name="Submit", role="button")

    bbox = TargetBoundingBox(left=100, top=200, right=200, bottom=250)
    pt = SafeActionPoint(x=150, y=225, bounding_box=bbox, desktop_generation_id=1)
    ev = TargetEvidence(source="UI_AUTOMATION", identifier="btn_submit")
    resolved = ResolvedTarget(
        target_id="tgt_1",
        bounding_box=bbox,
        safe_point=pt,
        confidence=0.95,
        evidence=ev,
        observation_id="obs_1",
        desktop_generation_id=1,
    )

    res: GroundingValidationResult = validator.validate_grounding(
        target=target,
        resolved_target=resolved,
    )
    assert res.is_valid is True
    assert res.validated_point == (150, 225)
    assert res.confidence == 0.95


def test_grounding_validator_rejects_low_confidence():
    validator = GroundingValidator(min_confidence=0.70)
    target = SemanticTarget(name="Submit", role="button")

    bbox = TargetBoundingBox(left=100, top=200, right=200, bottom=250)
    pt = SafeActionPoint(x=150, y=225, bounding_box=bbox, desktop_generation_id=1)
    resolved = ResolvedTarget(
        target_id="tgt_1",
        bounding_box=bbox,
        safe_point=pt,
        confidence=0.55,  # below 0.70 threshold
        evidence=TargetEvidence(source="VISION", identifier="btn_submit"),
        observation_id="obs_1",
        desktop_generation_id=1,
    )

    res: GroundingValidationResult = validator.validate_grounding(
        target=target,
        resolved_target=resolved,
    )
    assert res.is_valid is False
    assert "below safety threshold" in res.failure_reason


def test_grounding_validator_rejects_out_of_bounds_coordinates():
    validator = GroundingValidator(desktop_width=1920, desktop_height=1080)
    target = SemanticTarget(name="OffscreenButton", role="button")

    res: GroundingValidationResult = validator.validate_grounding(
        target=target,
        candidate_coords=(2500, 500),  # x=2500 exceeds width 1920
    )
    assert res.is_valid is False
    assert "outside desktop bounds" in res.failure_reason


def test_grounding_validator_rejects_coordinates_outside_bounding_box():
    validator = GroundingValidator(desktop_width=1920, desktop_height=1080)
    target = SemanticTarget(name="Button", role="button")

    bbox = TargetBoundingBox(left=100, top=200, right=200, bottom=250)
    # Point is outside bbox
    pt = SafeActionPoint(x=50, y=50, bounding_box=bbox, desktop_generation_id=1)
    resolved = ResolvedTarget(
        target_id="tgt_1",
        bounding_box=bbox,
        safe_point=pt,
        confidence=0.90,
        evidence=TargetEvidence(source="UIA", identifier="btn"),
        observation_id="obs_1",
        desktop_generation_id=1,
    )

    res: GroundingValidationResult = validator.validate_grounding(
        target=target,
        resolved_target=resolved,
    )
    assert res.is_valid is False
    assert "outside resolved bounding box" in res.failure_reason
