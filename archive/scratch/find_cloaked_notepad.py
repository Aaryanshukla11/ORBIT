import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Kill any existing notepad
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

print("Starting notepad via cmd /c start notepad...")
subprocess.run("cmd /c start notepad", shell=True)
time.sleep(4)

# Find all Notepad PIDs and their thread desktops
p = subprocess.run(["tasklist", "/fi", "imagename eq notepad*"], capture_output=True, text=True)
print(p.stdout)

# Find all HWNDs owned by any Notepad PID, visible or invisible
notepad_hwnds = []
def enum_any(hwnd, _):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    
    vis = bool(user32.IsWindowVisible(hwnd))
    
    # Check DwmGetWindowAttribute for cloaked
    is_cloaked = ctypes.c_int(0)
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(is_cloaked), ctypes.sizeof(is_cloaked))
    except Exception:
        pass
    
    if "notepad" in buf.value.lower() or "notepad" in cls_buf.value.lower():
        notepad_hwnds.append((hwnd, pid.value, buf.value, cls_buf.value, vis, is_cloaked.value))
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(enum_any), 0)

print(f"EnumWindows found {len(notepad_hwnds)} notepad windows:")
for h in notepad_hwnds:
    print("  ", h)

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
