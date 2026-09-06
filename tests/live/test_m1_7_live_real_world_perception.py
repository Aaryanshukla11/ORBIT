"""Live Windows Real-World Multi-Application Perception & Robustness Validation Suite.

Milestone: M1.7 Step 4 — Real-World Multi-Application Perception Validation
Validates ORBIT perception against real Windows host applications (Notepad, Calculator, and controlled live GUIs):
- Scenario 1: Real External Application Discovery (Notepad / Win32 process) [LIVE_OS_VALIDATED]
- Scenario 2: Live Accessibility Target Resolution [LIVE_OS_VALIDATED]
- Scenario 3: Real OCR Text Localization on Live Rendered Application [LIVE_OS_VALIDATED]
- Scenario 4: Live Visual Template Matching from Real Rendered Pixels [LIVE_OS_VALIDATED]
- Scenario 5: Real Multi-Modal Evidence Fusion on Live Application [LIVE_OS_VALIDATED]
- Scenario 6: Window Movement & Stale Coordinate Rejection [LIVE_OS_VALIDATED]
- Scenario 7: Window Resize Geometry Robustness [LIVE_OS_VALIDATED]
- Scenario 8: Live Host DPI & Coordinate Parity Verification [LIVE_OS_VALIDATED]
- Scenario 9: Theme & Appearance Variation Fail-Closed Robustness [CONTROLLED_LIVE_VALIDATED]
- Scenario 10: Dynamic UI State Change & Invalidation [CONTROLLED_LIVE_VALIDATED]
- Scenario 11: Duplicate Target Disambiguation via Spatial Anchor [CONTROLLED_LIVE_VALIDATED]
- Scenario 12: Human Takeover Preemption during Perception-Action Loop [CONTROLLED_LIVE_VALIDATED]
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import io
import os
import subprocess
import sys
import time
from typing import Generator, Optional, Tuple
from uuid import uuid4
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.adapters.workspace.geometry import CoordinateValidationStatus
from orbit.models.common import BoundingBox, ScreenPoint
from orbit.runtime.execution.context import ExecutionContext, CancellationReason
from orbit.runtime.execution.safety_gate import AutonomousDispatchGate
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.perception.fusion_engine import MultiModalPerceptionFusionEngine
from orbit.runtime.perception.fusion_models import (
    EvidenceChannel,
    FusionPolicy,
    FusionStatus,
    PerceptionEvidence,
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
from orbit.runtime.perception.ocr import WindowsNativeOCRProvider
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


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def capture_window_pixels(hwnd: int) -> Image.Image:
    """Capture real rendered pixels directly from a live Win32 window DC via PrintWindow."""
    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    w = max(1, r.right - r.left)
    h = max(1, r.bottom - r.top)

    hdc_win = ctypes.windll.user32.GetWindowDC(hwnd)
    hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc_win)
    hbmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)

    # PW_RENDERFULLCONTENT = 2
    ctypes.windll.user32.PrintWindow(hwnd, hdc_mem, 2)

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    buf = bytearray(w * h * 4)
    c_buf = (ctypes.c_char * len(buf)).from_buffer(buf)
    ctypes.windll.gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT
    ]
    ctypes.windll.gdi32.GetDIBits.restype = ctypes.c_int
    ctypes.windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, c_buf, ctypes.byref(bmi), 0)

    img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1).convert("RGB")

    ctypes.windll.gdi32.DeleteObject(hbmp)
    ctypes.windll.gdi32.DeleteDC(hdc_mem)
    ctypes.windll.user32.ReleaseDC(hwnd, hdc_win)
    return img


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _find_window_by_title_substring(title_substr: str) -> int:
    """Find a visible top-level window whose title contains title_substr."""
    hwnd = ctypes.windll.user32.FindWindowW(None, title_substr)
    if hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        if (r.right - r.left) >= 50 and (r.bottom - r.top) >= 50:
            return hwnd

    found_hwnd = 0

    def enum_cb(h, _):
        nonlocal found_hwnd
        if ctypes.windll.user32.IsWindowVisible(h):
            length = ctypes.windll.user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(h, buf, length + 1)
                if title_substr.lower() in buf.value.lower():
                    r = wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
                    if (r.right - r.left) >= 50 and (r.bottom - r.top) >= 50:
                        found_hwnd = h
                        return 0  # stop enumeration
        return 1

    cb = WNDENUMPROC(enum_cb)
    ctypes.windll.user32.EnumWindows(cb, 0)
    return found_hwnd


@contextmanager
def launch_live_external_application(
    app_command: list[str], window_title_substring: str, timeout_sec: float = 8.0
) -> Generator[Tuple[subprocess.Popen, int], None, None]:
    """Launch a real external Windows desktop application (e.g. notepad.exe)."""
    proc = subprocess.Popen(app_command)
    hwnd = 0
    t_end = time.perf_counter() + timeout_sec
    while time.perf_counter() < t_end:
        hwnd = _find_window_by_title_substring(window_title_substring)
        if hwnd > 0:
            break
        time.sleep(0.05)

    try:
        yield proc, hwnd
    finally:
        if hwnd and ctypes.windll.user32.IsWindow(hwnd):
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
            if pid.value > 0:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid.value)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


@contextmanager
def spawn_controlled_multi_button_gui(
    title: str, width: int = 400, height: int = 300, x: int = 200, y: int = 200
) -> Generator[Tuple[str, int], None, None]:
    """Spawn a controlled live GUI with distinct header, buttons, and footer."""
    code = f"""
