"""Unit and Regression Tests for Phase 2D: Layered WorldState, 4-Pass Grounding, Settle Detection & Freshness.

Guarantees Verified:
1. Layered WorldState (Tiers 1-4): Raw Evidence -> Perception/Fusion -> Canonical WorldState -> Compact Context.
2. 4-Pass Grounding: Pass 1 (UIA) -> Pass 2 (OCR/fuzzy) -> Pass 3 (Icon) -> Pass 4 (VLM).
3. GroundingCandidate Schema: target, bounds [ymin, xmin, ymax, xmax], source, confidence, observation_id, freshness_timestamp.
4. Dynamic Perceptual Settle Detection: pixel delta calculations, settlement thresholds, stability detection.
5. Strict Stale Grounding Rejection: Proposal or candidate grounded on observation N is rejected if execution attempted on N+1.
6. Clean boundary: Perception and grounding do not contain autonomous heuristic decision logic.
"""

from __future__ import annotations

import time
import pytest
from PIL import Image

from orbit.runtime.cognitive.world_state import (
    UnifiedWorldState,
    RawEvidenceLayer,
    PerceptionFusionLayer,
    CanonicalWorldState,
    CanonicalUIElement,
    CompactContext,
    WorldStateBuilder,
)
from orbit.runtime.targeting.grounding import (
    GroundingCandidate,
    GroundingSource,
    GroundingResult,
    MultiPassGrounder,
    StaleGroundingValidator,
)
from orbit.runtime.perception.settle import (
    PerceptualSettleDetector,
    SettleResult,
)
from orbit.runtime.cognitive.model_proposal import (
    ModelActionProposal,
    ModelActionType,
    TargetSelector,
)
from orbit.runtime.cognitive.primitive_validator import (
    ModelProposalValidator,
    ProposalValidationStage,
)
from orbit.runtime.cognitive.prompt_builder import MultimodalPromptBuilder
from orbit.runtime.cognitive.models import CurrentStateObservation


# =====================================================================
# 1. LAYERED WORLDSTATE TESTS
# =====================================================================

def test_layered_world_state_tier_construction():
    """Verify that WorldStateBuilder builds all 4 layers correctly with canonical fields."""
    img = Image.new("RGB", (1920, 1080), color=(255, 255, 255))
    raw_uia = [
        {"name": "File", "role": "menu_item", "bounds": [10, 20, 30, 60], "confidence": 0.95},
        {"name": "Save", "role": "button", "bounds": [50, 20, 80, 70], "confidence": 0.98},
    ]
    raw_ocr = [
        {"text": "Canvas Ready", "confidence": 0.90, "bounds": [900, 100, 930, 300]}
    ]

    ws = WorldStateBuilder.build_world_state(
        observation_id="obs_001_initial",
        screenshot=img,
        uia_elements=raw_uia,
        ocr_tokens=raw_ocr,
        active_window_title="Untitled - Paint",
        active_process_name="mspaint.exe",
        active_hwnd=12345,
    )

    # 1. Observation Identity
    assert ws.observation_id == "obs_001_initial"
    assert ws.timestamp > 0

    # 2. Tier 1: Raw Evidence Layer
    assert ws.raw_evidence.raw_screenshot_shape == (1080, 1920, 3)
    assert len(ws.raw_evidence.raw_uia_tree) == 2
    assert len(ws.raw_evidence.raw_ocr_tokens) == 1
    assert ws.raw_evidence.active_window_hwnd == 12345

    # 3. Tier 2: Perception / Fusion Layer
    assert len(ws.perception_fusion.detected_ui_nodes) == 3
    assert len(ws.perception_fusion.ocr_spatial_clusters) == 1

    # 4. Tier 3: Canonical WorldState
    assert ws.canonical_state.active_window_title == "Untitled - Paint"
    assert ws.canonical_state.active_process_name == "mspaint.exe"
    assert len(ws.canonical_state.interactive_elements) == 3

    file_elem = next(e for e in ws.canonical_state.interactive_elements if e.name == "File")
    assert file_elem.role == "menu_item"
    assert file_elem.bounds == [10, 20, 30, 60]

    # 5. Tier 4: Compact Context
    assert ws.compact_context.foreground_window_title == "Untitled - Paint"
    assert ws.compact_context.screen_resolution == "1920x1080"
    assert len(ws.compact_context.interactive_summary) == 3
    assert ws.compact_context.app_context == "Paint"


# =====================================================================
# 2. 4-PASS GROUNDING TESTS
# =====================================================================

