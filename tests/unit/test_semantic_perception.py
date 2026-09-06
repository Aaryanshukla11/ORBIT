"""Unit tests for ORBIT semantic perception, OCR models, coordinate mapping, and target resolution."""

import pytest
from datetime import datetime, timezone
from PIL import Image

from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
)
from orbit.models.common import BoundingBox
from orbit.runtime.perception.coordinate_mapper import (
    CoordinateMappingResult,
    OCRCoordinateMapper,
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
from orbit.runtime.perception.normalization import (
    matches_text,
    normalize_text,
    tokenize_text,
)
from orbit.runtime.perception.ocr import (
    MockOCRProvider,
    WindowsNativeOCRProvider,
)
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


def _create_test_snapshot(
    snapshot_id: str = "snap_test_001",
    generation_id: int = 1,
    is_stale: bool = False,
    freshness_state: FreshnessState = FreshnessState.FRESH,
) -> ObservationSnapshot:
    return ObservationSnapshot(
        snapshot_id=snapshot_id,
        generation_id=generation_id,
        timestamp_ns=1000000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=freshness_state,
        is_stale=is_stale,
    )


# --- 1. OCRBoundingBox & Coordinate Space Unit Tests ---

def test_ocr_bounding_box_geometry_and_validation():
    box = OCRBoundingBox(
        left=100,
        top=200,
        right=300,
        bottom=400,
        coordinate_space=OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE,
    )
    assert box.width == 200
    assert box.height == 200
    assert box.area == 40000
    assert box.is_valid is True
    assert box.center == (200, 300)
    assert box.coordinate_space == OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE

    # Convert to canonical BoundingBox
    canon = box.to_bounding_box()
    assert canon.left == 100
    assert canon.top == 200
    assert canon.width == 200
    assert canon.height == 200

    # Inverted box fails validation
    invalid_box = OCRBoundingBox(left=300, top=400, right=100, bottom=200)
    assert invalid_box.is_valid is False


def test_ocr_bounding_box_negative_virtual_desktop_coordinates():
    box = OCRBoundingBox(left=-1920, top=-500, right=-1000, bottom=-100)
    assert box.width == 920
    assert box.height == 400
    assert box.area == 368000
    assert box.is_valid is True
    assert box.center == (-1460, -300)


def test_ocr_bounding_box_from_rect_with_offset():
    box = OCRBoundingBox.from_rect(10.2, 20.8, 100.4, 50.1, offset_x=500, offset_y=300)
    assert box.left == 510
    assert box.top == 321
    assert box.right == 611
    assert box.bottom == 371
    assert box.is_valid is True


# --- 2. OCRCoordinateMapper Unit Tests ---

def test_coordinate_mapper_screenshot_pixel_space_transformation():
    mapper = OCRCoordinateMapper()
    box = OCRBoundingBox(
        left=50,
        top=80,
        right=250,
        bottom=180,
        coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE,
    )

    res = mapper.map_to_virtual_desktop(box, screenshot_offset_x=1920, screenshot_offset_y=100)
    assert res.is_valid is True
    assert res.status == OCRStatus.SUCCESS
    assert res.mapped_box is not None
    assert res.mapped_box.coordinate_space == OCRCoordinateSpace.VIRTUAL_DESKTOP_SPACE
    assert res.mapped_box.left == 1970
    assert res.mapped_box.top == 180
    assert res.mapped_box.right == 2170
    assert res.mapped_box.bottom == 280
    assert res.mapped_box.width == 200
    assert res.mapped_box.height == 100


def test_coordinate_mapper_window_client_space_transformation():
    mapper = OCRCoordinateMapper()
    box = OCRBoundingBox(
        left=20,
        top=30,
        right=120,
        bottom=70,
        coordinate_space=OCRCoordinateSpace.WINDOW_CLIENT_SPACE,
    )

    # Success when window origins provided
    res = mapper.map_to_virtual_desktop(box, window_origin_x=400, window_origin_y=300)
    assert res.is_valid is True
    assert res.status == OCRStatus.SUCCESS
    assert res.mapped_box is not None
    assert res.mapped_box.left == 420
    assert res.mapped_box.top == 330
    assert res.mapped_box.right == 520
    assert res.mapped_box.bottom == 370

    # Fail closed when window origins omitted
    res_fail = mapper.map_to_virtual_desktop(box, window_origin_x=None, window_origin_y=None)
    assert res_fail.is_valid is False
    assert res_fail.status == OCRStatus.COORDINATE_MAPPING_FAILED


def test_coordinate_mapper_logical_dpi_space_transformation():
    mapper = OCRCoordinateMapper()
    box = OCRBoundingBox(
        left=100,
        top=100,
        right=200,
        bottom=200,
        coordinate_space=OCRCoordinateSpace.LOGICAL_DPI_SPACE,
    )

    # 1.5x DPI Scaling
    res = mapper.map_to_virtual_desktop(box, dpi_scale_factor=1.5, screenshot_offset_x=100, screenshot_offset_y=50)
    assert res.is_valid is True
    assert res.status == OCRStatus.SUCCESS
    assert res.mapped_box is not None
    assert res.mapped_box.left == 250
    assert res.mapped_box.top == 200
    assert res.mapped_box.right == 400
    assert res.mapped_box.bottom == 350


def test_coordinate_mapper_invalid_geometry_fails_closed():
    mapper = OCRCoordinateMapper()
    # Inverted box
    inv_box = OCRBoundingBox(
        left=200,
        top=200,
        right=100,
        bottom=100,
        coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE,
    )
    res = mapper.map_to_virtual_desktop(inv_box)
    assert res.is_valid is False
    assert res.status == OCRStatus.COORDINATE_MAPPING_FAILED

    # Zero area box
    zero_box = OCRBoundingBox(
        left=100,
        top=100,
        right=100,
        bottom=200,
        coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE,
    )
    res_zero = mapper.map_to_virtual_desktop(zero_box)
    assert res_zero.is_valid is False
    assert res_zero.status == OCRStatus.COORDINATE_MAPPING_FAILED


# --- 3. Normalization Unit Tests ---

def test_text_normalization_unicode_and_whitespace():
    # Empty / None handling
    assert normalize_text(None) == ""
    assert normalize_text("") == ""

    # Whitespace collapsing & trimming
    raw = "   Save   \n\t  File   As...   "
    assert normalize_text(raw, case_fold=False) == "Save File As..."
    assert normalize_text(raw, case_fold=True) == "save file as..."

    # Unicode normalization (e.g. fullwidth characters canonicalized)
    fullwidth = "Ｓｅｔｔｉｎｇｓ"
    assert normalize_text(fullwidth, case_fold=True) == "settings"


def test_matches_text_exact_and_substring():
    candidate = "Confirm Save Changes"

    # Exact match
    assert matches_text(candidate, "Confirm Save Changes", exact_match=True) is True
    assert matches_text(candidate, "confirm save changes", exact_match=True, case_sensitive=False) is True
    assert matches_text(candidate, "confirm save changes", exact_match=True, case_sensitive=True) is False
    assert matches_text(candidate, "Save", exact_match=True) is False

    # Substring match
    assert matches_text(candidate, "Save", exact_match=False) is True
    assert matches_text(candidate, "save", exact_match=False, case_sensitive=False) is True
    assert matches_text(candidate, "save", exact_match=False, case_sensitive=True) is False
    assert matches_text(candidate, "Cancel", exact_match=False) is False


def test_tokenize_text():
    tokens = tokenize_text("  Open   Notepad.exe  Now! ")
    assert tokens == ["open", "notepad.exe", "now!"]


# --- 4. OCRProvider & Status Modeling Tests ---

@pytest.mark.asyncio
async def test_mock_ocr_provider_success_flow():
    word1 = OCRWord(
        text="Open",
        normalized_text="open",
        bounding_box=OCRBoundingBox(left=10, top=10, right=50, bottom=30),
    )
    word2 = OCRWord(
        text="File",
        normalized_text="file",
        bounding_box=OCRBoundingBox(left=60, top=10, right=100, bottom=30),
    )
    region = OCRTextRegion(
        text="Open File",
        normalized_text="open file",
        bounding_box=OCRBoundingBox(left=10, top=10, right=100, bottom=30),
        words=[word1, word2],
    )

    provider = MockOCRProvider(injected_regions=[region])
    assert provider.is_available() is True
    assert provider.provider_kind == OCRProviderKind.MOCK

    img = Image.new("RGB", (200, 100))
    res = await provider.extract_text(img, desktop_generation_id=2, observation_id="snap_123")

    assert res.status == OCRStatus.SUCCESS
    assert res.is_success is True
    assert res.has_text is True
    assert res.desktop_generation_id == 2
    assert res.observation_id == "snap_123"
    assert len(res.text_regions) == 1
    assert res.text_regions[0].text == "Open File"


@pytest.mark.asyncio
async def test_mock_ocr_provider_statuses():
    # Unsupported provider
    unavail_provider = MockOCRProvider(is_available_flag=False)
    assert unavail_provider.is_available() is False
    img = Image.new("RGB", (100, 100))
    res_unavail = await unavail_provider.extract_text(img)
    assert res_unavail.status == OCRStatus.UNSUPPORTED

    # Failed provider
    failed_provider = MockOCRProvider(injected_status=OCRStatus.FAILED)
    res_failed = await failed_provider.extract_text(img)
    assert res_failed.status == OCRStatus.FAILED
    assert res_failed.is_success is False

    # No text detected
    empty_provider = MockOCRProvider(injected_regions=[])
    res_empty = await empty_provider.extract_text(img)
    assert res_empty.status in (OCRStatus.NO_TEXT, OCRStatus.NO_TEXT_FOUND)
    assert res_empty.has_text is False


# --- 5. SemanticPerceptionEngine Unit Tests ---

@pytest.mark.asyncio
async def test_semantic_perception_engine_stale_observation_rejected():
    provider = MockOCRProvider()
    engine = SemanticPerceptionEngine(ocr_provider=provider)

    snap_stale = _create_test_snapshot(is_stale=True, freshness_state=FreshnessState.STALE)
    img = Image.new("RGB", (100, 100))

    result = await engine.scan_observation(snap_stale, image=img)
    assert result.status == OCRStatus.STALE_OBSERVATION
    assert result.is_success is False
    assert result.desktop_generation_id == snap_stale.generation_id


@pytest.mark.asyncio
async def test_semantic_perception_engine_find_text_regions():
    word1 = OCRWord(
        text="Submit",
        normalized_text="submit",
        bounding_box=OCRBoundingBox(left=50, top=50, right=120, bottom=80),
    )
    region1 = OCRTextRegion(
        text="Submit Form",
        normalized_text="submit form",
        bounding_box=OCRBoundingBox(left=50, top=50, right=200, bottom=80),
        words=[word1],
    )
    region2 = OCRTextRegion(
        text="Cancel",
        normalized_text="cancel",
        bounding_box=OCRBoundingBox(left=220, top=50, right=300, bottom=80),
        words=[],
    )

    provider = MockOCRProvider(injected_regions=[region1, region2])
    engine = SemanticPerceptionEngine(ocr_provider=provider)

    snap = _create_test_snapshot()
    img = Image.new("RGB", (500, 200))
    scan_res = await engine.scan_observation(snap, image=img)

    # Line match
    matches_line = engine.find_text_regions(scan_res, "Submit Form", exact_match=True)
    assert len(matches_line) == 1
    assert matches_line[0].text == "Submit Form"

    # Word match
    matches_word = engine.find_text_regions(scan_res, "Submit", exact_match=True)
    assert len(matches_word) == 1
    assert matches_word[0].text == "Submit"
    assert matches_word[0].bounding_box.left == 50

    # Substring match
    matches_sub = engine.find_text_regions(scan_res, "form", exact_match=False)
    assert len(matches_sub) == 1
    assert matches_sub[0].text == "Submit Form"

    # No match
    matches_none = engine.find_text_regions(scan_res, "Delete", exact_match=True)
    assert len(matches_none) == 0


# --- 6. Target Locator OCR_TEXT Strategy Unit Tests ---

def test_target_locator_ocr_text_resolution_success():
    region = OCRTextRegion(
        text="Launch Diagnostics",
        normalized_text="launch diagnostics",
        bounding_box=OCRBoundingBox(left=100, top=200, right=300, bottom=250),
        words=[],
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="Launch Diagnostics",
        observation_id="snap_test_001",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1)

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Launch Diagnostics",
        metadata={"ocr_result": ocr_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.bounding_box.left == 100
    assert res.target.bounding_box.top == 200
    assert res.target.bounding_box.width == 200
    assert res.target.bounding_box.height == 50
    assert 100 < res.target.safe_point.x < 300
    assert 200 < res.target.safe_point.y < 250
    assert res.target.evidence.source == "OCR_TEXT"
    assert res.target.evidence.name == "Launch Diagnostics"


def test_target_locator_ocr_text_ambiguous_fails_closed():
    # Two separate "Settings" buttons on screen
    r1 = OCRTextRegion(
        text="Settings",
        normalized_text="settings",
        bounding_box=OCRBoundingBox(left=10, top=10, right=80, bottom=40),
    )
    r2 = OCRTextRegion(
        text="Settings",
        normalized_text="settings",
        bounding_box=OCRBoundingBox(left=10, top=100, right=80, bottom=130),
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[r1, r2],
        full_text="Settings Settings",
        observation_id="snap_test_001",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1)

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Settings",
        metadata={"ocr_result": ocr_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.AMBIGUOUS
    assert res.candidates_count == 2
    assert res.target is None
    assert "Ambiguous OCR target: 2 regions matched" in (res.diagnostic_message or "")


def test_target_locator_ocr_text_not_found():
    region = OCRTextRegion(
        text="Help",
        normalized_text="help",
        bounding_box=OCRBoundingBox(left=10, top=10, right=80, bottom=40),
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="Help",
        observation_id="snap_test_001",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1)

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="NonExistentButton",
        metadata={"ocr_result": ocr_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.NOT_FOUND
    assert res.target is None


def test_target_locator_ocr_text_generation_mismatch_fails_closed():
    region = OCRTextRegion(
        text="Save",
        normalized_text="save",
        bounding_box=OCRBoundingBox(left=10, top=10, right=80, bottom=40),
    )
    # OCR result generated under generation 1
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="Save",
        observation_id="snap_old",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    # Current active snapshot is at generation 2
    snap_gen2 = _create_test_snapshot(generation_id=2)

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Save",
        metadata={"ocr_result": ocr_result},
    )

    res = locator.locate_target(snap_gen2, intent)
    assert res.status == TargetResolutionStatus.STALE_OBSERVATION
    assert res.is_stale_observation is True
    assert res.target is None


def test_target_locator_ocr_text_unsupported_provider_fails_closed():
    ocr_result = OCRResult(
        status=OCRStatus.UNSUPPORTED,
        provider_kind=OCRProviderKind.UNSUPPORTED,
        text_regions=[],
        full_text="",
        desktop_generation_id=1,
        error_message="OCR backend is unavailable",
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1)

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Save",
        metadata={"ocr_result": ocr_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.UNSUPPORTED
    assert res.target is None


def test_target_locator_ocr_coordinate_mapping_failure_fails_closed():
    # Region with coordinate space SCREENSHOT_PIXEL_SPACE but invalid geometry
    region = OCRTextRegion(
        text="CorruptedBox",
        normalized_text="corruptedbox",
        bounding_box=OCRBoundingBox(
            left=500,
            top=500,
            right=200,
            bottom=200,
            coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE,
        ),
        words=[],
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="CorruptedBox",
        observation_id="snap_test_001",
        desktop_generation_id=1,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_test_snapshot(generation_id=1)

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="CorruptedBox",
        metadata={"ocr_result": ocr_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.INVALID_REQUEST
    assert res.target is None
    assert "OCR coordinate mapping failed" in (res.diagnostic_message or "")