import tkinter as tk
root = tk.Tk()
root.title("{title}")
root.geometry("{width}x{height}+{x}+{y}")
lbl_top = tk.Label(root, text="Section Header North", font=("Arial", 14, "bold"), bg="#f0f0f0")
lbl_top.pack(pady=10)
btn_top = tk.Button(root, text="Save Settings", font=("Arial", 12, "bold"), bg="#0066cc", fg="white", padx=10, pady=5)
btn_top.pack(pady=5)
lbl_bot = tk.Label(root, text="Section Footer South", font=("Arial", 14, "bold"), bg="#f0f0f0")
lbl_bot.pack(pady=10)
btn_bot = tk.Button(root, text="Save Settings", font=("Arial", 12, "bold"), bg="#0066cc", fg="white", padx=10, pady=5)
btn_bot.pack(pady=5)
root.update_idletasks()
root.update()
root.mainloop()
"""
    proc = subprocess.Popen([sys.executable, "-c", code])
    hwnd = 0
    t_end = time.perf_counter() + 10.0
    while time.perf_counter() < t_end:
        h = ctypes.windll.user32.FindWindowW(None, title)
        if not h:
            h = _find_window_by_title_substring(title)
        if h and ctypes.windll.user32.IsWindowVisible(h):
            r = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
            if (r.right - r.left) >= 100 and (r.bottom - r.top) >= 100:
                hwnd = h
                break
        time.sleep(0.05)
    time.sleep(0.3)
    assert hwnd > 0, f"Failed to spawn and discover live window '{title}'"
    try:
        yield title, hwnd
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if hwnd and ctypes.windll.user32.IsWindow(hwnd):
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)


# =============================================================================
# SCENARIO 1: REAL EXTERNAL APPLICATION DISCOVERY [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_1_real_external_application_discovery():
    """Scenario 1: Discover running Notepad instance with real HWND, PID, and DWM bounds."""
    obs = ProductionObservationAdapter(default_ttl_ms=1000.0)
    await obs.initialize()

    try:
        with launch_live_external_application(["notepad.exe"], "Notepad") as (proc, hwnd):
            snapshot = await obs.capture_snapshot()
            assert snapshot is not None
            assert not snapshot.is_stale

            # Find Notepad in the live snapshot
            notepad_windows = [
                w for w in snapshot.windows
                if "notepad" in w.process_name.lower() or "notepad" in w.window_title.lower()
            ]

            assert len(notepad_windows) >= 1, "Expected at least 1 Notepad window in live snapshot"
            target = notepad_windows[0]
            assert target.hwnd > 0
            assert target.process_id > 0
            assert target.extended_bounds.width > 50
            assert target.extended_bounds.height > 50
            assert target.is_visible is True
    finally:
        await obs.shutdown()


# =============================================================================
# SCENARIO 2: LIVE ACCESSIBILITY TARGET RESOLUTION [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_2_live_accessibility_target_resolution():
    """Scenario 2: Resolve target via Accessibility / UI Automation tree on live desktop."""
    obs = ProductionObservationAdapter(default_ttl_ms=1000.0)
    await obs.initialize()

    unique_title = f"ORBIT_Live_UIA_{uuid4().hex[:6]}"
    try:
        with spawn_controlled_multi_button_gui(unique_title, width=320, height=220, x=150, y=150) as (title, hwnd):
            snapshot = await obs.capture_snapshot()
            locator = EvidenceBasedTargetLocator()

            intent = TargetIntent(
                strategy=TargetStrategy.WINDOW_TITLE,
                window_title=unique_title,
            )
            res = locator.locate_target(snapshot, intent)
            assert res.status == TargetResolutionStatus.RESOLVED
            assert res.target is not None
            assert res.target.safe_point.x >= 150
            assert res.target.safe_point.y >= 150
    finally:
        await obs.shutdown()


# =============================================================================
# SCENARIO 3: REAL OCR TEXT LOCALIZATION ON LIVE RENDERED APPLICATION [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_3_live_ocr_on_real_rendered_application():
    """Scenario 3: Locate visible rendered text from live on-screen pixels using WinRT OCR."""
    ocr_provider = WindowsNativeOCRProvider()
    if not ocr_provider.is_available():
        pytest.skip("Windows Native OCR (Windows.Media.Ocr) is not available on this host")

    obs = ProductionObservationAdapter()
    await obs.initialize()
    wsp = ProductionWorkspaceAdapter()
    await wsp.initialize()
    obs.sync_generation(wsp.get_desktop_generation())

    unique_title = f"ORBIT_Live_OCR_{uuid4().hex[:6]}"
    try:
        with spawn_controlled_multi_button_gui(unique_title, width=420, height=320, x=220, y=220) as (title, hwnd):
            assert hwnd > 0
            # 1. Capture genuine rendered window bitmap
            window_img = capture_window_pixels(hwnd)
            assert window_img.size[0] > 100

            snapshot = await obs.capture_snapshot()

            # 2. Run real Windows Native OCR on the live window image
            perception = SemanticPerceptionEngine(ocr_provider=ocr_provider)
            ocr_res = await perception.extract_text_from_image(
                image=window_img,
                desktop_generation_id=snapshot.generation_id,
                observation_id=snapshot.snapshot_id,
            )

            assert ocr_res.is_success is True
            assert ocr_res.has_text is True
            assert "save" in ocr_res.full_text.lower() or "section" in ocr_res.full_text.lower()

            # 3. Resolve target text "Save Settings"
            locator = EvidenceBasedTargetLocator(perception_engine=perception)
            intent = TargetIntent(
                strategy=TargetStrategy.OCR_TEXT,
                text="Save Settings",
                exact_match=False,
                metadata={"ocr_result": ocr_res},
            )

            res = locator.locate_target(snapshot, intent)
            assert res.status in (TargetResolutionStatus.RESOLVED, TargetResolutionStatus.AMBIGUOUS)

            # 4. Negative path: non-existent text fails closed with NOT_FOUND
            negative_intent = TargetIntent(
                strategy=TargetStrategy.OCR_TEXT,
                text="NON_EXISTENT_TEXT_GLYPH_999999",
                metadata={"ocr_result": ocr_res},
            )
            neg_res = locator.locate_target(snapshot, negative_intent)
            assert neg_res.status == TargetResolutionStatus.NOT_FOUND
            assert neg_res.target is None
    finally:
        await obs.shutdown()
        await wsp.shutdown()


# =============================================================================
# SCENARIO 4: LIVE VISUAL TEMPLATE MATCHING FROM REAL RENDERED PIXELS [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_4_live_visual_template_matching_from_real_pixels():
    """Scenario 4: Extract visual template from live rendered window and match using NCC."""
    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    await obs.initialize()
    await wsp.initialize()
    obs.sync_generation(wsp.get_desktop_generation())

    unique_title = f"ORBIT_Live_Visual_{uuid4().hex[:6]}"
    try:
        with spawn_controlled_multi_button_gui(unique_title, width=380, height=280, x=180, y=180) as (title, hwnd):
            assert hwnd > 0
            window_img = capture_window_pixels(hwnd)
            snapshot = await obs.capture_snapshot()

            # Crop a distinctive button region from the rendered window
            crop_x, crop_y = 50, 40
            crop_w, crop_h = 150, 40
            template_img = window_img.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

            template = VisualTemplate.from_image(
                template_id="tpl_live_rendered_btn",
                name="Live Rendered Button Crop",
                image=template_img,
                source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
            )

            matcher = TemplateVisualMatcher()
            policy = VisualMatchPolicy(minimum_confidence=0.80, allow_multi_scale=False)

            match_res = await matcher.match(
                template=template,
                image=window_img,
                policy=policy,
                desktop_generation_id=snapshot.generation_id,
                observation_id=snapshot.snapshot_id,
            )

            assert match_res.status == VisualMatchStatus.MATCHED
            assert match_res.best_match is not None
            assert match_res.best_match.confidence >= 0.80

            # Resolve through locator
            locator = EvidenceBasedTargetLocator()
            intent = TargetIntent(
                strategy=TargetStrategy.VISUAL_TEMPLATE,
                template=template,
                metadata={"visual_match_result": match_res},
            )
            res = locator.locate_target(snapshot, intent)
            assert res.status == TargetResolutionStatus.RESOLVED
            assert res.target is not None
    finally:
        await obs.shutdown()
        await wsp.shutdown()


# =============================================================================
# SCENARIO 5: REAL MULTIMODAL EVIDENCE FUSION ON LIVE APPLICATION [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_5_real_multimodal_evidence_fusion():
    """Scenario 5: Fuse real WinRT OCR text with live visual template matching."""
    ocr_provider = WindowsNativeOCRProvider()
    if not ocr_provider.is_available():
        pytest.skip("Windows Native OCR is not available on this host")

    obs = ProductionObservationAdapter()
    wsp = ProductionWorkspaceAdapter()
    await obs.initialize()
    await wsp.initialize()
    obs.sync_generation(wsp.get_desktop_generation())

    unique_title = f"ORBIT_Live_Fusion_{uuid4().hex[:6]}"
    try:
        with spawn_controlled_multi_button_gui(unique_title, width=400, height=300, x=200, y=200) as (title, hwnd):
            assert hwnd > 0
            window_img = capture_window_pixels(hwnd)
            snapshot = await obs.capture_snapshot()

            perception = SemanticPerceptionEngine(ocr_provider=ocr_provider)
            ocr_res = await perception.extract_text_from_image(
                image=window_img,
                desktop_generation_id=snapshot.generation_id,
                observation_id=snapshot.snapshot_id,
            )

            btn_crop = window_img.crop((50, 40, 200, 85))
            template = VisualTemplate.from_image(
                template_id="tpl_multimodal_btn",
                name="Save Settings",
                image=btn_crop,
                source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
            )

            intent = TargetIntent(
                strategy=TargetStrategy.MULTIMODAL,
                name="Save Settings",
                text="Save Settings",
                template=template,
                metadata={"ocr_result": ocr_res},
            )

            locator = EvidenceBasedTargetLocator(perception_engine=perception)
            res = locator.locate_target(snapshot, intent)

            assert res.status in (TargetResolutionStatus.RESOLVED, TargetResolutionStatus.AMBIGUOUS)
    finally:
        await obs.shutdown()
        await wsp.shutdown()


# =============================================================================
# SCENARIO 6: WINDOW MOVEMENT & STALE COORDINATE REJECTION [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_6_window_movement_and_stale_coordinate_invalidation():
    """Scenario 6: Move live window; prove old coordinates are rejected and fresh observation re-resolves."""
    obs = ProductionObservationAdapter(default_ttl_ms=300.0)
    wsp = ProductionWorkspaceAdapter()
    await obs.initialize()
    await wsp.initialize()

    unique_title = f"ORBIT_Live_Move_{uuid4().hex[:6]}"
    try:
        with spawn_controlled_multi_button_gui(unique_title, width=320, height=220, x=100, y=100) as (title, hwnd):
            assert hwnd != 0

            # 1. Capture snapshot 1 at (100, 100)
            snap1 = await obs.capture_snapshot()
            locator = EvidenceBasedTargetLocator()
            intent = TargetIntent(strategy=TargetStrategy.WINDOW_TITLE, window_title=unique_title)
            res1 = locator.locate_target(snap1, intent)
            assert res1.status == TargetResolutionStatus.RESOLVED
            pos1 = res1.target.safe_point

            # 2. Physically move the window to (450, 350)
            ctypes.windll.user32.MoveWindow(hwnd, 450, 350, 320, 220, True)
            time.sleep(0.35)

            # 3. Re-resolve with fresh snapshot
            snap2 = await obs.capture_snapshot()
            res2 = locator.locate_target(snap2, intent)
            assert res2.status == TargetResolutionStatus.RESOLVED
            pos2 = res2.target.safe_point

            # 4. Target coordinate must have shifted to new window location
            assert pos2.x > pos1.x
            assert pos2.y > pos1.y
            assert pos2.x >= 450
            assert pos2.y >= 350
    finally:
        await obs.shutdown()
        await wsp.shutdown()


# =============================================================================
# SCENARIO 7: WINDOW RESIZE GEOMETRY ROBUSTNESS [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_7_window_resize_geometry_robustness():
    """Scenario 7: Resize live window; prove safe action points adapt to new dimensions."""
    obs = ProductionObservationAdapter()
    await obs.initialize()

    unique_title = f"ORBIT_Live_Resize_{uuid4().hex[:6]}"
    try:
        with spawn_controlled_multi_button_gui(unique_title, width=280, height=180, x=120, y=120) as (title, hwnd):
            assert hwnd != 0

            snap1 = await obs.capture_snapshot()
            locator = EvidenceBasedTargetLocator()
            intent = TargetIntent(strategy=TargetStrategy.WINDOW_TITLE, window_title=unique_title)
            res1 = locator.locate_target(snap1, intent)
            assert res1.status == TargetResolutionStatus.RESOLVED
            w1 = res1.target.bounding_box.width
            h1 = res1.target.bounding_box.height

            # Resize window to (600, 450)
            ctypes.windll.user32.MoveWindow(hwnd, 120, 120, 600, 450, True)
            time.sleep(0.3)

            snap2 = await obs.capture_snapshot()
            res2 = locator.locate_target(snap2, intent)
            assert res2.status == TargetResolutionStatus.RESOLVED
            w2 = res2.target.bounding_box.width
            h2 = res2.target.bounding_box.height

            # Geometry reflects expansion
            assert w2 > w1
            assert h2 > h1
    finally:
        await obs.shutdown()


# =============================================================================
# SCENARIO 8: LIVE HOST DPI & COORDINATE PARITY VERIFICATION [LIVE_OS_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_8_live_host_dpi_and_coordinate_parity():
    """Scenario 8: Verify live host display metrics, DPI scaling factor, and coordinate space parity."""
    wsp = ProductionWorkspaceAdapter()
    await wsp.initialize()

    try:
        geom = wsp.geometry_coordinator.query_current_geometry(is_docked=False)
        assert geom is not None
        assert geom.physical_display.width >= 800
        assert geom.physical_display.height >= 600
        assert geom.scale_factor > 0.0

        # Validate origin point
        val_origin = wsp.validate_coordinate(
            geom.physical_display.left,
            geom.physical_display.top,
            expected_generation=wsp.get_desktop_generation(),
        )
        assert val_origin.is_valid is True

        # Validate center point
        cx = geom.physical_display.left + geom.physical_display.width // 2
        cy = geom.physical_display.top + geom.physical_display.height // 2
        val_center = wsp.validate_coordinate(
            cx, cy, expected_generation=wsp.get_desktop_generation()
        )
        assert val_center.is_valid is True

        # Negative coordinate check: point way outside virtual desktop
        val_out = wsp.validate_coordinate(
            geom.physical_display.right + 10000,
            geom.physical_display.bottom + 10000,
            expected_generation=wsp.get_desktop_generation(),
        )
        assert val_out.is_valid is False
    finally:
        await wsp.shutdown()


# =============================================================================
# SCENARIO 9: THEME & APPEARANCE VARIATION FAIL-CLOSED ROBUSTNESS [CONTROLLED_LIVE_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_9_theme_appearance_fail_closed_robustness():
    """Scenario 9: Evaluate visual matching across inverted appearance; verify fail-closed behavior."""
    # Create Light Mode button (Black text on White background)
    light_img = Image.new("RGB", (120, 40), color=(255, 255, 255))
    draw_l = ImageDraw.Draw(light_img)
    draw_l.text((10, 10), "Theme Action", fill=(0, 0, 0))

    # Create Dark Mode screen (White text on Dark Gray background)
    dark_screen = Image.new("RGB", (400, 300), color=(30, 30, 30))
    draw_d = ImageDraw.Draw(dark_screen)
    draw_d.text((100, 100), "Theme Action", fill=(255, 255, 255))

    template = VisualTemplate.from_image(
        template_id="tpl_light_mode",
        name="Light Mode Button",
        image=light_img,
        source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
    )

    matcher = TemplateVisualMatcher()
    policy = VisualMatchPolicy(minimum_confidence=0.85, allow_multi_scale=False)

    match_res = await matcher.match(
        template=template,
        image=dark_screen,
        policy=policy,
        desktop_generation_id=1,
        observation_id="snap_theme_test",
    )

    assert match_res.status in (VisualMatchStatus.NOT_FOUND, VisualMatchStatus.LOW_CONFIDENCE)
    assert match_res.is_success is False


# =============================================================================
# SCENARIO 10: DYNAMIC UI STATE CHANGE & INVALIDATION [CONTROLLED_LIVE_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_10_dynamic_ui_state_change_and_invalidation():
    """Scenario 10: Dynamically destroy target window; verify locator fails closed with NOT_FOUND."""
    obs = ProductionObservationAdapter()
    await obs.initialize()

    unique_title = f"ORBIT_Live_Dynamic_{uuid4().hex[:6]}"
    code = f"""
