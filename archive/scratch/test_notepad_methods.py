import ctypes
import os
import subprocess
import time
import sys
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

observer = Win32WindowObserver()

methods = [
    ("explorer notepad.exe", lambda: subprocess.Popen(["explorer.exe", "notepad.exe"])),
    ("powershell Start-Process notepad", lambda: subprocess.Popen(["powershell", "-Command", "Start-Process notepad"])),
    ("cmd start notepad", lambda: subprocess.Popen("start notepad", shell=True)),
    ("system32 notepad.exe", lambda: subprocess.Popen([r"C:\Windows\System32\notepad.exe"])),
]

for name, fn in methods:
    print(f"\n--- Testing Method: {name} ---")
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
    time.sleep(1)
    
    fn()
    time.sleep(3)
    
    fg, windows = observer.observe_windows()
    notepad_wins = [w for w in windows if "notepad" in (w.title or "").lower() or "notepad" in (w.process_name or "").lower()]
    print(f"Foreground: {fg.title if fg else None}")
    print(f"Found {len(notepad_wins)} visible Notepad windows:")
    for w in notepad_wins:
        print(f"  HWND={w.hwnd}, Title={w.title!r}, Proc={w.process_name!r}")
    
    subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
