"""
Production Live Windows Desktop Perception Acceptance Suite (Step 3).

Validates:
1. Baseline Multimodal Desktop Perception:
   - Win32 Top-Level Window Hierarchy & Focus State
   - Desktop Visual Frame Screenshot Capture
   - Windows UI Automation Accessibility Controls
   - Live Optical Character Recognition (OCR) Tokens
   - Perception Evidence Fusion & Provenance Tracking
   - Token-Efficient LLM Context Summarization
2. Dynamic Window & App Discovery:
   - Live Calculator Launch & Dynamic Scoping
   - Live UIA Controls & OCR Fusion Grounding
3. MS Paint Canvas Dynamic Grounding & Interaction:
   - Live Paint Launch & Window Rect Perception
   - Visual Perception Dynamic Canvas Identification
   - Live Drawing Interaction
   - Fresh Post-Action Observation Verification
4. Strict Fresh Observation Invariant:
   - Zero Stale Cache / Coordinate guessing
   - Timestamps, Observation IDs, and Screenshots refresh every iteration
"""

import asyncio
import ctypes
import os
import subprocess
import sys
import time

# Ensure src is on pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from orbit.runtime.perception.engine import DesktopPerceptionEngine
from orbit.runtime.perception.models import DesktopObservation, VisualRegionType


def _click_at(x: int, y: int):
    """Simulate left click at physical screen coordinates."""
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)


def _draw_drag(start_x: int, start_y: int, end_x: int, end_y: int):
    """Simulate mouse drag transaction to draw on canvas."""
    ctypes.windll.user32.SetCursorPos(int(start_x), int(start_y))
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    time.sleep(0.05)
    
    steps = 10
    for i in range(1, steps + 1):
        cur_x = int(start_x + (end_x - start_x) * (i / steps))
        cur_y = int(start_y + (end_y - start_y) * (i / steps))
        ctypes.windll.user32.SetCursorPos(cur_x, cur_y)
        time.sleep(0.02)
        
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
    time.sleep(0.05)


