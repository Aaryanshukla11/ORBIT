import ctypes
import os
import subprocess
import sys
import time
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

observer = Win32WindowObserver()

def find_notepad_windows():
    results = []
    fg, windows = observer.observe_windows()
    for w in windows:
        if "notepad" in (w.title or "").lower() or "notepad" in (w.process_name or "").lower():
            results.append((w.hwnd, w.title, w.process_name))
    return results

print("1. Checking existing processes...")
p = subprocess.run(["tasklist"], capture_output=True, text=True)
for line in p.stdout.splitlines():
    if "notepad" in line.lower():
        print("  Process:", line)

print("\n2. Trying ShellExecuteW('notepad.exe')...")
res = ctypes.windll.shell32.ShellExecuteW(None, "open", "notepad.exe", None, None, 1)
print("ShellExecuteW return code:", res)
time.sleep(3)

print("\n3. Checking processes after ShellExecuteW...")
p = subprocess.run(["tasklist"], capture_output=True, text=True)
for line in p.stdout.splitlines():
    if "notepad" in line.lower():
        print("  Process:", line)

print("\n4. Checking windows after ShellExecuteW...")
wins = find_notepad_windows()
print("Notepad windows found:", wins)

print("\n5. Trying subprocess.Popen(['notepad.exe'])...")
proc = subprocess.Popen(["notepad.exe"])
print("Popen PID:", proc.pid)
time.sleep(3)

print("\n6. Checking processes after Popen...")
p = subprocess.run(["tasklist"], capture_output=True, text=True)
for line in p.stdout.splitlines():
    if "notepad" in line.lower():
        print("  Process:", line)

print("\n7. Checking windows after Popen...")
wins = find_notepad_windows()
print("Notepad windows found:", wins)

subprocess.run("taskkill /f /im notepad.exe", shell=True, capture_output=True)
