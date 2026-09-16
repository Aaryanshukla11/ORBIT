import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

p = subprocess.Popen(["mspaint.exe"])
time.sleep(3)

# Find Untitled - Paint window
paint_hwnd = None
paint_tid = None

def cb(hwnd, _):
    global paint_hwnd, paint_tid
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    if "paint" in buf.value.lower():
        paint_hwnd = hwnd
        tid = wintypes.DWORD()
        paint_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        print(f"Found window HWND={hwnd}, Title={buf.value!r}, TID={paint_tid}, PID={tid.value}")
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(cb), 0)

if paint_tid:
    h_thread = kernel32.OpenThread(0x0040, False, paint_tid) # THREAD_QUERY_INFORMATION
    desk = user32.GetThreadDesktop(paint_tid)
    name_buf = ctypes.create_unicode_buffer(256)
    needed = wintypes.DWORD()
    user32.GetUserObjectInformationW(desk, 2, name_buf, 256, ctypes.byref(needed))
    print(f"Paint thread desktop handle={desk}, name={name_buf.value!r}")

subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
