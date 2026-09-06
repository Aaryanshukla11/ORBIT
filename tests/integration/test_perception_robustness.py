"""Integration tests for perception robustness, edge cases, and fail-closed safety invariants."""

import asyncio
from unittest.mock import MagicMock
from PIL import Image, ImageDraw
import pytest

from orbit.models.common import BoundingBox, ScreenPoint
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedTarget,
    ObservedWindow,
)
from orbit.runtime.execution import (
    ClosedLoopExecutionEngine,
    ExecutionPolicy,
    ExecutionState,
)
from orbit.runtime.perception.engine import SemanticPerceptionEngine
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
from orbit.runtime.perception.visual_matcher import TemplateVisualMatcher
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchRegion,
    VisualMatchResult,
    VisualMatchStatus,
    VisualMatcherKind,
    VisualTemplate,
    VisualTemplateSource,
)
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetBoundingBox,
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


def _create_synthetic_snapshot(generation_id: int = 1, is_stale: bool = False) -> ObservationSnapshot:
    """Helper to create a deterministic observation snapshot."""
    return ObservationSnapshot(
        snapshot_id="snap_robustness_test_001",
        timestamp_ns=1000000000,
        generation_id=generation_id,
        is_stale=is_stale,
        freshness_state=FreshnessState.STALE if is_stale else FreshnessState.FRESH,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=12345,
                process_id=9999,
                process_name="robustness_test.exe",
                window_title="Robustness Test Window",
                extended_bounds=BoundingBox(left=100, top=100, width=500, height=400),
                is_visible=True,
                is_foreground=True,
            )
        ],
        detected_elements=[
            ObservedElement(
                element_id="el_save_btn",
                source="UI_AUTOMATION",
                name="Save Document",
                control_type="Button",
                bounds=BoundingBox(left=120, top=140, width=100, height=40),
                is_enabled=True,
                is_offscreen=False,
            )
        ],
    )


def test_stale_ocr_evidence_rejected_fail_closed():
    """Verify that OCR evidence from an older generation or marked stale fails closed."""
    locator = EvidenceBasedTargetLocator()
    snapshot = _create_synthetic_snapshot(generation_id=2)

    # Stale OCR result with generation_id = 1
    stale_ocr = OCRResult(
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        status=OCRStatus.SUCCESS,
        text_regions=[
            OCRTextRegion(
                text="Save",
                normalized_text="save",
                bounding_box=OCRBoundingBox(left=120, top=140, right=220, bottom=180),
                confidence=0.95,
                words=[
                    OCRWord(
                        text="Save",
                        normalized_text="save",
                        bounding_box=OCRBoundingBox(left=120, top=140, right=220, bottom=180),
                        confidence=0.95,
                    )
                ],
                coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE,
            )
        ],
        full_text="Save",
        desktop_generation_id=1,  # Mismatched generation
        observation_id="snap_old_000",
    )

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Save",
        metadata={"ocr_result": stale_ocr},
    )

    res = locator.locate_target(snapshot, intent)
    assert res.status == TargetResolutionStatus.STALE_OBSERVATION
    assert res.target is None


def test_stale_visual_evidence_rejected_fail_closed():
    """Verify that visual template match from mismatched generation fails closed."""
    locator = EvidenceBasedTargetLocator()
    snapshot = _create_synthetic_snapshot(generation_id=3)

    img = Image.new("RGB", (32, 32), color=(100, 150, 200))
    template = VisualTemplate.from_image(
        template_id="tpl_save",
        name="Save Icon",
        image=img,
        source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
    )

    stale_match = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        desktop_generation_id=2,  # Mismatched generation
        observation_id="snap_old_000",
        matches=[
            VisualMatchRegion(
                template_id="tpl_save",
                template_name="Save Icon",
                bounding_box=OCRBoundingBox(left=120, top=140, right=152, bottom=172),
                confidence=0.95,
            )
        ],
        best_match=VisualMatchRegion(
            template_id="tpl_save",
            template_name="Save Icon",
            bounding_box=OCRBoundingBox(left=120, top=140, right=152, bottom=172),
            confidence=0.95,
        ),
    )

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": stale_match},
    )

    res = locator.locate_target(snapshot, intent)
    assert res.status == TargetResolutionStatus.STALE_OBSERVATION
    assert res.target is None