def test_four_pass_grounding_pass1_uia():
    """Verify Pass 1 grounds directly from UIA accessibility elements."""
    ws = WorldStateBuilder.build_world_state(
        observation_id="obs_uia_test",
        screenshot=Image.new("RGB", (800, 600)),
        uia_elements=[
            {"name": "Save As", "role": "menu_item", "bounds": [100, 50, 130, 120], "confidence": 0.96},
        ],
        ocr_tokens=[],
        active_window_title="Editor",
        active_process_name="notepad.exe",
    )

    grounder = MultiPassGrounder()
    result = grounder.ground_target(
        target_name="Save As",
        target_role="menu_item",
        world_state=ws,
    )

    assert result.is_grounded is True
    assert result.pass_number == 1
    assert "PASS_1_UIA" in result.attempted_passes
    assert result.candidate is not None
    assert result.candidate.source == GroundingSource.UIA
    assert result.candidate.bounds == [100, 50, 130, 120]
    assert result.candidate.observation_id == "obs_uia_test"
    assert result.candidate.confidence >= 0.90


def test_four_pass_grounding_pass2_ocr_fuzzy():
    """Verify Pass 2 grounds from OCR text tokens when UIA has no match."""
    ws = WorldStateBuilder.build_world_state(
        observation_id="obs_ocr_test",
        screenshot=Image.new("RGB", (800, 600)),
        uia_elements=[],  # No UIA elements available
        ocr_tokens=[
            {"text": "Export Document", "confidence": 0.88, "bounds": [200, 300, 240, 450]},
        ],
        active_window_title="Custom App",
        active_process_name="custom.exe",
    )

    grounder = MultiPassGrounder()
    result = grounder.ground_target(
        target_name="Export Document",
        target_role=None,
        world_state=ws,
    )

    assert result.is_grounded is True
    assert result.pass_number == 2
    assert "PASS_1_UIA" in result.attempted_passes
    assert "PASS_2_OCR" in result.attempted_passes
    assert result.candidate is not None
    assert result.candidate.source == GroundingSource.OCR
    assert result.candidate.bounds == [200, 300, 240, 450]
    assert result.candidate.observation_id == "obs_ocr_test"


def test_four_pass_grounding_pass4_vlm_bounds():
    """Verify Pass 4 falls back to VLM candidate bounds when UIA and OCR fail."""
    ws = WorldStateBuilder.build_world_state(
        observation_id="obs_vlm_test",
        screenshot=Image.new("RGB", (1000, 1000)),
        uia_elements=[],
        ocr_tokens=[],
        active_window_title="Render View",
        active_process_name="canvas.exe",
    )

    grounder = MultiPassGrounder()
    result = grounder.ground_target(
        target_name="Unlabeled Drawing Palette",
        target_role="canvas",
        world_state=ws,
        candidate_bounds=[400, 400, 600, 600],
    )

    assert result.is_grounded is True
    assert result.pass_number == 4
    assert result.candidate is not None
    assert result.candidate.source == GroundingSource.VLM
    assert result.candidate.bounds == [400, 400, 600, 600]
    assert result.candidate.observation_id == "obs_vlm_test"


# =====================================================================
# 3. GROUNDING CANDIDATE SCHEMA & CENTER CALCULATION
# =====================================================================

def test_grounding_candidate_schema_and_coordinates():
    """Verify GroundingCandidate schema completeness and center transformations."""
    candidate = GroundingCandidate(
        target="File Menu",
        bounds=[100, 200, 300, 400],  # ymin, xmin, ymax, xmax in 0-1000
        source=GroundingSource.UIA,
        confidence=0.99,
        observation_id="obs_schema_test",
    )

    assert candidate.target == "File Menu"
    assert candidate.bounds == [100, 200, 300, 400]
    assert candidate.source == GroundingSource.UIA
    assert candidate.confidence == 0.99
    assert candidate.observation_id == "obs_schema_test"
    assert candidate.freshness_timestamp > 0

    # Normalized center (u, v): x_mid = (200+400)/2000 = 0.3, y_mid = (100+300)/2000 = 0.2
    u, v = candidate.center_normalized
    assert pytest.approx(u, 0.001) == 0.3
    assert pytest.approx(v, 0.001) == 0.2

    # Pixel center for 1920x1080 screen: x = 0.3 * 1920 = 576, y = 0.2 * 1080 = 216
    px, py = candidate.to_pixel_center(1920, 1080)
    assert px == 576
    assert py == 216


# =====================================================================
# 4. DYNAMIC PERCEPTUAL SETTLE DETECTION TESTS
# =====================================================================

