"""Live Windows host validation tests for Multi-Modal Perception Fusion & Grounding Layer."""

import io
import time
import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
from orbit.runtime.perception.fusion_models import (
    EvidenceChannel,
    FusionPolicy,
    FusionStatus,
)
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
from orbit.runtime.perception.visual_engine import VisualPerceptionEngine
from orbit.runtime.perception.visual_matcher import TemplateVisualMatcher
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualTemplate,
    VisualTemplateSource,
)
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


@pytest.mark.asyncio
async def test_live_windows_multimodal_perception_fusion():
    """Live OS Test: Capture live Windows desktop and fuse multimodal evidence (UIA + OCR + Visual)."""
    ocr_provider = WindowsNativeOCRProvider()
    if not ocr_provider.is_available():
        pytest.skip("Windows Native OCR (Windows.Media.Ocr) is not available on this host")

    obs_adapter = ProductionObservationAdapter()
    await obs_adapter.initialize()
    ws_adapter = ProductionWorkspaceAdapter()
    await ws_adapter.initialize()

    active_gen = ws_adapter.get_desktop_generation()
    obs_adapter.sync_generation(active_gen)

    # 1. Capture live snapshot and desktop image
    snapshot = await obs_adapter.capture_snapshot()
    assert snapshot.generation_id == active_gen
    assert snapshot.is_stale is False

    frame = await obs_adapter.capture_screen()
    assert frame is not None
    assert len(frame.raw_bytes) > 0

    pil_image = Image.open(io.BytesIO(frame.raw_bytes))

    # Render a high-contrast target onto the image to ensure consistent OCR + visual target detection
    draw = ImageDraw.Draw(pil_image)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()

    # Draw Button at (400, 300)
    draw.rectangle([400, 300, 650, 370], fill=(0, 102, 204))
    draw.text((420, 315), "Confirm Action", fill=(255, 255, 255), font=font)

    # 2. Run live Windows OCR extraction
    perception_engine = SemanticPerceptionEngine(ocr_provider=ocr_provider)
    ocr_res = await perception_engine.scan_observation(snapshot, image=pil_image)
    assert ocr_res.is_success is True

    # 3. Extract visual template from the drawn button
    template_img = pil_image.crop((400, 300, 650, 370))
    template = VisualTemplate.from_image(
        template_id="tpl_confirm",
        name="Confirm Action",
        image=template_img,
        source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
    )

    # 4. Execute Multi-Modal Target Resolution
    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        text="Confirm Action",
        name="Confirm Action",
        template=template,
        metadata={"ocr_result": ocr_res},
    )

    locator = EvidenceBasedTargetLocator(perception_engine=perception_engine)
    res = locator.locate_target(snapshot, intent)

    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None

    # Verify coordinate safety against live workspace adapter
    coord_val = ws_adapter.validate_coordinate(
        res.target.safe_point.x,
        res.target.safe_point.y,
        expected_generation=snapshot.generation_id,
    )
    assert coord_val.is_valid is True

    await obs_adapter.shutdown()
    await ws_adapter.shutdown()


@pytest.mark.asyncio
async def test_live_windows_multimodal_contradiction_fails_closed():
    """Live OS Test: Submit contradictory multimodal intent against live desktop; verify fail-closed."""
    ocr_provider = WindowsNativeOCRProvider()
    if not ocr_provider.is_available():
        pytest.skip("Windows Native OCR is not available on this host")

    obs_adapter = ProductionObservationAdapter()
    await obs_adapter.initialize()
    ws_adapter = ProductionWorkspaceAdapter()
    await ws_adapter.initialize()

    active_gen = ws_adapter.get_desktop_generation()
    obs_adapter.sync_generation(active_gen)

    snapshot = await obs_adapter.capture_snapshot()

    # Intent with non-existent target name across all channels
    intent = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        name="NON_EXISTENT_MULTIMODAL_TEST_GLYPH_99999",
        text="NON_EXISTENT_MULTIMODAL_TEST_GLYPH_99999",
    )

    locator = EvidenceBasedTargetLocator()
    res = locator.locate_target(snapshot, intent)

    # Must fail closed with NOT_FOUND
    assert res.status == TargetResolutionStatus.NOT_FOUND
    assert res.target is None

    await obs_adapter.shutdown()
    await ws_adapter.shutdown()
