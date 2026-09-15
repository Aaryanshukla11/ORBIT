import ctypes
from ctypes import wintypes
import subprocess
import time
import sys

user32 = ctypes.windll.user32
p = subprocess.Popen(["mspaint.exe"])
time.sleep(3)
pid = p.pid

def check_hwnd(hwnd):
    vis = user32.IsWindowVisible(hwnd)
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value.strip()
    
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    cls_name = cls_buf.value
    
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    
    wpid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
    
    if wpid.value == pid or "paint" in title.lower():
        print(f"Paint HWND {hwnd}: vis={vis}, len={length}, title={title!r}, class={cls_name!r}, rect=({rect.left},{rect.top},{w},{h})")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def enum_all(hwnd, _):
    check_hwnd(hwnd)
    return True

user32.EnumWindows(WNDENUMPROC(enum_all), 0)
subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
