import ctypes
from ctypes import wintypes
import subprocess
import time

def find_window(tq_clean, exe_name, timeout=3.0):
    t0 = time.time()
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    GetWindowRect = ctypes.windll.user32.GetWindowRect

    while time.time() - t0 < timeout:
        found_hwnds = []
        def _enum_cb(hwnd, lparam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLength(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowText(hwnd, buff, length + 1)
                    w_title = buff.value
                    if tq_clean in w_title.lower() or tq_clean in exe_name.lower():
                        r = wintypes.RECT()
                        if GetWindowRect(hwnd, ctypes.byref(r)):
                            if (r.right - r.left) > 50 and (r.bottom - r.top) > 50:
                                found_hwnds.append((hwnd, w_title, r))
            return True

        cb = WNDENUMPROC(_enum_cb)
        ctypes.windll.user32.EnumWindows(cb, 0)
        if found_hwnds:
            return found_hwnds
        time.sleep(0.3)
    return []

# Test Paint
print("Launching Paint...")
subprocess.Popen(["mspaint.exe"], shell=False)
hwnds = find_window("paint", "mspaint.exe")
print(f"Paint search found {len(hwnds)} windows:")
for h, t, r in hwnds:
    print(f"  - HWND {h}: '{t}' ({r.left}, {r.top}, {r.right-r.left}, {r.bottom-r.top})")
