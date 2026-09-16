import subprocess
import time
import os
import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def get_proc_name(hwnd):
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return 0, ''
    h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h_proc:
        return pid.value, ''
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    name = ''
    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
        name = os.path.basename(buf.value)
    kernel32.CloseHandle(h_proc)
    return pid.value, name

print("Launching mspaint...")
os.system("start mspaint")
time.sleep(2.0)

for p in psutil.process_iter(['pid', 'name']):
    if 'paint' in (p.info['name'] or '').lower():
        print("Paint Process:", p.info)

def check_enum():
    results = []
    def _cb(h, _):
        pid, name = get_proc_name(h)
        length = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(h, buf, length + 1)
        vis = bool(user32.IsWindowVisible(h))
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        if 'paint' in name.lower() or 'paint' in buf.value.lower():
            results.append((h, pid, name, buf.value, vis, r.left, r.top, r.right, r.bottom))
        return True

    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_cb)
    user32.EnumWindows(cb, 0)
    print("EnumWindows Paint matches:", len(results))
    for r in results:
        print(r)

check_enum()
