import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")
from window_tracker import WindowTracker

def check_notepad():
    wt = WindowTracker()
    wins = wt.enumerate_visible_windows()
    matches = [w for w in wins if "notepad" in w.process_name.lower() or "notepad" in w.window_title.lower()]
    return matches

print("Initial Notepad count:", len(check_notepad()))

# Method 1: ShellExecuteW
print("Trying ShellExecuteW 'open' 'notepad.exe'...")
ctypes.windll.shell32.ShellExecuteW(0, "open", "notepad.exe", None, None, 1)
time.sleep(2)
res1 = check_notepad()
print("After ShellExecuteW:", len(res1), [(w.hwnd, w.process_name, w.window_title) for w in res1])

if not res1:
    print("Trying explorer.exe notepad.exe...")
    subprocess.Popen(["explorer.exe", "notepad.exe"])
    time.sleep(2)
    res2 = check_notepad()
    print("After explorer.exe notepad.exe:", len(res2), [(w.hwnd, w.process_name, w.window_title) for w in res2])

if not res1 and not res2:
    print("Trying cmd.exe /c start notepad...")
    subprocess.Popen(["cmd.exe", "/c", "start", "notepad"])
    time.sleep(2)
    res3 = check_notepad()
    print("After cmd.exe /c start notepad:", len(res3), [(w.hwnd, w.process_name, w.window_title) for w in res3])