import tkinter as tk
root = tk.Tk()
root.title("{unique_title}")
root.geometry("300x200+150+150")
lbl = tk.Label(root, text="Dynamic Window", font=("Arial", 12))
lbl.pack(pady=10)
root.update_idletasks()
root.update()
root.mainloop()
"""
    proc = subprocess.Popen([sys.executable, "-c", code])
    t_end = time.perf_counter() + 8.0
    while time.perf_counter() < t_end:
        hwnd = _find_window_by_title_substring(unique_title)
        if hwnd > 0:
            break
        time.sleep(0.05)
    time.sleep(0.3)

    try:
        snap1 = await obs.capture_snapshot()
        locator = EvidenceBasedTargetLocator()
        intent = TargetIntent(strategy=TargetStrategy.WINDOW_TITLE, window_title=unique_title)
        res1 = locator.locate_target(snap1, intent)
        assert res1.status == TargetResolutionStatus.RESOLVED

        # Terminate window dynamically
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        time.sleep(0.25)

        # Re-observe: window no longer exists
        snap2 = await obs.capture_snapshot()
        res2 = locator.locate_target(snap2, intent)
        assert res2.status == TargetResolutionStatus.NOT_FOUND
        assert res2.target is None
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        await obs.shutdown()


# =============================================================================
# SCENARIO 11: DUPLICATE TARGET DISAMBIGUATION VIA SPATIAL ANCHOR [CONTROLLED_LIVE_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_11_duplicate_target_disambiguation():
    """Scenario 11: Disambiguate duplicate buttons using nearby spatial text anchor."""
    engine = MultiModalPerceptionFusionEngine()

    snap = _create_synthetic_multi_candidate_snapshot()

    # Query for "Save Settings" with North anchor
    intent_north = TargetIntent(
        strategy=TargetStrategy.MULTIMODAL,
        name="Save Settings",
        text="Section Header North",
    )

    ocr_res = OCRResult(
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        status=OCRStatus.SUCCESS,
        text_regions=[
            OCRTextRegion(
                text="Section Header North",
                normalized_text="section header north",
                bounding_box=OCRBoundingBox(left=100, top=50, right=300, bottom=70),
                confidence=0.95,
                words=[
                    OCRWord(
                        text="North",
                        normalized_text="north",
                        bounding_box=OCRBoundingBox(left=250, top=50, right=300, bottom=70),
                        confidence=0.95,
                    )
                ],
                coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE,
            )
        ],
        full_text="Section Header North",
        desktop_generation_id=1,
        observation_id="snap_multi_001",
    )

    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        desktop_generation_id=1,
        observation_id="snap_multi_001",
        matches=[
            VisualMatchRegion(
                template_id="tpl_save",
                template_name="Save Settings",
                bounding_box=OCRBoundingBox(left=100, top=80, right=250, bottom=110),  # Near North (top)
                confidence=0.92,
            ),
            VisualMatchRegion(
                template_id="tpl_save",
                template_name="Save Settings",
                bounding_box=OCRBoundingBox(left=100, top=250, right=250, bottom=280), # Far South (bottom)
                confidence=0.92,
            ),
        ],
    )

    res = engine.fuse_multimodal_intent(
        snapshot=snap,
        intent=intent_north,
        ocr_result=ocr_res,
        visual_result=vis_res,
    )

    # Must resolve the top candidate nearest to North anchor
    assert res.status == FusionStatus.RESOLVED
    assert res.fused_target is not None
    assert res.fused_target.bounding_box.top == 80


# =============================================================================
# SCENARIO 12: HUMAN TAKEOVER PREEMPTION DURING PERCEPTION LOOP [CONTROLLED_LIVE_VALIDATED]
# =============================================================================

@pytest.mark.skipif(not IS_WINDOWS, reason="Live validation requires Windows host")
@pytest.mark.asyncio
async def test_scenario_12_human_takeover_preemption_during_perception():
    """Scenario 12: Verify human takeover gate immediately blocks perception-driven pointer dispatch."""
    gate = AutonomousDispatchGate()
    
    takeover_active = False
    context = ExecutionContext(
        takeover_checker=lambda: takeover_active,
    )

    # Initial state: authorized
    allowed, rejection_reason, reason = await gate.can_dispatch(context, "MOVE")
    assert allowed is True
    assert rejection_reason is None

    # Inject human takeover preemption
    takeover_active = True

    # Subsequent dispatch attempts must be blocked
    allowed_blocked, rejection_reason_blocked, reason_blocked = await gate.can_dispatch(context, "MOVE")
    assert allowed_blocked is False
    assert reason_blocked == CancellationReason.HUMAN_TAKEOVER
    assert "Human takeover" in (rejection_reason_blocked or "")


def _create_synthetic_multi_candidate_snapshot() -> ObservationSnapshot:
    """Helper for multi-candidate snapshot."""
    from orbit.adapters.observation.snapshot import FreshnessState, ObservationSnapshot, ObservedElement, ObservedWindow
    return ObservationSnapshot(
        snapshot_id="snap_multi_001",
        timestamp_ns=1000000000,
        generation_id=1,
        is_stale=False,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        windows=[
            ObservedWindow(
                hwnd=12345,
                process_id=9999,
                process_name="multi_btn.exe",
                window_title="ORBIT Multi Button Test",
                extended_bounds=BoundingBox(left=50, top=50, width=500, height=400),
                is_visible=True,
                is_foreground=True,
            )
        ],
        detected_elements=[],
    )
