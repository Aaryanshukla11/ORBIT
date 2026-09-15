import subprocess
import time
import sys
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

observer = Win32WindowObserver()

for desk_val in ["Default", r"WinSta0\Default"]:
    print(f"\nTesting mspaint with lpDesktop = {desk_val!r}...")
    si = subprocess.STARTUPINFO()
    si.lpDesktop = desk_val
    p = subprocess.Popen(["mspaint.exe"], startupinfo=si)
    time.sleep(3)
    
    fg, wins = observer.observe_windows()
    paint_wins = [w for w in wins if "paint" in (w.title or "").lower()]
    print(f"Paint windows found on Default: {len(paint_wins)}")
    for pw in paint_wins:
        print(f"  FOUND: HWND={pw.hwnd}, Title={pw.title!r}")
    
    subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
