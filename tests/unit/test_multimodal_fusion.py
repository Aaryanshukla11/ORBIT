"""Unit tests for Multi-Modal Perception Fusion & Confidence Grounding Layer."""

import time
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
from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
from orbit.runtime.perception.fusion_models import (
    EvidenceChannel,
    FusionPolicy,
    FusionStatus,
    PerceptionEvidence,
    SpatialRelation,
)
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRWord,
)
from orbit.runtime.perception.visual_models import (
    VisualMatchRegion,
    VisualMatchResult,
    VisualMatchStatus,
    VisualMatcherKind,
)
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    TargetBoundingBox,
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


def _create_test_snapshot(
    generation_id: int = 1,
    is_stale: bool = False,
    elements: list[ObservedElement] | None = None,
    windows: list[ObservedWindow] | None = None,
) -> ObservationSnapshot:
    """Helper creating an ObservationSnapshot for fusion tests."""
    return ObservationSnapshot(
        snapshot_id="snap_fusion_001",
        timestamp_ns=time.monotonic_ns(),
        generation_id=generation_id,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        detected_elements=elements or [],
        windows=windows or [],
        is_stale=is_stale,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
    )


def test_spatial_agreement_iou_and_distance():
    """Test geometric agreement evaluation across overlapping and disjoint boxes."""
    engine = MultiModalPerceptionFusionEngine()

    box1 = TargetBoundingBox(left=100, top=100, right=200, bottom=200)
    box2 = TargetBoundingBox(left=120, top=120, right=220, bottom=220)
    box_far = TargetBoundingBox(left=500, top=500, right=600, bottom=600)

    # Overlapping
    agreement = engine.evaluate_spatial_agreement(box1, box2)
    assert agreement.is_aligned is True
    assert agreement.iou > 0.3
    assert agreement.relation == SpatialRelation.OVERLAPPING

    # Disjoint far away
    agreement_far = engine.evaluate_spatial_agreement(box1, box_far)
    assert agreement_far.is_aligned is False
    assert agreement_far.iou == 0.0
    assert agreement_far.relation == SpatialRelation.DISJOINT


def test_semantic_agreement_exact_and_fuzzy():
    """Test semantic matching and normalization across perception labels."""
    engine = MultiModalPerceptionFusionEngine()

    # Exact
    sem_exact = engine.evaluate_semantic_agreement("Save Document", "save document")
    assert sem_exact.is_matched is True
    assert sem_exact.similarity_score == 1.0

    # Substring / Partial
    sem_sub = engine.evaluate_semantic_agreement("Save", "Save Document")
    assert sem_sub.is_matched is True
    assert sem_sub.similarity_score >= 0.90

    # Disjoint
    sem_diff = engine.evaluate_semantic_agreement("Cancel", "Settings")
    assert sem_diff.is_matched is False
    assert sem_diff.similarity_score == 0.0


def test_grounded_confidence_non_inflation():
    """Prove that combining weak evidence NEVER inflates confidence above source bounds."""
    engine = MultiModalPerceptionFusionEngine()

    weak_evidence = [
        PerceptionEvidence(
            channel=EvidenceChannel.OCR_TEXT,
            bounding_box=TargetBoundingBox(left=100, top=100, right=150, bottom=130),
            confidence=0.60,
            text_label="Settings",
            desktop_generation_id=1,
        )
    ]

    # Weak primary + weak supporting
    fused_conf = engine.calculate_grounded_confidence(
        primary_conf=0.60,
        supporting_items=weak_evidence,
        spatial=None,
        semantic=None,
    )

    # Must NOT become high confidence (> 0.80)
    assert fused_conf <= 0.65
    assert fused_conf < 0.80


