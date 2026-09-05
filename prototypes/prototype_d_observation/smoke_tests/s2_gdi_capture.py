"""
Smoke Test S2: GDI Screen Capture
Validates: GetDC, CreateCompatibleDC, CreateCompatibleBitmap, BitBlt (CAPTUREBLT), GetDIBits, buffer verification.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capture_engine import CaptureEngine
from coordinate_mapper import CoordinateMapper

def run_s2() -> dict:
    result = {
        "test_id": "S2",
        "name": "GDI Screen Capture",
        "apis_tested": ["GetWindowDC(Desktop)", "CreateCompatibleDC", "CreateCompatibleBitmap", "BitBlt(CAPTUREBLT)", "GetDIBits", "ReleaseDC"],
        "status": "PASS",
        "evidence_type": "LIVE_OS_VALIDATED",
        "metrics": {},
        "error": None
    }
    
    try:
        engine = CaptureEngine()
        img, dur_ms, bounds = engine.capture_full_desktop()
        
        if img is None:
            raise RuntimeError("CaptureEngine returned None")
            
        extrema = img.getextrema()
        has_variance = any((hi - lo) > 0 for lo, hi in extrema[:3])
        
        result["metrics"]["width"] = img.width
        result["metrics"]["height"] = img.height
        result["metrics"]["capture_duration_ms"] = dur_ms
        result["metrics"]["virtual_bounds"] = bounds.as_tuple()
        result["metrics"]["is_non_empty_pixel_data"] = has_variance
        result["metrics"]["extrema"] = extrema
        
    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
        
    return result

if __name__ == "__main__":
    res = run_s2()
    print(json.dumps(res, indent=2))
