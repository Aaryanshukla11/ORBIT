import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Set thread desktop to Default
h_desk = user32.OpenInputDesktop(0, False, 0x01FF) or user32.OpenDesktopW("Default", 0, False, 0x01FF)
user32.SetThreadDesktop(h_desk)

# Launch Notepad via explorer
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

print("Launching Notepad...")
subprocess.Popen(["notepad.exe"])
time.sleep(4)

# Enumerate
DESKENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
windows = []

def cb(hwnd, _):
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    
    cls_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buf, 256)
    
    vis = bool(user32.IsWindowVisible(hwnd))
    
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    if buf.value or vis:
        windows.append((hwnd, pid.value, buf.value, cls_buf.value, vis))
    return True

user32.EnumDesktopWindows.argtypes = [wintypes.HDESK, DESKENUMPROC, wintypes.LPARAM]
user32.EnumDesktopWindows(h_desk, DESKENUMPROC(cb), 0)

print(f"Total windows on Default: {len(windows)}")
for h, p, t, c, v in windows:
    if "notepad" in t.lower() or "notepad" in c.lower() or "orbit" in t.lower():
        print(f"  MATCH: HWND={h}, PID={p}, Title={t!r}, Class={c!r}, Vis={v}")

# What is the foreground window?
fg = user32.GetForegroundWindow()
fg_buf = ctypes.create_unicode_buffer(256)
user32.GetWindowTextW(fg, fg_buf, 256)
print(f"Foreground Window HWND: {fg}, Title: {fg_buf.value!r}")
