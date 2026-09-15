import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32

p = subprocess.Popen(["mspaint.exe"])
time.sleep(3)

pid = p.pid
print(f"Launched mspaint with PID {pid}")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]

wins = []
def cb(hwnd, _):
    wpid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
    
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    
    vis = bool(user32.IsWindowVisible(hwnd))
    
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    
    if wpid.value == pid or "paint" in buf.value.lower():
        wins.append((hwnd, wpid.value, buf.value, cls_buf.value, vis))
    return True

user32.EnumWindows(WNDENUMPROC(cb), 0)
print(f"Found {len(wins)} windows:")
for w in wins:
    print(" ", w)

# Now check GetForegroundWindow
fg = user32.GetForegroundWindow()
fg_buf = ctypes.create_unicode_buffer(256)
user32.GetWindowTextW(fg, fg_buf, 256)
print(f"Foreground: HWND={fg}, Title={fg_buf.value!r}")

subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