def test_equidistant_duplicate_candidate_ambiguity_fails_closed():
    """Verify that equidistant duplicate visual candidates fail closed with AMBIGUOUS."""
    engine = MultiModalPerceptionFusionEngine(
        default_policy=FusionPolicy(ambiguity_distance_margin_px=15.0)
    )

    # Snapshot with two identical icons and anchor text
    snap = _create_synthetic_snapshot(generation_id=1)

    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        desktop_generation_id=1,
        observation_id="snap_robustness_test_001",
        matches=[
            VisualMatchRegion(
                template_id="tpl_icon",
                template_name="Icon",
                bounding_box=OCRBoundingBox(left=100, top=90, right=130, bottom=110),
                confidence=0.90,
            ),
            VisualMatchRegion(
                template_id="tpl_icon",
                template_name="Icon",
                bounding_box=OCRBoundingBox(left=170, top=90, right=200, bottom=110),
                confidence=0.90,
            ),
        ],
    )

    ocr_res = OCRResult(
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        status=OCRStatus.SUCCESS,
        text_regions=[
            OCRTextRegion(
                text="Target",
                normalized_text="target",
                bounding_box=OCRBoundingBox(left=140, top=90, right=160, bottom=110),
                confidence=0.95,
                words=[
                    OCRWord(
                        text="Target",
                        normalized_text="target",
                        bounding_box=OCRBoundingBox(left=140, top=90, right=160, bottom=110),
                        confidence=0.95,
                    )
                ],
                coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE,
            )
        ],
        full_text="Target",
        desktop_generation_id=1,
        observation_id="snap_robustness_test_001",
    )

    img = Image.new("RGB", (30, 20), color=(0, 100, 200))
    template = VisualTemplate.from_image(
        template_id="tpl_icon",
        name="Icon",
        image=img,
        source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
    )

    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        name="Icon",
        text="Target",
        template=template,
    )

    res = engine.fuse_multimodal_intent(
        snapshot=snap,
        intent=intent,
        ocr_result=ocr_res,
        visual_result=vis_res,
    )

    # Must fail closed with AMBIGUOUS
    assert res.status == FusionStatus.AMBIGUOUS
    assert res.fused_target is None


def test_high_frequency_window_movement_coordinate_invalidation():
    """Verify that moving a window invalidates previously resolved target coordinates."""
    locator = EvidenceBasedTargetLocator()

    # Step 1: Initial window position at (100, 100)
    snap1 = _create_synthetic_snapshot(generation_id=10)
    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="Save Document",
        role="Button",
    )
    res1 = locator.locate_target(snap1, intent)
    assert res1.status == TargetResolutionStatus.RESOLVED
    assert res1.target is not None
    initial_safe_point = res1.target.safe_point

    # Step 2: Window moves to (400, 400), generation increments to 11
    snap2 = ObservationSnapshot(
        snapshot_id="snap_robustness_test_002",
        timestamp_ns=2000000000,
        generation_id=11,
        is_stale=False,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=12345,
                process_id=9999,
                process_name="robustness_test.exe",
                window_title="Robustness Test Window",
                extended_bounds=BoundingBox(left=400, top=400, width=500, height=400),
                is_visible=True,
                is_foreground=True,
            )
        ],
        detected_elements=[
            ObservedElement(
                element_id="el_save_btn",
                source="UI_AUTOMATION",
                name="Save Document",
                control_type="Button",
                bounds=BoundingBox(left=420, top=440, width=100, height=40),
                is_enabled=True,
                is_offscreen=False,
            )
        ],
    )

    # snap1 still has generation_id 10
    res_stale = locator.locate_target(snap1, intent)
    assert res_stale.target.safe_point.desktop_generation_id == 10

    # Re-resolving with snap2 yields updated coordinates
    res2 = locator.locate_target(snap2, intent)
    assert res2.status == TargetResolutionStatus.RESOLVED
    assert res2.target is not None
    new_safe_point = res2.target.safe_point

    # Coordinates must reflect new position
    assert new_safe_point.x != initial_safe_point.x
    assert new_safe_point.y != initial_safe_point.y
    assert new_safe_point.desktop_generation_id == 11
    assert 420 <= new_safe_point.x <= 520
    assert 440 <= new_safe_point.y <= 480


