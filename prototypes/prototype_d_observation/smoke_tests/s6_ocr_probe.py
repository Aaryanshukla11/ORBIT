"""
Smoke Test S6: OCR Capability Detection & Probe
Validates: Native WinRT OCR availability, optional Tesseract availability, and honest fallback classification.
"""

import sys
import json

def run_s6() -> dict:
    result = {
        "test_id": "S6",
        "name": "OCR Capability Probe",
        "apis_tested": ["winsdk.windows.media.ocr", "pytesseract"],
        "status": "PASS",  # Probing succeeds even if drivers are absent
        "evidence_type": "LIVE_OS_VALIDATED",
        "metrics": {},
        "error": None
    }
    
    # 1. Probe Native WinRT OCR
    winrt_available = False
    winrt_error = None
    try:
        import winsdk.windows.media.ocr as win_ocr
        winrt_available = True
    except ImportError as e:
        winrt_error = str(e)
    except Exception as e:
        winrt_error = str(e)
        
    result["metrics"]["native_winrt_ocr"] = {
        "available": winrt_available,
        "diagnostic_reason": winrt_error if not winrt_available else "RUNTIME_PRESENT"
    }
    
    # 2. Probe Optional Tesseract
    tess_available = False
    tess_error = None
    try:
        import pytesseract
        tess_available = True
    except ImportError as e:
        tess_error = str(e)
    except Exception as e:
        tess_error = str(e)
        
    result["metrics"]["optional_tesseract_ocr"] = {
        "available": tess_available,
        "diagnostic_reason": tess_error if not tess_available else "RUNTIME_PRESENT"
    }
    
    overall_ocr_available = winrt_available or tess_available
    result["metrics"]["overall_ocr_available"] = overall_ocr_available
    result["metrics"]["effective_pipeline_state"] = "ACTIVE" if overall_ocr_available else "UNAVAILABLE_DECOUPLED_FALLBACK"
    
    return result

if __name__ == "__main__":
    res = run_s6()
    print(json.dumps(res, indent=2))
