import ctypes
import os
import subprocess
import time
import sys

sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

observer = Win32WindowObserver()

print("1. Cleaning up existing notepad...")
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
time.sleep(1)

print("2. Launching Notepad with lpDesktop = 'WinSta0\\\\Default'...")
si = subprocess.STARTUPINFO()
si.lpDesktop = r"WinSta0\Default"

proc = subprocess.Popen(
    ["notepad.exe"],
    startupinfo=si,
)
print("Started Notepad with PID:", proc.pid)
time.sleep(3)

print("3. Observing windows via Win32WindowObserver...")
fg, windows = observer.observe_windows()
print(f"Foreground window: {fg.title if fg else None}")

notepad_wins = [w for w in windows if "notepad" in (w.title or "").lower() or "notepad" in (w.process_name or "").lower()]
print(f"Total Notepad windows found: {len(notepad_wins)}")
for w in notepad_wins:
    print(f"  MATCH: HWND={w.hwnd}, Title={w.title!r}, Proc={w.process_name!r}")

# Cleanup
subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
