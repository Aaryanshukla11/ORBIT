"""Unit tests for Set-of-Marks (SOM) visual overlay generation and visual region grounding (Phase 2G.3)."""

from PIL import Image
import pytest
from unittest.mock import MagicMock

from orbit.adapters.observation.snapshot import BoundingBox, ObservedElement, ObservedWindow
from orbit.runtime.agent.contracts import SemanticTarget
from orbit.runtime.perception.set_of_marks import SetOfMarksGenerator, SOMMark, SOMResult
from orbit.runtime.targeting.models import (
    TargetBoundingBox,
    TargetResolutionResult,
    TargetResolutionStatus,
)
from orbit.runtime.targeting.visual_grounder import VisualRegionGrounder


def test_som_generator_with_uia_elements():
    """Verify SOM generator overlays marks on UIA elements with correct coordinates."""
    img = Image.new("RGB", (800, 600), color="white")
    generator = SetOfMarksGenerator()

    elem1 = MagicMock(spec=ObservedElement)
    elem1.bounding_box = BoundingBox(left=50, top=50, width=100, height=40)
    elem1.name = "Submit"
    elem1.control_type = "Button"

    elem2 = MagicMock(spec=ObservedElement)
    elem2.bounding_box = BoundingBox(left=200, top=100, width=150, height=30)
    elem2.name = "Username"
    elem2.control_type = "Edit"

    result = generator.generate_som(image=img, uia_elements=[elem1, elem2])

    assert isinstance(result, SOMResult)
    assert len(result.marks) == 2
    assert result.marks[0].mark_id == 1
    assert result.marks[0].label == "Submit"
    assert result.marks[0].bounding_box.left == 50
    assert result.marks[0].bounding_box.top == 50
    assert result.marks[0].bounding_box.right == 150
    assert result.marks[0].bounding_box.bottom == 90
    assert result.marks[0].center_point == (100, 70)

    assert result.marks[1].mark_id == 2
    assert result.marks[1].label == "Username"
    assert result.marks[1].bounding_box.left == 200

    # Verify summary text generation
    summary = result.to_summary_text()
    assert "[1] 'Submit' (Button)" in summary
    assert "[2] 'Username' (Edit)" in summary


def test_som_generator_with_ocr_tokens():
    """Verify SOM generator captures OCR tokens when UIA tree is sparse or empty."""
    img = Image.new("RGB", (800, 600), color="black")
    generator = SetOfMarksGenerator()

    ocr_tokens = [
        {"word": "Login", "left": 100, "top": 100, "width": 80, "height": 30},
        {"word": "Cancel", "left": 200, "top": 100, "width": 80, "height": 30},
    ]

    result = generator.generate_som(image=img, ocr_tokens=ocr_tokens)

    assert len(result.marks) == 2
    assert result.marks[0].label == "Login"
    assert result.marks[0].source == "OCR"
    assert result.marks[1].label == "Cancel"
    assert result.marks[1].source == "OCR"


def test_som_iou_deduplication():
    """Verify overlapping bounding boxes (UIA and OCR on same button) are deduplicated."""
    img = Image.new("RGB", (800, 600), color="gray")
    generator = SetOfMarksGenerator(iou_overlap_threshold=0.6)

    # UIA button at (100, 100, 200, 150)
    elem = MagicMock(spec=ObservedElement)
    elem.bounding_box = BoundingBox(left=100, top=100, width=100, height=50)
    elem.name = "OK"
    elem.control_type = "Button"

    # OCR token at almost identical coordinates (102, 102, 95, 45)
    ocr_tokens = [{"word": "OK", "left": 102, "top": 102, "width": 95, "height": 45}]

    result = generator.generate_som(image=img, uia_elements=[elem], ocr_tokens=ocr_tokens)

    # Should deduplicate into exactly 1 mark, prioritizing UIA
    assert len(result.marks) == 1
    assert result.marks[0].source == "UIA"
    assert result.marks[0].label == "OK"


