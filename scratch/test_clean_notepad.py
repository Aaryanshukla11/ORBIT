import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import time

user32 = ctypes.windll.user32

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

local_state = r"C:\Users\Aaryan shukla\AppData\Local\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState"
backup_dir = r"C:\Users\Aaryan shukla\AppData\Local\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState_backup"

tab_dir = os.path.join(local_state, "TabState")
win_dir = os.path.join(local_state, "WindowState")

print(f"Cleaning {len(os.listdir(tab_dir))} tab files and {len(os.listdir(win_dir))} win files...")

# Move to backup
if not os.path.exists(backup_dir):
    os.makedirs(backup_dir, exist_ok=True)

for root_dir in [tab_dir, win_dir]:
    for f in os.listdir(root_dir):
        fp = os.path.join(root_dir, f)
        try:
            os.remove(fp)
        except Exception:
            pass

print(f"Remaining in TabState: {len(os.listdir(tab_dir))}, WindowState: {len(os.listdir(win_dir))}")

# Now launch notepad
print("\nLaunching Notepad now...")
p = subprocess.Popen(["cmd", "/c", "start", "notepad.exe"])
time.sleep(3)

# Enumerate windows on current desktop
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
found = []
def enum_cb(hwnd, _):
    if not user32.IsWindowVisible(hwnd): return True
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    t = buf.value.strip()
    if t and ("notepad" in t.lower() or "untitled" in t.lower()):
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        found.append((hwnd, t, cls_buf.value))
    return True

user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
print(f"Notepad windows found: {len(found)}")
for h, t, c in found:
    print(f"  FOUND: HWND={h}, Title={t!r}, Class={c}")

# Check with Win32WindowObserver
import sys
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver
observer = Win32WindowObserver()
fg, wins = observer.observe_windows()
print(f"\nWin32WindowObserver foreground: {fg.title if fg else None}")
obs_np = [w for w in wins if "notepad" in (w.title or "").lower() or "notepad" in (w.process_name or "").lower()]
print(f"Win32WindowObserver notepad windows: {len(obs_np)}")
for w in obs_np:
    print(f"  OBSERVER: HWND={w.hwnd}, Title={w.title!r}, Proc={w.process_name!r}")
