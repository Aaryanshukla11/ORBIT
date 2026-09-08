import ctypes
from ctypes import wintypes
import subprocess
import time
import sys

sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

observer = Win32WindowObserver()

# Pre-cleanup
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

print("1. Launching Notepad via cmd /c start notepad...")
subprocess.run("cmd /c start notepad.exe", shell=True)
time.sleep(3)

print("2. Observing windows via Win32WindowObserver...")
fg, wins = observer.observe_windows()
print(f"Foreground: {fg.title if fg else None}")

notepad_wins = [w for w in wins if "notepad" in (w.title or "").lower() or "notepad" in (w.process_name or "").lower()]
print(f"Found {len(notepad_wins)} Notepad windows in Win32WindowObserver:")
for w in notepad_wins:
    print(f"  MATCH: HWND={w.hwnd}, Title={w.title!r}, Proc={w.process_name!r}")

# Cleanup
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
