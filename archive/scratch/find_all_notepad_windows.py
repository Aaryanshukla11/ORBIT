import ctypes
from ctypes import wintypes
import os
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

proc = subprocess.Popen(["notepad.exe"])
print("Launched notepad with PID:", proc.pid)
time.sleep(3)

notepad_pid = proc.pid
found_windows = []

def cb(hwnd, _):
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
    
    # Check if pid matches or title/class has notepad
    if pid.value == notepad_pid or "notepad" in title.lower() or "notepad" in cls_name.lower():
        found_windows.append({
            "hwnd": hwnd,
            "pid": pid.value,
            "title": title,
            "class": cls_name,
            "visible": vis,
        })
    return True

user32.EnumWindows(WNDENUMPROC(cb), 0)
print(f"Direct EnumWindows found {len(found_windows)} windows:")
for fw in found_windows:
    print(" ", fw)

# Now check UI Automation!
print("\nChecking via UI Automation Desktop root...")
try:
    import uiautomation as auto
    root = auto.GetRootControl()
    notepad_ctrl = root.WindowControl(searchDepth=1, SubName="Notepad")
    if notepad_ctrl.Exists(0, 0):
        print(f"UIA Found Notepad: Name={notepad_ctrl.Name!r}, Class={notepad_ctrl.ClassName!r}, NativeWindowHandle={notepad_ctrl.NativeWindowHandle}")
    else:
        print("UIA did not find WindowControl with SubName='Notepad' at depth 1. Listing all depth 1 windows:")
        for c in root.GetChildren():
            if c.ControlType == auto.ControlType.WindowControl or "notepad" in c.Name.lower():
                print(f"  UIA Child: Name={c.Name!r}, Class={c.ClassName!r}, Handle={c.NativeWindowHandle}")
except Exception as ex:
    print("UIA Exception:", ex)

proc.terminate()
