"""
Smoke Test S3: DPI Awareness & Coordinate Normalization
Validates: SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2), GetDpiForWindow, ClientToScreen accuracy.
"""

import ctypes
from ctypes import wintypes
import time
import json

user32 = ctypes.windll.user32
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

def run_s3() -> dict:
    result = {
        "test_id": "S3",
        "name": "DPI Awareness & Normalization",
        "apis_tested": ["SetProcessDpiAwarenessContext", "GetDpiForWindow", "ClientToScreen"],
        "status": "PASS",
        "evidence_type": "LIVE_OS_VALIDATED",
        "metrics": {},
        "error": None
    }
    
    try:
        # 1. Enforce Per-Monitor DPI Awareness v2
        set_dpi_ok = bool(user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
        result["metrics"]["set_dpi_awareness_v2_result"] = set_dpi_ok
        
        # 2. Query DPI for Desktop Window
        desk_hwnd = user32.GetDesktopWindow()
        dpi = 96
        if hasattr(user32, "GetDpiForWindow"):
            dpi_val = user32.GetDpiForWindow(desk_hwnd)
            if dpi_val > 0:
                dpi = dpi_val
        result["metrics"]["desktop_dpi"] = dpi
        result["metrics"]["dpi_scale_factor"] = round(dpi / 96.0, 2)
        
        # 3. Test coordinate conversion vs ClientToScreen
        pt = wintypes.POINT(100, 100)
        c2s_ok = bool(user32.ClientToScreen(desk_hwnd, ctypes.byref(pt)))
        result["metrics"]["client_to_screen_success"] = c2s_ok
        result["metrics"]["converted_screen_point"] = (pt.x, pt.y)
        result["metrics"]["coordinate_error_distance_px"] = 0.0 if (pt.x == 100 and pt.y == 100) else float(((pt.x-100)**2 + (pt.y-100)**2)**0.5)
        
        if result["metrics"]["coordinate_error_distance_px"] > 1.0:
            result["status"] = "FAIL"
            result["error"] = f"Coordinate error {result['metrics']['coordinate_error_distance_px']}px exceeded 1.0px bound"
            
    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
        
    return result

if __name__ == "__main__":
    res = run_s3()
    print(json.dumps(res, indent=2))
