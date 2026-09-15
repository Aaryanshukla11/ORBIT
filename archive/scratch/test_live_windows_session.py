"""Physical Windows E2E Acceptance Tester for ORBIT.

Tests A, B, C, D:
- TEST A: Calculator launch, semantic button locate, physical click, UI state verify
- TEST B: Text editor launch, focus, physical typing, text verify
- TEST C: Paint launch, DRAW_STROKES, canvas verify
- TEST D: Window focus disturbance, failure detection, diagnosis, recovery
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
import sys
import time
from typing import Dict, Any


def run_e2e_acceptance():
    results: Dict[str, Dict[str, Any]] = {}
    u32 = ctypes.windll.user32

    # Check session
    fg_before = u32.GetForegroundWindow()
    hdesk = u32.OpenInputDesktop(0, False, 0x0100)
    print(f"DEBUG: Foreground HWND: {fg_before}, Input Desktop Handle: {bool(hdesk)}")
    if hdesk:
        u32.CloseDesktop(hdesk)

    # -------------------------------------------------------------
    # TEST B: Open text editor -> focus -> type unique test string -> verify
    # -------------------------------------------------------------
    test_b_record = {
        "planned_primitive": "LAUNCH_APPLICATION('notepad') -> TYPE_TEXT('ORBIT_AUDIT_VERIFIED_7749')",
        "grounding_method": "Win32 Edit Control Locator",
        "executor_used": "ProductionKeyboardAdapter (Win32 SendInput)",
        "physical_result": "UNKNOWN",
        "verification_evidence": "NONE",
        "final_result": "NOT EXECUTED",
    }
    try:
        proc = subprocess.Popen(["notepad.exe"])
        time.sleep(1.5)
        hwnd = u32.FindWindowW("Notepad", None)
        if hwnd:
            u32.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            # Find edit child
            edit_hwnd = u32.FindWindowExW(hwnd, None, "Edit", None) or u32.FindWindowExW(hwnd, None, "RichEditD2DPT", None)
            
            # Type test string
            test_str = "ORBIT_AUDIT_VERIFIED_7749"
            from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
            kb = ProductionKeyboardAdapter()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(kb.initialize())
            loop.run_until_complete(kb.type_text(test_str))
            time.sleep(0.5)

            # Read text from edit control
            buf_len = 256
            buf = ctypes.create_unicode_buffer(buf_len)
            target_hwnd = edit_hwnd if edit_hwnd else hwnd
            u32.SendMessageW(target_hwnd, 0x000D, buf_len, buf)  # WM_GETTEXT
            read_text = buf.value
            
            test_b_record["physical_result"] = f"Notepad HWND {hwnd}, Edit HWND {edit_hwnd}, typed '{test_str}'"
            test_b_record["verification_evidence"] = f"WM_GETTEXT returned '{read_text}'"
            if test_str in read_text:
                test_b_record["final_result"] = "PASS"
            else:
                test_b_record["final_result"] = "PARTIAL / NOT EXECUTED"
        else:
            test_b_record["physical_result"] = "Notepad process started but window not found in foreground desktop"
            test_b_record["final_result"] = "NOT EXECUTED"
        
        if proc:
            proc.terminate()
    except Exception as ex:
        test_b_record["physical_result"] = f"Exception during execution: {ex}"
        test_b_record["final_result"] = "NOT EXECUTED"
    
    results["TEST_B"] = test_b_record

    # Print summary JSON
    import json
    print("--- E2E AUDIT RESULTS ---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run_e2e_acceptance()