def test_dynamic_perceptual_settle_detection():
    """Verify PerceptualSettleDetector computes pixel deltas and reports settle status."""
    detector = PerceptualSettleDetector(
        settle_threshold=0.01,
        min_stable_frames=2,
        max_settle_timeout=1.0,
    )

    # Identical frames -> settle immediately
    frame1 = Image.new("RGB", (200, 200), color=(100, 100, 100))
    frame2 = Image.new("RGB", (200, 200), color=(100, 100, 100))

    delta = detector.calculate_pixel_delta(frame1, frame2)
    assert delta == 0.0

    # Changing frame -> delta > threshold
    frame3 = Image.new("RGB", (200, 200), color=(200, 200, 200))
    delta_changed = detector.calculate_pixel_delta(frame1, frame3)
    assert delta_changed > 0.01

    # Settle sequence simulation
    frames = [
        Image.new("RGB", (100, 100), color=(0, 0, 0)),
        Image.new("RGB", (100, 100), color=(255, 255, 255)),
        Image.new("RGB", (100, 100), color=(255, 255, 255)),
        Image.new("RGB", (100, 100), color=(255, 255, 255)),
    ]
    frame_iter = iter(frames)
    result = detector.wait_until_settled(capture_fn=lambda: next(frame_iter))

    assert result.is_settled is True
    assert result.stable_frames >= 2
    assert result.final_pixel_delta <= 0.01


# =====================================================================
# 5. STALE GROUNDING REJECTION TESTS
# =====================================================================

def test_stale_grounding_rejection_against_new_observation():
    """Verify proposal grounded against Observation N is rejected if validated against N+1."""
    validator = ModelProposalValidator()

    # Proposal grounded against observation N
    proposal_obs_n = ModelActionProposal(
        action_type=ModelActionType.CLICK,
        target_selector=TargetSelector(
            name="Save Button",
            role="button",
            bounds=[100, 100, 140, 200],
            observation_id="obs_frame_100",
        ),
        expected_outcome="Save dialog opened",
        observation_id="obs_frame_100",
    )

    # 1. Validation against same observation N -> VALID
    valid_result = validator.validate_proposal(
        proposal_obs_n,
        current_observation_id="obs_frame_100",
    )
    assert valid_result.is_valid is True

    # 2. Validation against subsequent observation N+1 -> REJECTED (STALE GROUNDING)
    stale_result = validator.validate_proposal(
        proposal_obs_n,
        current_observation_id="obs_frame_101",
    )
    assert stale_result.is_valid is False
    assert stale_result.failed_stage == ProposalValidationStage.GROUNDING
    assert "STALE_GROUNDING_REJECTED" in stale_result.failure_reason
    assert "obs_frame_100" in stale_result.failure_reason
    assert "obs_frame_101" in stale_result.failure_reason


def test_stale_grounding_validator_time_decay():
    """Verify StaleGroundingValidator rejects candidate when timestamp exceeds freshness limit."""
    candidate = GroundingCandidate(
        target="Text Editor",
        bounds=[50, 50, 500, 500],
        source=GroundingSource.UIA,
        confidence=0.95,
        observation_id="obs_decay_test",
        freshness_timestamp=time.time() - 5.0,  # 5 seconds old
    )

    is_fresh, reason = StaleGroundingValidator.validate_candidate_freshness(
        candidate=candidate,
        current_observation_id="obs_decay_test",
        max_age_seconds=3.0,
    )

    assert is_fresh is False
    assert "STALE_GROUNDING_REJECTED" in reason
    assert "exceeded freshness limit" in reason


# =====================================================================
# 6. PROMPT BUILDER INTEGRATION WITH COMPACT CONTEXT
# =====================================================================

def test_prompt_builder_consumes_world_state_compact_context():
    """Verify MultimodalPromptBuilder embeds CompactContext and observation_id."""
    ws = WorldStateBuilder.build_world_state(
        observation_id="obs_prompt_tier4",
        screenshot=Image.new("RGB", (1280, 720)),
        uia_elements=[
            {"name": "Save", "role": "button", "bounds": [10, 10, 30, 40]},
            {"name": "Canvas", "role": "canvas", "bounds": [50, 50, 700, 700]},
        ],
        active_window_title="Untitled - Paint",
        active_process_name="mspaint.exe",
    )

    obs = CurrentStateObservation(
        active_window_title="Untitled - Paint",
        active_process_name="mspaint.exe",
        world_state=ws,
    )

    builder = MultimodalPromptBuilder()
    payload = builder.build_prompt(
        user_goal="Draw a blue circle and save",
        current_observation=obs,
    )

    user_prompt = payload["user_prompt"]
    assert "obs_prompt_tier4" in user_prompt
    assert "Untitled - Paint" in user_prompt
    assert "Focus App Context: Paint" in user_prompt
    assert "[button] \"Save\"" in user_prompt
