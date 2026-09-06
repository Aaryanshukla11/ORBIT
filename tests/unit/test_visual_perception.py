"""Unit tests for ORBIT visual template perception, matching engine, and target resolution."""

import pytest
from datetime import datetime, timezone
import numpy as np
from PIL import Image, ImageDraw

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
)
from orbit.models.common import BoundingBox
from orbit.runtime.perception.coordinate_mapper import OCRCoordinateMapper
from orbit.runtime.perception.models import OCRBoundingBox, OCRCoordinateSpace
from orbit.runtime.perception.visual_engine import VisualPerceptionEngine
from orbit.runtime.perception.visual_matcher import (
    MockVisualMatcher,
    TemplateVisualMatcher,
)
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchRegion,
    VisualMatchResult,
    VisualMatchStatus,
    VisualMatcherKind,
    VisualTemplate,
    VisualTemplateSource,
)
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


def _create_test_snapshot(
    snapshot_id: str = "snap_vis_001",
    generation_id: int = 1,
    is_stale: bool = False,
    freshness_state: FreshnessState = FreshnessState.FRESH,
    screenshot_image: Image.Image | None = None,
) -> ObservationSnapshot:
    snap = ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=generation_id,
        timestamp_ns=1000000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=freshness_state,
        is_stale=is_stale,
    )
    if screenshot_image is not None:
        snap.telemetry["screenshot"] = screenshot_image
    return snap


def _generate_synthetic_scene_and_icon(
    scene_size: tuple[int, int] = (600, 400),
    icon_pos: tuple[int, int] = (250, 150),
    icon_size: tuple[int, int] = (40, 40),
) -> tuple[Image.Image, Image.Image]:
    """Render a synthetic desktop scene with a distinct high-contrast icon."""
    scene = Image.new("RGB", scene_size, color=(240, 240, 245))
    draw_scene = ImageDraw.Draw(scene)
    draw_scene.rectangle([50, 50, 550, 350], fill=(255, 255, 255), outline=(180, 180, 180))

    # Render distinct icon pattern
    ix, iy = icon_pos
    iw, ih = icon_size
    draw_scene.rectangle([ix, iy, ix + iw, iy + ih], fill=(0, 120, 215))
    draw_scene.polygon([(ix + 10, iy + 30), (ix + 20, iy + 10), (ix + 30, iy + 30)], fill=(255, 255, 255))

    # Crop the exact template
    icon_tpl = scene.crop((ix, iy, ix + iw, iy + ih))
    return scene, icon_tpl


# --- 1. VisualTemplate Validation & Provenance Tests ---

def test_visual_template_creation_and_checksum():
    _, icon_img = _generate_synthetic_scene_and_icon()
    tpl = VisualTemplate.from_image(
        template_id="tpl_search_01",
        name="Search Icon",
        image=icon_img,
        source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
        semantic_intent="Search input button",
    )

    assert tpl.template_id == "tpl_search_01"
    assert tpl.name == "Search Icon"
    assert tpl.width == 40
    assert tpl.height == 40
    assert tpl.is_valid is True
    assert tpl.source == VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE
    assert tpl.checksum is not None
    assert len(tpl.checksum) == 64  # SHA-256


def test_visual_template_registry_lifecycle():
    engine = VisualPerceptionEngine()
    _, icon_img = _generate_synthetic_scene_and_icon()
    tpl = VisualTemplate.from_image("tpl_gear_01", "Settings Gear", icon_img)

    assert engine.register_template(tpl) is True
    assert engine.get_template("tpl_gear_01") == tpl
    assert len(engine.list_templates()) == 1

    assert engine.unregister_template("tpl_gear_01") is True
    assert engine.get_template("tpl_gear_01") is None


# --- 2. Deterministic TemplateVisualMatcher Tests ---

@pytest.mark.asyncio
async def test_template_matcher_exact_match_success():
    scene, icon_tpl = _generate_synthetic_scene_and_icon(icon_pos=(200, 120))
    template = VisualTemplate.from_image("tpl_icon_01", "Test Icon", icon_tpl)

    matcher = TemplateVisualMatcher()
    policy = VisualMatchPolicy(minimum_confidence=0.85)

    res = await matcher.match(template=template, image=scene, policy=policy, desktop_generation_id=1)
    assert res.status == VisualMatchStatus.MATCHED
    assert res.is_success is True
    assert res.best_match is not None
    assert res.best_match.confidence >= 0.90
    assert abs(res.best_match.bounding_box.left - 200) <= 2
    assert abs(res.best_match.bounding_box.top - 120) <= 2
    assert res.best_match.bounding_box.width == 40
    assert res.best_match.bounding_box.height == 40


