import ctypes
import os
import subprocess
import time
from orbit.adapters.pointer.safety import attached_to_input_desktop

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
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
                    title = buf.value
                    cls_name = cls_buf.value
                    if "antigravity" in title.lower():
                        return True
                    if 'paint' in title.lower() or 'paint' in cls_name.lower():
                        wins.append((hwnd, title, cls_name))
            return True
        cb = WNDENUMPROC(proc)
        user32.EnumWindows(cb, 0)
        return wins

# Close any open paint
os.system("taskkill /F /IM mspaint.exe >nul 2>&1")
time.sleep(1.0)
print("Before launch:", find_paint())

# Test ShellExecuteW with "mspaint"
print("Launching via ShellExecuteW('mspaint')...")
res = shell32.ShellExecuteW(None, "open", "mspaint", None, None, 1) # SW_SHOWNORMAL
print("ShellExecuteW return code (>32 means success):", res)
time.sleep(2.5)
p_after = find_paint()
print("Paint after ShellExecuteW:", p_after)

# If not found, test with explorer.exe shell:AppsFolder...
if not p_after:
    print("Testing explorer shell:AppsFolder...")
    shell32.ShellExecuteW(None, "open", "explorer.exe", "shell:AppsFolder\\Microsoft.Paint_8wekyb3d8bbwe!App", None, 1)
    time.sleep(2.5)
    print("Paint after AppsFolder:", find_paint())
