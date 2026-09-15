import ctypes
from ctypes import wintypes
import subprocess
import time

print("Launching Paint via mspaint.exe...")
p = subprocess.Popen(["mspaint.exe"], shell=False)
time.sleep(1.5)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
GetWindowText = ctypes.windll.user32.GetWindowTextW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetWindowRect = ctypes.windll.user32.GetWindowRect

all_wins = []
def _enum(hwnd, lparam):
    if IsWindowVisible(hwnd):
        length = GetWindowTextLength(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            title = buff.value
            r = wintypes.RECT()
            GetWindowRect(hwnd, ctypes.byref(r))
            w = r.right - r.left
            h = r.bottom - r.top
            all_wins.append((hwnd, title, (r.left, r.top, w, h)))
    return True

ctypes.windll.user32.EnumWindows(WNDENUMPROC(_enum), 0)
print(f"Total visible titled windows: {len(all_wins)}")
for hwnd, title, rect in all_wins:
    if any(k in title.lower() for k in ["paint", "notepad", "code", "orbit"]):
        print(f"  - HWND {hwnd}: '{title}' {rect}")