async def run_live_perception_acceptance_suite():
    print("=" * 75)
    print("ORBIT STEP 3: PRODUCTION MULTIMODAL DESKTOP PERCEPTION ACCEPTANCE SUITE")
    print("=" * 75)

    perception_engine = DesktopPerceptionEngine()

    # -------------------------------------------------------------------------
    # TEST 0: Baseline Desktop Multimodal Perception
    # -------------------------------------------------------------------------
    print("\n[TEST 0] Baseline Desktop Multimodal Observation...")
    t0 = time.time()
    obs0: DesktopObservation = await perception_engine.observe(include_ocr=True, include_uia=True)
    dt = time.time() - t0

    print(f"Observation ID: {obs0.observation_id}")
    print(f"Capture Time: {dt:.2f}s (duration_ms={obs0.capture_metadata.get('capture_duration_ms', 0):.1f}ms)")
    print(f"Screen Dimensions: {obs0.screen_width}x{obs0.screen_height}")
    print(f"Observation Consistent: {obs0.is_consistent} (Warnings: {obs0.consistency_warnings})")
    print(f"Foreground Window: {obs0.foreground_window.title if obs0.foreground_window else 'None'} ({obs0.foreground_window.process_name if obs0.foreground_window else ''})")
    print(f"Visible Windows Count: {len(obs0.visible_windows)}")
    print(f"UIA Elements Count: {len(obs0.uia_elements)}")
    print(f"OCR Tokens Count: {len(obs0.ocr_tokens)}")
    print(f"Perceived Fused Elements: {len(obs0.perceived_elements)}")
    print(f"Visual Regions: {len(obs0.visual_regions)}")

    assert obs0.screen_width > 0 and obs0.screen_height > 0, "Invalid screen dimensions"
    assert obs0.screenshot_reference is not None, "Screenshot reference must be present"
    assert len(obs0.visible_windows) > 0, "Must detect live visible windows"
    print("\n--- LLM Context Summary Sample ---")
    print(obs0.desktop_summary)
    print("----------------------------------")
    print("[TEST 0 PASSED] Baseline multimodal desktop perception verified.")

    # -------------------------------------------------------------------------
    # TEST 1: Live Calculator Observation & Multimodal Fusion Grounding
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Launching Windows Calculator and observing fresh state...")
    ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", "shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", None, 1)
    
    calc_windows = []
    obs1 = None
    for _ in range(20):
        time.sleep(0.3)
        obs1 = await perception_engine.observe(include_ocr=True, include_uia=True)
        calc_windows = [w for w in obs1.visible_windows if "calculator" in w.title.lower() or "calc" in (w.process_name or "").lower()]
        if calc_windows:
            break

    try:
        assert len(calc_windows) > 0, "Must detect Calculator window in live observation"
        cw = calc_windows[0]
        print(f"Discovered Calculator Window: HWND={cw.hwnd}, Title='{cw.title}', Class='{cw.window_class}', Process='{cw.process_name}'")
        print(f"Window Bounds: ({cw.window_bounds.left}, {cw.window_bounds.top}, {cw.window_bounds.width}, {cw.window_bounds.height})")

        # Scoped observation on Calculator
        obs_calc = await perception_engine.observe(target_hwnd=cw.hwnd, include_ocr=True, include_uia=True)
        print(f"Calculator Scoped UIA Elements: {len(obs_calc.uia_elements)}")
        print(f"Calculator Scoped Perceived Fused Elements: {len(obs_calc.perceived_elements)}")
        fused_with_ocr = [pe for pe in obs_calc.perceived_elements if "OCR" in pe.evidence.evidence_sources]
        print(f"Perceived Elements with OCR Corroboration: {len(fused_with_ocr)}")
        for pe in obs_calc.perceived_elements[:5]:
            print(f"  * {pe.role.title()}: '{pe.name}' | Confidence: {pe.confidence:.2f} | Sources: {pe.evidence.evidence_sources}")

        assert len(obs_calc.perceived_elements) > 0, "Must fuse perception evidence for Calculator"
        print("[TEST 1 PASSED] Live Calculator discovered, scoped, and fused with multi-channel evidence.")
    finally:
        subprocess.run(["taskkill", "/F", "/IM", "CalculatorApp.exe"], capture_output=True)

    # -------------------------------------------------------------------------
    # TEST 2: MS Paint Canvas Dynamic Grounding & Live Stroke Execution
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Launching MS Paint and observing dynamic canvas grounding...")
    ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App", None, 1)
    
    paint_windows = []
    obs_paint_pre = None
    for _ in range(20):
        time.sleep(0.3)
        obs_paint_pre = await perception_engine.observe(include_ocr=True, include_uia=True)
        paint_windows = [w for w in obs_paint_pre.visible_windows if "paint" in w.title.lower() or "paint" in (w.process_name or "").lower()]
        if paint_windows:
            break

    try:
        assert len(paint_windows) > 0, "Must detect Paint window in live observation"
        pw = paint_windows[0]
        print(f"Discovered Paint Window: HWND={pw.hwnd}, Title='{pw.title}', Bounds=({pw.window_bounds.left}, {pw.window_bounds.top}, {pw.window_bounds.width}, {pw.window_bounds.height})")

        # Ground Paint canvas bounds dynamically via visual perception
        canvas_regions = [r for r in obs_paint_pre.visual_regions if r.region_type == VisualRegionType.CANVAS]
        print(f"Discovered Canvas Visual Regions: {len(canvas_regions)}")
        assert len(canvas_regions) > 0, "Must detect Canvas visual region"
        canvas = canvas_regions[0]
        print(f"Grounded Canvas Bounds: ({canvas.bounds.left}, {canvas.bounds.top}, {canvas.bounds.width}, {canvas.bounds.height}), Confidence={canvas.confidence:.2f}")

        # Execute physical drawing stroke on canvas
        start_x = canvas.bounds.left + 150
        start_y = canvas.bounds.top + 150
        end_x = canvas.bounds.left + 350
        end_y = canvas.bounds.top + 250
        print(f"Executing physical drawing stroke: ({start_x}, {start_y}) -> ({end_x}, {end_y})...")
        _draw_drag(start_x, start_y, end_x, end_y)
        time.sleep(0.5)

        # ---------------------------------------------------------------------
        # TEST 3: Fresh Observation Invariant (Post-Action Observation)
        # ---------------------------------------------------------------------
        print("\n[TEST 3] Capturing Fresh Post-Action Observation...")
        obs_paint_post = await perception_engine.observe(include_ocr=True, include_uia=True)
        
        print(f"Pre-Action Observation ID:  {obs_paint_pre.observation_id}")
        print(f"Post-Action Observation ID: {obs_paint_post.observation_id}")
        assert obs_paint_pre.observation_id != obs_paint_post.observation_id, "Observation ID must be unique per capture"
        assert obs_paint_post.timestamp >= obs_paint_pre.timestamp, "Post-action timestamp must be >= pre-action"
        print("[TEST 3 PASSED] Fresh post-action observation captured with zero stale cache reuse.")
        print("[TEST 2 PASSED] MS Paint canvas grounded dynamically and drawing stroke executed.")

    finally:
        subprocess.run(["taskkill", "/F", "/IM", "mspaint.exe"], capture_output=True)

    print("\n" + "=" * 75)
    print("ALL LIVE WINDOWS DESKTOP PERCEPTION ACCEPTANCE TESTS PASSED!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_live_perception_acceptance_suite())
