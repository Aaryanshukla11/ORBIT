import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time

user32 = ctypes.windll.user32

# EnumWindows setup
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

# Start a fresh notepad
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

print("Starting notepad.exe...")
ctypes.windll.shell32.ShellExecuteW(None, "open", "notepad.exe", None, None, 1)
time.sleep(3)

# Find all windows and their PIDs
all_windows = []
def enum_all(hwnd, _):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    cls_name = cls_buf.value
    
    vis = bool(user32.IsWindowVisible(hwnd))
    
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    
    all_windows.append({
        "hwnd": hwnd,
        "pid": pid.value,
        "title": title,
        "class": cls_name,
        "visible": vis,
        "rect": (rect.left, rect.top, rect.right, rect.bottom)
    })
    return True

user32.EnumWindows(WNDENUMPROC(enum_all), 0)

# Check processes
p = subprocess.run(["tasklist"], capture_output=True, text=True)
notepad_pids = set()
for line in p.stdout.splitlines():
    if "notepad" in line.lower():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            notepad_pids.add(int(parts[1]))
            print("Notepad process:", line)

print(f"\nScanning {len(all_windows)} windows for Notepad PIDs ({notepad_pids}) or Notepad in title/class...")
found = []
for w in all_windows:
    if w["pid"] in notepad_pids or "notepad" in w["title"].lower() or "notepad" in w["class"].lower():
        found.append(w)
        print("MATCH:", w)

if not found:
    print("NO MATCHING WINDOWS AT ALL! Let's check EnumDesktopWindows...")
    # Check EnumDesktopWindows on Default desktop
    h_desk = user32.OpenInputDesktop(0, False, 0x01FF) or user32.OpenDesktopW("Default", 0, False, 0x01FF)
    print("Desktop handle:", h_desk)
    desk_windows = []
    def enum_desk(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        desk_windows.append((hwnd, pid.value, buf.value))
        return True
    DESKENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumDesktopWindows.argtypes = [wintypes.HDESK, DESKENUMPROC, wintypes.LPARAM]
    user32.EnumDesktopWindows(h_desk, DESKENUMPROC(enum_desk), 0)
    print(f"EnumDesktopWindows found {len(desk_windows)} windows:")
    for hw, p, t in desk_windows:
        if p in notepad_pids or "notepad" in t.lower():
            print("  DESK MATCH:", hw, p, t)

# Cleanup
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
