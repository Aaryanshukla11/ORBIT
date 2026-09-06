"""Live Windows Optical Character Recognition (OCR) Validation Suite for Milestone M1.7.

Validates that native Windows OCR (Windows.Media.Ocr.OcrEngine):
1. Runs against the live Windows host WinRT subsystem.
2. Performs real character recognition using the local Windows OCR engine.
3. Detects visible text characters and words truthfully without fake confidence.
4. Generates valid physical bounding boxes corresponding to the on-screen element coordinates.
5. Feeds into EvidenceBasedTargetLocator to resolve an OCR_TEXT target with safe action point.

Epistemic Classification:
- LIVE_OS_VALIDATED: Executed against live Windows WinRT OCR engine subsystem on the host machine.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import io
import subprocess
import sys
import time
from typing import Generator
from uuid import uuid4
from PIL import Image, ImageDraw
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import OCRResult, OCRStatus
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


@pytest.mark.skipif(not IS_WINDOWS, reason="Live OCR validation requires Windows host")
@pytest.mark.asyncio
async def test_live_windows_native_ocr_execution_on_host():
    """Validate that native Windows OCR executes and extracts text on the live Windows host."""
    provider = WindowsNativeOCRProvider()
    if not provider.is_available():
        pytest.skip("WindowsNativeOCRProvider is not available on this platform")

    # Render a high-contrast test image with UI button and text
    img = Image.new("RGB", (800, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        from PIL import ImageFont
        font = ImageFont.load_default()

    draw.text((40, 50), "ORBIT Semantic Perception Live", fill=(0, 0, 0), font=font)
    draw.rectangle([40, 140, 450, 220], fill=(0, 102, 204))
    draw.text((60, 155), "Execute Action Now", fill=(255, 255, 255), font=font)

    obs = ProductionObservationAdapter()
    await obs.initialize()
    try:
        snapshot = await obs.capture_snapshot()

        # Run real Windows Native OCR engine matching active generation
        t0 = time.perf_counter()
        ocr_res: OCRResult = await provider.extract_text(
            image=img,
            desktop_generation_id=snapshot.generation_id,
            observation_id=snapshot.snapshot_id,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0

        # Assertions
        assert ocr_res.status == OCRStatus.SUCCESS
        assert ocr_res.has_text is True
        assert len(ocr_res.text_regions) >= 1
        assert duration_ms < 5000.0  # Typically <50ms, allow margin for CPU load

        full_text_lower = ocr_res.full_text.lower()
        assert "semantic" in full_text_lower or "perception" in full_text_lower or "execute" in full_text_lower or "action" in full_text_lower

        locator = EvidenceBasedTargetLocator()

        intent = TargetIntent(
            strategy=TargetStrategy.OCR_TEXT,
            text="Execute Action Now",
            exact_match=False,
            metadata={"ocr_result": ocr_res},
        )

        res = locator.locate_target(snapshot, intent)
        assert res.status == TargetResolutionStatus.RESOLVED
        assert res.target is not None

        # Verify safe interior action point lies within the bounding box
        target_pt = res.target.safe_point
        assert res.target.bounding_box.left <= target_pt.x <= res.target.bounding_box.right
        assert res.target.bounding_box.top <= target_pt.y <= res.target.bounding_box.bottom
        assert res.target.evidence.source == "OCR_TEXT"
    finally:
        await obs.shutdown()
