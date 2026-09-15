import os
import subprocess
import time
import ctypes
import ctypes.wintypes
from orbit.adapters.pointer.safety import attached_to_input_desktop

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

def find_paint():
    with attached_to_input_desktop():
        wins = []
        def proc(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buf, 256)
                    title = buf.value
                    cls_name = cls_buf.value
                    if "antigravity" in title.lower():
                        return True
                    if 'paint' in title.lower() or 'paint' in cls_name.lower():
                        wins.append((hwnd, title, cls_name))
            return True
        cb = WNDENUMPROC(proc)
        user32.EnumWindows(cb, 0)
        return wins

print("Closing stale mspaint processes...")
os.system("taskkill /F /IM mspaint.exe >nul 2>&1")
time.sleep(1.0)

print("\nTesting: os.system('start ms-paint:')")
os.system("start ms-paint:")
time.sleep(3.0)
w = find_paint()
print("Paint windows after start ms-paint::", w)

if not w:
    print("\nTesting: explorer.exe shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App")
    subprocess.Popen(["explorer.exe", "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App"])
    time.sleep(3.0)
    w2 = find_paint()
    print("Paint windows after AppsFolder:", w2)