def test_multimodal_fusion_accessibility_and_ocr_agreement():
    """When UIA element and OCR text align spatially and semantically, fusion returns RESOLVED."""
    engine = MultiModalPerceptionFusionEngine()

    el = ObservedElement(
        element_id="btn_save",
        name="Save",
        role="Button",
        control_type="Button",
        source="UIA",
        bounds=BoundingBox(left=100, top=200, width=80, height=30),
        is_enabled=True,
        is_offscreen=False,
    )
    snapshot = _create_test_snapshot(generation_id=1, elements=[el])

    ocr_word = OCRWord(
        text="Save",
        normalized_text="save",
        bounding_box=OCRBoundingBox(left=105, top=205, right=175, bottom=225, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.98,
    )
    ocr_region = OCRTextRegion(
        text="Save",
        normalized_text="save",
        bounding_box=OCRBoundingBox(left=105, top=205, right=175, bottom=225, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[ocr_word],
        confidence=0.98,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        full_text="Save",
        desktop_generation_id=1,
    )

    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        name="Save",
        text="Save",
    )

    fusion_res = engine.fuse_multimodal_intent(
        snapshot=snapshot,
        intent=intent,
        ocr_result=ocr_res,
    )

    assert fusion_res.status == FusionStatus.RESOLVED
    assert fusion_res.fused_target is not None
    assert fusion_res.fused_target.confidence >= 0.80
    assert len(fusion_res.fused_target.fused_evidence.supporting_channels) > 0


def test_multimodal_fusion_visual_and_ocr_disambiguation():
    """When 3 identical visual icons exist, OCR text anchor disambiguates to the closest one."""
    engine = MultiModalPerceptionFusionEngine()
    snapshot = _create_test_snapshot(generation_id=1)

    # 3 visual candidate icons at X=100, X=300, X=500
    v1 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=100, top=100, right=132, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_gear",
        template_name="Settings",
    )
    v2 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=300, top=100, right=332, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_gear",
        template_name="Settings",
    )
    v3 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=500, top=100, right=532, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_gear",
        template_name="Settings",
    )
    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[v1, v2, v3],
        best_match=v1,
        template_id="tpl_gear",
        desktop_generation_id=1,
    )

    # OCR text anchor "General Settings" near the second icon (X=340)
    ocr_region = OCRTextRegion(
        text="General Settings",
        normalized_text="general settings",
        bounding_box=OCRBoundingBox(left=340, top=105, right=440, bottom=125, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        full_text="General Settings",
        desktop_generation_id=1,
    )

    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        text="General Settings",
        template_id="tpl_gear",
    )

    fusion_res = engine.fuse_multimodal_intent(
        snapshot=snapshot,
        intent=intent,
        ocr_result=ocr_res,
        visual_result=vis_res,
    )

    assert fusion_res.status == FusionStatus.RESOLVED
    assert fusion_res.fused_target is not None
    # Disambiguated target must be the second icon at X=300
    assert fusion_res.fused_target.bounding_box.left == 300


def test_multimodal_fusion_equidistant_icons_ambiguous_fails_closed():
    """When two identical icons are equidistant to the text anchor, fusion returns AMBIGUOUS."""
    engine = MultiModalPerceptionFusionEngine()
    snapshot = _create_test_snapshot(generation_id=1)

    # 2 icons equidistant from X=200 (one at X=150, one at X=250)
    v1 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=150, top=100, right=182, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_btn",
        template_name="Button",
    )
    v2 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=250, top=100, right=282, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_btn",
        template_name="Button",
    )
    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[v1, v2],
        best_match=v1,
        template_id="tpl_btn",
        desktop_generation_id=1,
    )

    # Text at X=200
    ocr_region = OCRTextRegion(
        text="Center Label",
        normalized_text="center label",
        bounding_box=OCRBoundingBox(left=200, top=100, right=240, bottom=120, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        desktop_generation_id=1,
    )

    intent = TargetIntent(strategy=TargetStrategy.MULTIMODAL, text="Center Label", template_id="tpl_btn")

    fusion_res = engine.fuse_multimodal_intent(snapshot, intent, ocr_result=ocr_res, visual_result=vis_res)
    assert fusion_res.status == FusionStatus.AMBIGUOUS
    assert fusion_res.fused_target is None


def test_multimodal_fusion_contradictory_channels_fail_closed():
    """When visual template and text anchor are far apart under co-location intent, fail closed with CONTRADICTORY."""
    engine = MultiModalPerceptionFusionEngine()
    snapshot = _create_test_snapshot(generation_id=1)

    v1 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=100, top=100, right=132, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_icon",
        template_name="Icon",
    )
    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[v1],
        best_match=v1,
        desktop_generation_id=1,
    )

    ocr_region = OCRTextRegion(
        text="Save",
        normalized_text="save",
        bounding_box=OCRBoundingBox(left=700, top=700, right=760, bottom=720, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        desktop_generation_id=1,
    )

    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        text="Save",
        metadata={"require_colocated": True},
    )

    fusion_res = engine.fuse_multimodal_intent(snapshot, intent, ocr_result=ocr_res, visual_result=vis_res)
    assert fusion_res.status == FusionStatus.CONTRADICTORY
    assert fusion_res.fused_target is None


def test_multimodal_fusion_stale_snapshot_rejected():
    """Stale snapshot triggers STALE_OBSERVATION fail closed."""
    engine = MultiModalPerceptionFusionEngine()
    stale_snapshot = _create_test_snapshot(generation_id=1, is_stale=True)

    intent = TargetIntent(strategy=TargetStrategy.MULTIMODAL, name="Any")
    fusion_res = engine.fuse_multimodal_intent(stale_snapshot, intent)

    assert fusion_res.status == FusionStatus.STALE_OBSERVATION


