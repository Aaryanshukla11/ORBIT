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

def find_real_paint():
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
                    title = buf.value
                    cls_name = cls_buf.value
                    if "antigravity" in title.lower():
                        return True
                    if 'paint' in title.lower() or 'paint' in cls_name.lower() or 'msppaint' in cls_name.lower():
                        wins.append((hwnd, title, cls_name))
            return True
        cb = WNDENUMPROC(proc)
        user32.EnumWindows(cb, 0)
        return wins

print("Testing App Execution Alias:")
alias_path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\mspaint.exe")
print("Alias path exists:", os.path.exists(alias_path))

print("Launching via subprocess.Popen([alias_path])...")
try:
    p = subprocess.Popen([alias_path])
    print("Process spawned, pid:", p.pid)
except Exception as e:
    print("Popen error:", e)

time.sleep(3.0)
print("Paint windows:", find_real_paint())
