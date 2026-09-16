import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

methods = [
    ("cmd /c start notepad.exe", "cmd /c start notepad.exe"),
    ("notepad.exe", ["notepad.exe"]),
    ("powershell Start-Process notepad", ["powershell", "-Command", "Start-Process notepad"]),
    ("explorer.exe shell:appsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App", "explorer.exe shell:appsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"),
]

for name, cmd in methods:
    print(f"\nTesting: {name}")
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
    time.sleep(1)
    
    if isinstance(cmd, str):
        subprocess.Popen(cmd, shell=True)
    else:
        subprocess.Popen(cmd)
    time.sleep(3)
    
    wins = []
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        t = buf.value.strip()
        if t:
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            wins.append((hwnd, t, cls_buf.value))
        return True
    
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    print(f"  Windows on current desktop ({len(wins)}):")
    for h, t, c in wins:
        if "notepad" in t.lower() or "notepad" in c.lower() or "untitled" in t.lower():
            print(f"    MATCH: HWND={h}, Title={t!r}, Class={c}")
        else:
            print(f"    OTHER: HWND={h}, Title={t!r}, Class={c}")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