def test_multimodal_fusion_generation_mismatch_rejected():
    """Evidence with mismatched generation ID triggers STALE_OBSERVATION."""
    engine = MultiModalPerceptionFusionEngine()
    snapshot = _create_test_snapshot(generation_id=2)

    ocr_region = OCRTextRegion(
        text="Test",
        normalized_text="test",
        bounding_box=OCRBoundingBox(left=10, top=10, right=60, bottom=30, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    # OCR has generation 1, snapshot has generation 2
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        desktop_generation_id=1,
    )

    intent = TargetIntent(strategy=TargetStrategy.MULTIMODAL, text="Test")
    fusion_res = engine.fuse_multimodal_intent(snapshot, intent, ocr_result=ocr_res)

    assert fusion_res.status == FusionStatus.STALE_OBSERVATION


def test_target_locator_multimodal_strategy_resolved():
    """EvidenceBasedTargetLocator resolves MULTIMODAL strategy into a valid ResolvedTarget."""
    locator = EvidenceBasedTargetLocator()

    el = ObservedElement(
        element_id="btn_ok",
        name="OK",
        role="Button",
        control_type="Button",
        source="UIA",
        bounds=BoundingBox(left=50, top=50, width=60, height=25),
        is_enabled=True,
        is_offscreen=False,
    )
    snapshot = _create_test_snapshot(generation_id=1, elements=[el])

    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        name="OK",
    )

    res = locator.locate_target(snapshot, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.bounding_box.left == 50
    assert res.target.safe_point.x == 79
    assert res.target.safe_point.y == 62


def test_target_locator_multimodal_strategy_contradictory_fails_closed():
    """Locator propagates CONTRADICTORY status when channels disagree."""
    locator = EvidenceBasedTargetLocator()
    snapshot = _create_test_snapshot(generation_id=1)

    v1 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=100, top=100, right=130, bottom=130, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_cancel",
        template_name="Cancel",
    )
    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[v1],
        best_match=v1,
        desktop_generation_id=1,
    )

    ocr_region = OCRTextRegion(
        text="Cancel",
        normalized_text="cancel",
        bounding_box=OCRBoundingBox(left=800, top=800, right=850, bottom=820, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        desktop_generation_id=1,
    )

    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        text="Cancel",
        metadata={"ocr_result": ocr_res, "visual_match_result": vis_res, "require_colocated": True},
    )

    res = locator.locate_target(snapshot, intent)
    assert res.status == TargetResolutionStatus.CONTRADICTORY
    assert res.target is None


def test_multimodal_fusion_low_confidence_fails_closed():
    """When fused confidence is below threshold, status is LOW_CONFIDENCE."""
    engine = MultiModalPerceptionFusionEngine()
    snapshot = _create_test_snapshot(generation_id=1)

    el = ObservedElement(
        element_id="btn_low",
        name="LowConf",
        role="Button",
        control_type="Button",
        source="UIA",
        bounds=BoundingBox(left=10, top=10, width=50, height=20),
        is_enabled=True,
        is_offscreen=False,
    )
    snapshot = _create_test_snapshot(generation_id=1, elements=[el])

    policy = FusionPolicy(min_fused_confidence=0.99)  # Very high requirement
    intent = TargetIntent(strategy=TargetStrategy.MULTIMODAL, name="LowConf")
    res = engine.fuse_multimodal_intent(snapshot, intent, policy=policy)

    assert res.status == FusionStatus.LOW_CONFIDENCE
    assert res.fused_target is None


def test_multimodal_fusion_empty_evidence_not_found():
    """Empty snapshot without any matching targets returns NOT_FOUND."""
    engine = MultiModalPerceptionFusionEngine()
    snapshot = _create_test_snapshot(generation_id=1)

    intent = TargetIntent(strategy=TargetStrategy.MULTIMODAL, name="NonExistent")
    res = engine.fuse_multimodal_intent(snapshot, intent)

    assert res.status == FusionStatus.NOT_FOUND
    assert res.fused_target is None


def test_multimodal_fusion_cross_modal_requirement_enforcement():
    """When cross-modal agreement is required, single-channel detection returns LOW_CONFIDENCE."""
    engine = MultiModalPerceptionFusionEngine()
    el = ObservedElement(
        element_id="btn_single",
        name="SingleModality",
        role="Button",
        control_type="Button",
        source="UIA",
        bounds=BoundingBox(left=10, top=10, width=50, height=20),
        is_enabled=True,
        is_offscreen=False,
    )
    snapshot = _create_test_snapshot(generation_id=1, elements=[el])

    policy = FusionPolicy(require_cross_modal_agreement=True)
    intent = TargetIntent(strategy=TargetStrategy.MULTIMODAL, name="SingleModality")
    res = engine.fuse_multimodal_intent(snapshot, intent, policy=policy)

    assert res.status == FusionStatus.LOW_CONFIDENCE


def test_semantic_perception_engine_fuse_multimodal_observation():
    """SemanticPerceptionEngine.fuse_multimodal_observation delegates correctly."""
    from orbit.runtime.perception.engine import SemanticPerceptionEngine

    engine = SemanticPerceptionEngine()
    el = ObservedElement(
        element_id="btn_eng",
        name="EngineTest",
        role="Button",
        control_type="Button",
        source="UIA",
        bounds=BoundingBox(left=10, top=10, width=50, height=20),
        is_enabled=True,
        is_offscreen=False,
    )
    snapshot = _create_test_snapshot(generation_id=1, elements=[el])

    intent = TargetIntent(strategy=TargetStrategy.MULTIMODAL, name="EngineTest")
    res = engine.fuse_multimodal_observation(snapshot, intent)

    assert res.status == FusionStatus.RESOLVED
    assert res.fused_target is not None

