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
                    if 'paint' in buf.value.lower() or 'paint' in cls_buf.value.lower():
                        wins.append((hwnd, buf.value, cls_buf.value))
            return True
        cb = WNDENUMPROC(proc)
        user32.EnumWindows(cb, 0)
        return wins

print("Initial Paint windows:", find_paint())

print("\nAttempt 1: os.startfile('mspaint')")
try:
    os.startfile('mspaint')
except Exception as e:
    print("startfile err:", e)
time.sleep(3.0)
p1 = find_paint()
print("Paint after Attempt 1:", p1)

if not p1:
    print("\nAttempt 2: subprocess.Popen(['cmd.exe', '/c', 'start', 'mspaint'])")
    subprocess.Popen(['cmd.exe', '/c', 'start', 'mspaint'], shell=True)
    time.sleep(3.0)
    p2 = find_paint()
    print("Paint after Attempt 2:", p2)
