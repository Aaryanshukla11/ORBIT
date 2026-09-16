import subprocess
import time
import sys
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

observer = Win32WindowObserver()

print("Testing mspaint.exe...")
subprocess.Popen(["mspaint.exe"])
time.sleep(3)

fg, windows = observer.observe_windows()
paint_wins = [w for w in windows if "paint" in (w.title or "").lower() or "mspaint" in (w.process_name or "").lower()]
print(f"Paint visible windows found: {len(paint_wins)}")
for w in paint_wins:
    print(f"  HWND={w.hwnd}, Title={w.title!r}, Proc={w.process_name!r}")

subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