@pytest.mark.asyncio
async def test_template_matcher_no_match():
    scene, _ = _generate_synthetic_scene_and_icon()
    # Create completely unrelated icon (e.g. solid black box with red circle)
    unrelated_icon = Image.new("RGB", (40, 40), color=(0, 0, 0))
    draw = ImageDraw.Draw(unrelated_icon)
    draw.ellipse([5, 5, 35, 35], fill=(255, 0, 0))

    template = VisualTemplate.from_image("tpl_unrelated", "Unrelated Icon", unrelated_icon)
    matcher = TemplateVisualMatcher()
    policy = VisualMatchPolicy(minimum_confidence=0.85)

    res = await matcher.match(template=template, image=scene, policy=policy)
    assert res.status in (VisualMatchStatus.NOT_FOUND, VisualMatchStatus.LOW_CONFIDENCE)
    assert res.is_success is False
    assert res.best_match is None


@pytest.mark.asyncio
async def test_template_matcher_duplicate_ambiguity_fails_closed():
    # Scene with TWO identical icons
    scene = Image.new("RGB", (800, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(scene)

    # Icon 1 at (100, 100)
    draw.rectangle([100, 100, 140, 140], fill=(0, 120, 215))
    draw.polygon([(110, 130), (120, 110), (130, 130)], fill=(255, 255, 255))

    # Icon 2 at (500, 100)
    draw.rectangle([500, 100, 540, 140], fill=(0, 120, 215))
    draw.polygon([(510, 130), (520, 110), (530, 130)], fill=(255, 255, 255))

    icon_tpl = scene.crop((100, 100, 140, 140))
    template = VisualTemplate.from_image("tpl_dup", "Duplicate Icon", icon_tpl)

    matcher = TemplateVisualMatcher()
    policy = VisualMatchPolicy(minimum_confidence=0.85, ambiguity_margin=0.05)

    res = await matcher.match(template=template, image=scene, policy=policy)
    assert res.status == VisualMatchStatus.AMBIGUOUS
    assert res.is_success is False
    assert res.best_match is None
    assert len(res.matches) >= 2


@pytest.mark.asyncio
async def test_template_matcher_invalid_image_dimensions():
    matcher = TemplateVisualMatcher()
    # Template larger than search image
    small_scene = Image.new("RGB", (30, 30), color=(255, 255, 255))
    large_icon = Image.new("RGB", (100, 100), color=(0, 0, 0))
    template = VisualTemplate.from_image("tpl_large", "Large Icon", large_icon)

    res = await matcher.match(template=template, image=small_scene)
    assert res.status == VisualMatchStatus.NOT_FOUND
    assert res.is_success is False


# --- 3. VisualPerceptionEngine Integration Tests ---

@pytest.mark.asyncio
async def test_visual_engine_stale_snapshot_rejected():
    engine = VisualPerceptionEngine()
    scene, icon_tpl = _generate_synthetic_scene_and_icon()
    template = VisualTemplate.from_image("tpl_test", "Test Icon", icon_tpl)

    stale_snap = _create_test_snapshot(is_stale=True, freshness_state=FreshnessState.STALE, screenshot_image=scene)
    res = await engine.find_template(stale_snap, template)

    assert res.status == VisualMatchStatus.STALE_OBSERVATION
    assert res.is_success is False


# --- 4. Target Locator VISUAL_TEMPLATE Strategy Tests ---

def test_target_locator_visual_template_resolution_success():
    scene, icon_tpl = _generate_synthetic_scene_and_icon(icon_pos=(300, 200))
    template = VisualTemplate.from_image("tpl_btn", "Button Icon", icon_tpl)

    match_region = VisualMatchRegion(
        template_id="tpl_btn",
        template_name="Button Icon",
        bounding_box=OCRBoundingBox(left=300, top=200, right=340, bottom=240),
        confidence=0.96,
        scale_factor=1.0,
    )
    match_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id="tpl_btn",
        observation_id="snap_vis_001",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1, screenshot_image=scene)

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": match_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.bounding_box.left == 300
    assert res.target.bounding_box.top == 200
    assert res.target.bounding_box.width == 40
    assert res.target.bounding_box.height == 40
    assert res.target.confidence == 0.96
    assert res.target.evidence.source == "VISUAL_TEMPLATE"
    assert res.target.evidence.name == "Button Icon"


def test_target_locator_visual_template_ambiguous_fails_closed():
    m1 = VisualMatchRegion(
        template_id="tpl_dup",
        template_name="Dup Icon",
        bounding_box=OCRBoundingBox(left=100, top=100, right=140, bottom=140),
        confidence=0.95,
    )
    m2 = VisualMatchRegion(
        template_id="tpl_dup",
        template_name="Dup Icon",
        bounding_box=OCRBoundingBox(left=500, top=100, right=540, bottom=140),
        confidence=0.94,
    )
    match_result = VisualMatchResult(
        status=VisualMatchStatus.AMBIGUOUS,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[m1, m2],
        best_match=None,
        template_id="tpl_dup",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1)

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template_id="tpl_dup",
        metadata={"visual_match_result": match_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.AMBIGUOUS
    assert res.target is None
    assert res.candidates_count == 2


def test_target_locator_visual_template_generation_mismatch_fails_closed():
    match_region = VisualMatchRegion(
        template_id="tpl_btn",
        template_name="Button Icon",
        bounding_box=OCRBoundingBox(left=300, top=200, right=340, bottom=240),
        confidence=0.95,
    )
    # Match under generation 1
    match_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id="tpl_btn",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    # Active snapshot is at generation 2
    snap_gen2 = _create_test_snapshot(generation_id=2)

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template_id="tpl_btn",
        metadata={"visual_match_result": match_result},
    )

    res = locator.locate_target(snap_gen2, intent)
    assert res.status == TargetResolutionStatus.STALE_OBSERVATION
    assert res.is_stale_observation is True
    assert res.target is None


# --- 5. Extended Edge Case & Safety Unit Tests ---

@pytest.mark.asyncio
async def test_template_matcher_near_equal_ambiguity():
    # Two slightly different icons that both score high (>0.90) but within margin 0.05
    scene = Image.new("RGB", (800, 400), color=(240, 240, 245))
    draw = ImageDraw.Draw(scene)

    # Icon 1 at (100, 100)
    draw.rectangle([100, 100, 140, 140], fill=(0, 120, 215))
    draw.polygon([(110, 130), (120, 110), (130, 130)], fill=(255, 255, 255))

    # Icon 2 at (500, 100) with 1 pixel line added (near identical)
    draw.rectangle([500, 100, 540, 140], fill=(0, 120, 215))
    draw.polygon([(510, 130), (520, 110), (530, 130)], fill=(255, 255, 255))
    draw.line([(500, 100), (540, 100)], fill=(255, 255, 0), width=1)

    icon_tpl = scene.crop((100, 100, 140, 140))
    template = VisualTemplate.from_image("tpl_near", "Near Icon", icon_tpl)

    matcher = TemplateVisualMatcher()
    policy = VisualMatchPolicy(minimum_confidence=0.80, ambiguity_margin=0.10)

    res = await matcher.match(template=template, image=scene, policy=policy)
    assert res.status == VisualMatchStatus.AMBIGUOUS
    assert res.best_match is None


@pytest.mark.asyncio
async def test_template_matcher_zero_variance_solid_template():
    scene, _ = _generate_synthetic_scene_and_icon()
    solid_icon = Image.new("RGB", (40, 40), color=(255, 255, 255))
    template = VisualTemplate.from_image("tpl_solid", "Solid Icon", solid_icon)

    matcher = TemplateVisualMatcher()
    res = await matcher.match(template=template, image=scene)
    assert res.status == VisualMatchStatus.NOT_FOUND
    assert res.best_match is None


def test_visual_coordinate_mapping_dpi_scaling():
    mapper = OCRCoordinateMapper()
    # Logical DPI bbox (at 1.5x DPI scale factor) with screenshot offset (1920, 0)
    logical_bbox = OCRBoundingBox(
        left=200,
        top=100,
        right=240,
        bottom=140,
        coordinate_space=OCRCoordinateSpace.LOGICAL_DPI_SPACE,
    )
    result = mapper.map_to_virtual_desktop(
        box=logical_bbox,
        dpi_scale_factor=1.5,
        screenshot_offset_x=1920,
        screenshot_offset_y=0,
    )

    assert result.is_valid is True
    assert result.mapped_box is not None
    # Expected: (200 * 1.5) + 1920 = 300 + 1920 = 2220
    # Expected: (100 * 1.5) + 0 = 150
    # Width: 40 * 1.5 = 60
    # Height: 40 * 1.5 = 60
    assert result.mapped_box.left == 2220
    assert result.mapped_box.top == 150
    assert result.mapped_box.width == 60
    assert result.mapped_box.height == 60
    assert result.mapped_box.coordinate_space == OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE


@pytest.mark.asyncio
async def test_visual_matching_deterministic_repeatability():
    scene, icon_tpl = _generate_synthetic_scene_and_icon(icon_pos=(180, 220))
    template = VisualTemplate.from_image("tpl_rep", "Repeat Icon", icon_tpl)
    matcher = TemplateVisualMatcher()
    policy = VisualMatchPolicy(minimum_confidence=0.90)

    results = []
    for _ in range(3):
        r = await matcher.match(template=template, image=scene, policy=policy, desktop_generation_id=1)
        results.append(r)

    # All runs must produce identical results
    assert all(r.status == VisualMatchStatus.MATCHED for r in results)
    assert all(r.best_match.bounding_box.left == 180 for r in results)
    assert all(r.best_match.bounding_box.top == 220 for r in results)
    assert len(set(r.best_match.confidence for r in results)) == 1


@pytest.mark.asyncio
async def test_multimodal_visual_and_ocr_fusion_disambiguation():
    """Test that multimodal fusion resolves an ambiguous icon by using nearby OCR text."""
    # Scene with TWO identical gear icons: one at (100, 100) next to 'Settings', one at (500, 100) next to 'Tools'
    scene = Image.new("RGB", (800, 400), color=(240, 240, 245))
    draw = ImageDraw.Draw(scene)

    # Gear 1 at (100, 100)
    draw.rectangle([100, 100, 140, 140], fill=(0, 120, 215))
    draw.ellipse([110, 110, 130, 130], fill=(255, 255, 255))
    draw.ellipse([115, 115, 125, 125], fill=(0, 120, 215))

    # Gear 2 at (500, 100)
    draw.rectangle([500, 100, 540, 140], fill=(0, 120, 215))
    draw.ellipse([510, 110, 530, 130], fill=(255, 255, 255))
    draw.ellipse([515, 115, 525, 125], fill=(0, 120, 215))

    icon_tpl = scene.crop((100, 100, 140, 140))
    template = VisualTemplate.from_image("tpl_gear", "Gear Icon", icon_tpl)

    # Mock OCR returning 'Settings' text next to Gear 1 (at 150, 110)
    from orbit.runtime.perception.models import OCRResult, OCRStatus, OCRTextRegion, OCRProviderKind
    from orbit.runtime.perception.ocr import MockOCRProvider
    from orbit.runtime.perception.engine import SemanticPerceptionEngine

    ocr_region = OCRTextRegion(
        text="Settings",
        normalized_text="settings",
        bounding_box=OCRBoundingBox(left=150, top=105, right=230, bottom=135),
        words=[],
        confidence=0.99,
        source_provider="MOCK",
    )
    mock_ocr = MockOCRProvider(injected_regions=[ocr_region])
    engine = SemanticPerceptionEngine(ocr_provider=mock_ocr)

    snap = _create_test_snapshot(screenshot_image=scene)

    # Run find_template_near_text anchored to 'Settings'
    res = await engine.find_template_near_text(
        snapshot=snap,
        template=template,
        text_label="Settings",
        image=scene,
        max_distance_px=100.0,
    )

    # Multimodal fusion MUST resolve the Gear 1 at (100, 100) and ignore the ambiguous Gear 2 at (500, 100)
    assert res.status == VisualMatchStatus.MATCHED
    assert res.best_match is not None
    assert abs(res.best_match.bounding_box.left - 100) <= 2
    assert abs(res.best_match.bounding_box.top - 100) <= 2


def test_target_locator_icon_template_strategy_support():
    scene, icon_tpl = _generate_synthetic_scene_and_icon(icon_pos=(300, 200))
    template = VisualTemplate.from_image("tpl_icon_strategy", "Icon Strategy", icon_tpl)

    match_region = VisualMatchRegion(
        template_id="tpl_icon_strategy",
        template_name="Icon Strategy",
        bounding_box=OCRBoundingBox(left=300, top=200, right=340, bottom=240),
        confidence=0.95,
    )
    match_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id="tpl_icon_strategy",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1, screenshot_image=scene)

    intent = TargetIntent(
        strategy=TargetStrategy.ICON_TEMPLATE,
        template=template,
        metadata={"visual_match_result": match_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.bounding_box.left == 300
    assert res.target.bounding_box.top == 200


