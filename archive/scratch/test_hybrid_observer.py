import ctypes
from ctypes import wintypes
import subprocess
import time
import sys

# Launch notepad
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

print("1. Launching notepad...")
subprocess.run("cmd /c start notepad.exe", shell=True)
time.sleep(2)

# Now test an observer that queries the current desktop
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

# Monkey patch _ensure_desktop_attached to NOT forcibly switch thread desktop
Win32WindowObserver._ensure_desktop_attached = lambda self: None

obs = Win32WindowObserver()
fg, wins = obs.observe_windows()

print(f"\n2. Results with current desktop:")
print(f"  Foreground: {fg.title if fg else None} (HWND: {fg.hwnd if fg else None})")
print(f"  Total windows: {len(wins)}")
for w in wins:
    print(f"  Win: HWND={w.hwnd:<8} | Title={w.title!r:<30} | Proc={w.process_name}")

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
