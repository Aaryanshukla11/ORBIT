"""
Phase P3: Multi-Monitor Reality Validation Harness for ORBIT Prototype D v1.3.1.
Discovers live display topology, evaluates coordinate conversion accuracy, and strictly classifies
multi-monitor hardware capability as PHYSICALLY_VALIDATED (if >=2 monitors) or NOT_PHYSICALLY_VALIDATED (if 1 monitor),
while validating signed negative coordinate math separately as SYNTHETICALLY_SIMULATED.
Outputs: results/monitor_validation_results.json
"""

import os
import sys
import time
import json
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinate_mapper import CoordinateMapper
from app_types import Rect

user32 = ctypes.windll.user32

def run_monitor_reality_validation() -> dict:
    print("==================================================================")
    print("  PHASE P3: MULTI-MONITOR REALITY VALIDATION")
    print("==================================================================")
    
    coord_mapper = CoordinateMapper()
    
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    SM_CMONITORS = 80
    
    v_left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    v_top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    v_width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    v_height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    monitor_count = user32.GetSystemMetrics(SM_CMONITORS) or 1
    
    # Enumerate live monitors via EnumDisplayMonitors
    monitors = []
    MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    
    def monitor_enum_cb(hMonitor, hdc, lprc, lparam):
        r = lprc.contents
        monitors.append({
            "hmonitor": hMonitor,
            "rect": (r.left, r.top, r.right, r.bottom),
            "width": r.right - r.left,
            "height": r.bottom - r.top,
            "is_primary": (r.left == 0 and r.top == 0)
        })
        return True
        
    user32.EnumDisplayMonitors(0, None, MONITORENUMPROC(monitor_enum_cb), 0)
    actual_monitors_count = len(monitors) if monitors else monitor_count
    
    print(f"Live Monitor Count : {actual_monitors_count}")
    print(f"Virtual Desktop    : ({v_left}, {v_top}, {v_width}x{v_height})")
    for idx, m in enumerate(monitors):
        print(f"  Monitor #{idx+1}: {m['width']}x{m['height']} @ ({m['rect'][0]}, {m['rect'][1]}) [Primary: {m['is_primary']}]")
        
    # Coordinate accuracy test against Win32 ClientToScreen
    desk_hwnd = user32.GetDesktopWindow()
    is_acc, err_dist, pt = coord_mapper.verify_coordinate_accuracy(desk_hwnd, 100, 100)
    
    # Signed Negative Coordinate Arithmetic Test (Mathematical Model)
    simulated_negative_rect = (-1920, -200, 400, 300)
    mapped_negative = coord_mapper.accessibility_to_virtual_rect(*simulated_negative_rect)
    math_underflow_prevented = (mapped_negative.left == -1920 and mapped_negative.width == 400 and mapped_negative.height == 300)
    
    # Reality Classification Decision
    if actual_monitors_count >= 2:
        hardware_classification = "PHYSICALLY_VALIDATED"
        hardware_verdict = "PASS"
        notes = f"Physical multi-monitor topology ({actual_monitors_count} displays) verified on live OS."
    else:
        hardware_classification = "NOT_PHYSICALLY_VALIDATED"
        hardware_verdict = "PASS"  # Topology detection passes; hardware limitation honestly classified
        notes = "Single physical monitor detected (SM_CMONITORS=1). Multi-monitor hardware unvalidated; signed coordinate math validated separately as SYNTHETICALLY_SIMULATED."
        
    records = {
        "test_id": "P3",
        "name": "Multi-Monitor Reality Validation",
        "display_topology": {
            "monitor_count": actual_monitors_count,
            "virtual_desktop_rect": (v_left, v_top, v_left + v_width, v_top + v_height),
            "virtual_width": v_width,
            "virtual_height": v_height,
            "enumerated_monitors": monitors,
        },
        "live_coordinate_accuracy": {
            "tested_against": "user32.ClientToScreen",
            "is_accurate_within_1px": is_acc,
            "error_distance_px": err_dist,
            "ground_truth_point": pt,
            "evidence_classification": "LIVE_OS_VALIDATED",
        },
        "signed_negative_coordinate_math": {
            "input_rect": simulated_negative_rect,
            "mapped_rect": mapped_negative.as_tuple(),
            "underflow_prevented": math_underflow_prevented,
            "evidence_classification": "SYNTHETICALLY_SIMULATED",
        },
        "hardware_reality_status": {
            "physical_multi_monitor_available": actual_monitors_count >= 2,
            "evidence_classification": hardware_classification,
            "verdict": hardware_verdict,
            "honest_boundary_notes": notes,
        },
        "overall_verdict": "PASS" if is_acc and math_underflow_prevented else "FAIL",
    }
    
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    out_path = os.path.join(results_dir, "monitor_validation_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
        
    print(f"\nMulti-Monitor Reality Validation Complete. Hardware Classification: {hardware_classification}")
    print(f"Saved to {out_path}")
    print("==================================================================")
    return records

if __name__ == "__main__":
    run_monitor_reality_validation()
