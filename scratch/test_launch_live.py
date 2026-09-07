import subprocess
import time
import os
import ctypes
from ctypes import wintypes

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

def find_window(target_query, exe_name):
    tq_clean = target_query.strip().lower()
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    found = []
    def enum_cb(h, _):
        if user32.IsWindowVisible(h):
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            w = r.right - r.left
            height = r.bottom - r.top
            if w > 50 and height > 50:
                length = user32.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                title = buf.value
                pid, pname = get_proc_name(h)
                
                title_match = bool(title and tq_clean in title.lower())
                proc_match = bool(pname and (tq_clean in pname.lower() or exe_name.lower() in pname.lower()))
                
                if title_match or proc_match:
                    found.append((h, pid, pname, title, w, height))
        return True

    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_cb)
    if hdesk:
        user32.EnumDesktopWindows(hdesk, cb, 0)
        user32.CloseDesktop(hdesk)
    return found

print("Launching mspaint.exe...")
p = subprocess.Popen(["mspaint.exe"])
for i in range(20):
    time.sleep(0.2)
    wins = find_window("paint", "mspaint.exe")
    if wins:
        print(f"Found Paint window after {i*0.2:.1f}s:", wins)
        break
else:
    print("Paint window not found within timeout!")

print("\nLaunching notepad.exe...")
p2 = subprocess.Popen(["notepad.exe"])
for i in range(20):
    time.sleep(0.2)
    wins = find_window("notepad", "notepad.exe")
    if wins:
        print(f"Found Notepad window after {i*0.2:.1f}s:", wins)
        break
else:
    print("Notepad window not found within timeout!")