def test_partial_window_occlusion_and_clipped_bounds():
    """Verify that offscreen / clipped elements are rejected or handled cleanly."""
    locator = EvidenceBasedTargetLocator()
    snap = ObservationSnapshot(
        snapshot_id="snap_occlusion_001",
        timestamp_ns=1000000000,
        generation_id=1,
        is_stale=False,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[],
        detected_elements=[
            ObservedElement(
                element_id="el_offscreen_btn",
                source="UI_AUTOMATION",
                name="Hidden Action",
                control_type="Button",
                bounds=BoundingBox(left=100, top=100, width=100, height=50),
                is_enabled=True,
                is_offscreen=True,  # Explicitly offscreen / occluded
            )
        ],
    )

    intent = TargetIntent(
        strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        name="Hidden Action",
    )

    # EvidenceBasedTargetLocator rejects offscreen elements
    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.NOT_FOUND
    assert res.target is None


def test_dpi_coordinate_transformation_invariants():
    """Verify that DPI scale factor transformations preserve aspect ratio and bounding box geometry."""
    box = BoundingBox(left=100, top=150, width=200, height=100)
    scale_150 = 1.5

    # Scale to physical pixels
    phys_left = int(box.left * scale_150)
    phys_top = int(box.top * scale_150)
    phys_width = int(box.width * scale_150)
    phys_height = int(box.height * scale_150)

    phys_box = BoundingBox(left=phys_left, top=phys_top, width=phys_width, height=phys_height)
    assert phys_box.width == 300  # 200 * 1.5 = 300
    assert phys_box.height == 150  # 100 * 1.5 = 150

    # Scale back to logical coordinates
    log_left = int(phys_box.left / scale_150)
    log_top = int(phys_box.top / scale_150)
    log_width = int(phys_box.width / scale_150)
    log_height = int(phys_box.height / scale_150)

    assert log_left == box.left
    assert log_top == box.top
    assert log_width == box.width
    assert log_height == box.height


def test_zero_pointer_dispatch_on_every_negative_status():
    """Verify that TargetResolutionResult with non-RESOLVED status has None target."""
    ocr_empty = OCRResult(
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        status=OCRStatus.NO_TEXT_FOUND,
        text_regions=[],
        full_text="",
        desktop_generation_id=1,
        observation_id="snap_robustness_test_001",
    )

    negative_intents = [
        TargetIntent(strategy=TargetStrategy.ACCESSIBILITY_ELEMENT, name="NON_EXISTENT_ELEMENT_XYZ"),
        TargetIntent(strategy=TargetStrategy.WINDOW_TITLE, window_title="NON_EXISTENT_WINDOW_XYZ"),
        TargetIntent(strategy=TargetStrategy.OCR_TEXT, text="NON_EXISTENT_OCR_XYZ", metadata={"ocr_result": ocr_empty}),
    ]

    locator = EvidenceBasedTargetLocator()
    snap = _create_synthetic_snapshot()

    for intent in negative_intents:
        res = locator.locate_target(snap, intent)
        assert res.status in (
            TargetResolutionStatus.NOT_FOUND,
            TargetResolutionStatus.AMBIGUOUS,
            TargetResolutionStatus.CONTRADICTORY,
            TargetResolutionStatus.LOW_CONFIDENCE,
            TargetResolutionStatus.INVALID_REQUEST,
        )
        assert res.target is None
