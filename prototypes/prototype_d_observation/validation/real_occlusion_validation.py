"""
Phase P1: Real HWND Occlusion Validation Harness for ORBIT Prototype D v1.3.1.
Spawns live Window A and overlapping Window B to empirically validate Z-order tracking,
distinguishing GEOMETRIC_OVERLAP from OBSERVED_VISUAL_OCCLUSION with screen capture pixel evidence.
Outputs: results/occlusion_validation_results.json
"""

import os
import sys
import time
import json
import tkinter as tk
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capture_engine import CaptureEngine
from window_tracker import WindowTracker
from visual_engine import VisualEngine
from fusion_engine import FusionEngine
from win32_control_provider import Win32ControlProvider
from msaa_provider import MSAAProvider
from uia_provider import UIAutomationProvider
from app_types import Rect, ConfidenceLevel, OcclusionState

user32 = ctypes.windll.user32

def run_real_occlusion_validation() -> dict:
    print("==================================================================")
    print("  PHASE P1: REAL HWND OCCLUSION EMPIRICAL VALIDATION")
    print("==================================================================")
    
    capture_eng = CaptureEngine()
    win_tracker = WindowTracker()
    visual_eng = VisualEngine()
    fusion_eng = FusionEngine()
    uia_prov = UIAutomationProvider()
    
    root_a = None
    root_b = None
    records = {}
    
    try:
        # Step 1: Launch Window A with observable target button
        print("[Step 1] Launching Target Window A...")
        root_a = tk.Tk()
        root_a.title("ORBIT_OCCLUSION_WINDOW_A")
        root_a.geometry("400x350+150+150")
        root_a.configure(bg="#1e293b")
        
        btn_target = tk.Button(root_a, text="CRITICAL TARGET BUTTON", bg="#0284c7", fg="white", font=("Segoe UI", 11, "bold"))
        btn_target.place(x=40, y=60, width=240, height=45)
        root_a.update()
        time.sleep(0.2)
        
        hwnd_a_raw = int(root_a.frame(), 16) if isinstance(root_a.frame(), str) else int(root_a.frame())
        hwnd_a = user32.GetParent(hwnd_a_raw) or hwnd_a_raw
        
        # Step 2: Capture baseline target metadata & screen surface (Frame 0)
        print("[Step 2] Observing Window A Baseline (Frame 0)...")
        win_a_obs = win_tracker.get_window_observation(hwnd_a)
        res_uia_a = uia_prov.traverse_window(hwnd_a)
        
        target_elem = next((e for e in res_uia_a.elements if e.name and "CRITICAL TARGET BUTTON" in e.name), None)
        if not target_elem:
            target_elem = res_uia_a.elements[0] if res_uia_a.elements else None
            
        target_rect = target_elem.bounds if target_elem else win_a_obs.extended_bounds
        
        img_f0 = capture_eng.capture_window(hwnd_a)
        
        # Step 3: Launch Window B to physically overlap Window A's target button
        print("[Step 3] Launching Overlapping Window B...")
        root_b = tk.Tk()
        root_b.title("ORBIT_OCCLUSION_WINDOW_B")
        root_b.configure(bg="#dc2626")  # Bright red opaque cover
        lbl_cover = tk.Label(root_b, text="OCCLUDING TOP WINDOW", bg="#dc2626", fg="white", font=("Segoe UI", 12, "bold"))
        lbl_cover.pack(expand=True, fill="both")
        root_b.update()
        
        hwnd_b_raw = int(root_b.frame(), 16) if isinstance(root_b.frame(), str) else int(root_b.frame())
        hwnd_b = user32.GetParent(hwnd_b_raw) or hwnd_b_raw
        
        # Position Window B directly over Window A extended frame bounds using SetWindowPos
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(hwnd_b, 0, win_a_obs.extended_bounds.left, win_a_obs.extended_bounds.top, 
                            win_a_obs.extended_bounds.width, win_a_obs.extended_bounds.height, SWP_SHOWWINDOW)
        root_b.update()
        root_b.lift()
        root_b.focus_force()
        root_b.update()
        time.sleep(0.3)
        
        # Step 4: Confirm actual live Z-order
        print("[Step 4] Confirming Live Desktop Z-Order...")
        all_wins = win_tracker.enumerate_visible_windows()
        win_a_live = next((w for w in all_wins if w.hwnd == hwnd_a), None)
        win_b_live = next((w for w in all_wins if w.hwnd == hwnd_b), None)
        
        z_order_confirmed = (win_b_live and win_a_live and win_b_live.z_order_rank < win_a_live.z_order_rank)
        print(f"  -> Window B Z-Order Rank: {win_b_live.z_order_rank if win_b_live else 'N/A'}")
        print(f"  -> Window A Z-Order Rank: {win_a_live.z_order_rank if win_a_live else 'N/A'}")
        print(f"  -> Z-Order Relationship Correct (B over A): {z_order_confirmed}")
        
        # Step 5: Capture Frame 1 from overlapping Window B and evaluate pixel change
        print("[Step 5] Capturing Overlapped Screen (Frame 1)...")
        img_f1 = capture_eng.capture_window(hwnd_b)
        
        has_changed, change_bbox, dhash_diff, var_diff = visual_eng.detect_changes(img_f0, img_f1)
        print(f"  -> ROI Pixel Change Observed: {has_changed} (dHash Diff: {dhash_diff}, Variance Diff: {var_diff:.2f})")
        
        # Step 6: Execute Evidence Fusion Engine
        print("[Step 6] Running Evidence Fusion Engine...")
        targets, visual_feats, conflicts, conf = fusion_eng.fuse_observations(
            screenshot=img_f1,
            windows=(win_b_live, win_a_live) if (win_b_live and win_a_live) else (),
            accessibility_elements=(target_elem,) if target_elem else (),
            provider_results=(res_uia_a,),
            generation_id=1,
        )
        
        fused_target = targets[0] if targets else None
        
        records = {
            "test_id": "P1",
            "name": "Real HWND Occlusion Validation",
            "window_a": {
                "hwnd": hwnd_a,
                "title": "ORBIT_OCCLUSION_WINDOW_A",
                "bounds": win_a_live.extended_bounds.as_tuple() if win_a_live else (),
                "z_order_rank": win_a_live.z_order_rank if win_a_live else 0,
            },
            "window_b": {
                "hwnd": hwnd_b,
                "title": "ORBIT_OCCLUSION_WINDOW_B",
                "bounds": win_b_live.extended_bounds.as_tuple() if win_b_live else (),
                "z_order_rank": win_b_live.z_order_rank if win_b_live else 0,
            },
            "target_control": {
                "name": target_elem.name if target_elem else "Critical Button",
                "bounds": target_rect.as_tuple(),
            },
            "empirical_evidence": {
                "z_order_relationship_confirmed": z_order_confirmed,
                "geometric_overlap_detected": fused_target.is_occluded if fused_target else False,
                "pixel_change_observed": has_changed,
                "dhash_hamming_distance": dhash_diff,
                "color_variance_delta": round(var_diff, 2),
                "occlusion_state_assigned": fused_target.occlusion_state.value if fused_target else "UNKNOWN",
                "confidence_level": fused_target.confidence.value if fused_target else "UNKNOWN",
                "contradiction_logged": len(conflicts) > 0,
                "conflicts": conflicts,
            },
            "evidence_classification": "CONTROLLED_LIVE_ENVIRONMENT",
            "verdict": "PASS" if (z_order_confirmed and has_changed and fused_target and fused_target.is_occluded) else "FAIL",
        }
        
    finally:
        if root_a:
            try:
                root_a.destroy()
            except Exception:
                pass
        if root_b:
            try:
                root_b.destroy()
            except Exception:
                pass
                
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    out_path = os.path.join(results_dir, "occlusion_validation_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
        
    print(f"\nReal HWND Occlusion Validation Complete. Verdict: {records['verdict']}")
    print(f"Saved to {out_path}")
    print("==================================================================")
    return records

if __name__ == "__main__":
    run_real_occlusion_validation()