def test_som_active_window_filtering():
    """Verify marks outside active window boundary are excluded when active window bounds provided."""
    img = Image.new("RGB", (1920, 1080), color="white")
    generator = SetOfMarksGenerator()

    # Elem 1 inside active window (500, 200, 1200, 800)
    elem1 = MagicMock(spec=ObservedElement)
    elem1.bounding_box = BoundingBox(left=600, top=300, width=100, height=50)
    elem1.name = "Inside"

    # Elem 2 outside active window (Taskbar at top/bottom)
    elem2 = MagicMock(spec=ObservedElement)
    elem2.bounding_box = BoundingBox(left=50, top=1040, width=80, height=30)
    elem2.name = "TaskbarButton"

    active_bounds = (500, 200, 1200, 800)
    result = generator.generate_som(image=img, uia_elements=[elem1, elem2], active_window_bounds=active_bounds)

    assert len(result.marks) == 1
    assert result.marks[0].label == "Inside"


def test_visual_region_grounder_resolves_numeric_mark():
    """Verify VisualRegionGrounder resolves mark index into physical SafeActionPoint."""
    grounder = VisualRegionGrounder()

    mark1 = SOMMark(
        mark_id=5,
        bounding_box=TargetBoundingBox(left=300, top=400, right=450, bottom=460),
        center_point=(375, 430),
        label="Save Document",
        role="button",
        source="UIA",
    )
    som_res = SOMResult(
        annotated_image=Image.new("RGB", (1000, 800)),
        marks=[mark1],
        mark_map={5: mark1},
        image_dimensions=(1000, 800),
    )

    # 1. Target with bracketed mark in name "Click [5]"
    target1 = SemanticTarget(name="Click [5]")
    res1 = grounder.resolve_from_som(target1, som_res)
    assert res1.status == TargetResolutionStatus.RESOLVED
    assert res1.target is not None
    assert res1.target.safe_point.x == 375
    assert res1.target.safe_point.y == 430
    assert res1.target.evidence.source == "VISUAL_SOM"
    assert res1.target.evidence.raw_metadata.get("mark_id") == 5

    # 2. Target with explicit parameter {"mark_id": 5}
    target2 = SemanticTarget(name="Save", parameters={"mark_id": 5})
    res2 = grounder.resolve_from_som(target2, som_res)
    assert res2.status == TargetResolutionStatus.RESOLVED
    assert res2.target.safe_point.x == 375


def test_visual_region_grounder_resolves_box_2d():
    """Verify VisualRegionGrounder converts normalized 2D bounding boxes to screen pixels."""
    grounder = VisualRegionGrounder()
    screen_dim = (1920, 1080)

    # Normalized box [0.1, 0.2, 0.3, 0.4] -> left: 192, top: 216, right: 576, bottom: 432
    norm_box = (0.1, 0.2, 0.3, 0.4)
    res = grounder.resolve_from_box_coordinates(
        normalized_box=norm_box,
        screen_dimensions=screen_dim,
        target_name="Canvas Toolbar",
    )

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.bounding_box.left == 192
    assert res.target.bounding_box.top == 216
    assert res.target.bounding_box.right == 576
    assert res.target.bounding_box.bottom == 432
    assert res.target.safe_point.x == (192 + 576) // 2
    assert res.target.safe_point.y == (216 + 432) // 2
    assert res.target.evidence.source == "VISUAL_BBOX"


def test_visual_region_grounder_rejects_invalid_boxes():
    """Verify VisualRegionGrounder fails closed when invalid or negative coordinates provided."""
    grounder = VisualRegionGrounder()
    screen_dim = (1920, 1080)

    # Out of range (> 1.0)
    res1 = grounder.resolve_from_box_coordinates(
        normalized_box=(0.1, 0.2, 1.5, 0.4),
        screen_dimensions=screen_dim,
    )
    assert res1.status == TargetResolutionStatus.INVALID_REQUEST

    # Degenerate (u2 <= u1)
    res2 = grounder.resolve_from_box_coordinates(
        normalized_box=(0.5, 0.2, 0.3, 0.4),
        screen_dimensions=screen_dim,
    )
    assert res2.status == TargetResolutionStatus.INVALID_REQUEST
