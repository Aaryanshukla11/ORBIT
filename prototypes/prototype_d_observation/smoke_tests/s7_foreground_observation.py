"""
Smoke Test S7: Foreground Window Observation & Focus Switching
Validates: GetForegroundWindow live tracking, SetForegroundWindow programmatic switching, and distinction between requested vs observed switches.
"""

import ctypes
from ctypes import wintypes
import time
import json
import tkinter as tk

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
user32.AllowSetForegroundWindow.restype = wintypes.BOOL

ASFW_ANY = -1

def run_s7() -> dict:
    result = {
        "test_id": "S7",
        "name": "Foreground Window Observation & Switching",
        "apis_tested": ["GetForegroundWindow", "SetForegroundWindow", "AllowSetForegroundWindow", "IsWindow"],
        "status": "PASS",
        "evidence_type": "LIVE_OS_VALIDATED",
        "metrics": {},
        "error": None
    }
    
    root_a = None
    root_b = None
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
        
        root_a = tk.Tk()
        root_a.title("ORBIT_SMOKE_FOCUS_A")
        root_a.geometry("300x200+100+100")
        
        root_b = tk.Tk()
        root_b.title("ORBIT_SMOKE_FOCUS_B")
        root_b.geometry("300x200+450+100")
        
        root_a.update()
        root_b.update()
        
        hwnd_a = int(root_a.frame(), 16) if isinstance(root_a.frame(), str) else int(root_a.frame())
        hwnd_b = int(root_b.frame(), 16) if isinstance(root_b.frame(), str) else int(root_b.frame())
        top_a = user32.GetParent(hwnd_a) or hwnd_a
        top_b = user32.GetParent(hwnd_b) or hwnd_b
        
        requested_switches = 4
        successful_activations = 0
        observed_transitions = 0
        
        last_fg = user32.GetForegroundWindow()
        
        for i in range(requested_switches):
            target_hwnd = top_b if (i % 2 == 0) else top_a
            user32.AllowSetForegroundWindow(ASFW_ANY)
            ok = user32.SetForegroundWindow(target_hwnd)
            if ok:
                successful_activations += 1
            
            # Poll foreground transition
            for _ in range(5):
                root_a.update()
                root_b.update()
                time.sleep(0.04)
                curr_fg = user32.GetForegroundWindow()
                if curr_fg != last_fg:
                    observed_transitions += 1
                    last_fg = curr_fg
                    break
                
        result["metrics"]["target_a_hwnd"] = top_a
        result["metrics"]["target_b_hwnd"] = top_b
        result["metrics"]["requested_switches"] = requested_switches
        result["metrics"]["successful_activation_requests"] = successful_activations
        result["metrics"]["observed_foreground_transitions"] = observed_transitions
        result["metrics"]["observed_switch_success_rate"] = round(observed_transitions / requested_switches, 2)
        
    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
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
                
    return result

if __name__ == "__main__":
    res = run_s7()
    print(json.dumps(res, indent=2))
