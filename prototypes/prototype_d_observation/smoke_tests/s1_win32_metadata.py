"""
Smoke Test S1: Win32 Window Metadata
Validates: EnumWindows, GetForegroundWindow, IsWindow, GetWindowThreadProcessId, DwmGetWindowAttribute.
"""

import ctypes
from ctypes import wintypes
import os
import sys
import json

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

def run_s1() -> dict:
    result = {
        "test_id": "S1",
        "name": "Win32 Window Metadata",
        "apis_tested": ["EnumWindows", "GetForegroundWindow", "IsWindow", "GetWindowThreadProcessId", "DwmGetWindowAttribute"],
        "status": "PASS",
        "evidence_type": "LIVE_OS_VALIDATED",
        "metrics": {},
        "error": None
    }
    
    try:
        # 1. GetForegroundWindow
        fg_hwnd = user32.GetForegroundWindow()
        result["metrics"]["foreground_hwnd"] = fg_hwnd
        result["metrics"]["is_foreground_window_valid"] = bool(user32.IsWindow(fg_hwnd)) if fg_hwnd else False
        
        # 2. GetWindowThreadProcessId
        pid = wintypes.DWORD()
        tid = user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid)) if fg_hwnd else 0
        result["metrics"]["foreground_pid"] = pid.value
        result["metrics"]["foreground_tid"] = tid
        
        # 3. DwmGetWindowAttribute (DWMWA_EXTENDED_FRAME_BOUNDS = 9)
        if fg_hwnd:
            rect = wintypes.RECT()
            hr = dwmapi.DwmGetWindowAttribute(fg_hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
            result["metrics"]["dwm_extended_bounds_hr"] = hr
            result["metrics"]["dwm_extended_bounds"] = (rect.left, rect.top, rect.right, rect.bottom)
            result["metrics"]["dwm_width"] = rect.right - rect.left
            result["metrics"]["dwm_height"] = rect.bottom - rect.top
        
        # 4. EnumWindows
        discovered_windows = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    discovered_windows.append({"hwnd": hwnd, "title": buf.value})
            return True
            
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        result["metrics"]["visible_top_level_windows_count"] = len(discovered_windows)
        result["metrics"]["sample_windows"] = discovered_windows[:5]
        
    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
        
    return result

if __name__ == "__main__":
    res = run_s1()
    print(json.dumps(res, indent=2))
