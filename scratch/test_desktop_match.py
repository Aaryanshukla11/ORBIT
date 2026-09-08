import ctypes
from ctypes import wintypes
import subprocess
import time
import sys

# Do NOT call SetThreadDesktop("Default")!
# Keep current thread desktop.

user32 = ctypes.windll.user32

p = subprocess.Popen(["mspaint.exe"])
time.sleep(3)

print("Observing windows on CURRENT desktop without forcing 'Default'...")
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

found = []
def enum_cb(hwnd, _):
    if not user32.IsWindowVisible(hwnd):
        return True
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return True
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value.strip()
    if not title or title in ("Program Manager", "Default IME", "MSCTFIME UI"):
        return True
    
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    
    found.append((hwnd, title, cls_buf.value))
    return True

user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

print(f"Total visible windows on current desktop: {len(found)}")
for h, t, c in found:
    print(f"  HWND={h:<10} | Title={t!r:<30} | Class={c}")

subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
