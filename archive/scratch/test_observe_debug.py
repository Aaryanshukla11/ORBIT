import ctypes
from ctypes import wintypes
import subprocess
import time
import sys
sys.path.insert(0, 'src')
from orbit.runtime.perception.windows import Win32WindowObserver

p = subprocess.Popen(["mspaint.exe"])
time.sleep(3)

observer = Win32WindowObserver()
try:
    fg, wins = observer.observe_windows()
    print("observe_windows succeeded, returned wins:", len(wins))
    for w in wins:
        print("  Win:", w.hwnd, repr(w.title), repr(w.process_name))
except Exception as e:
    import traceback
    print("Exception in observe_windows:")
    traceback.print_exc()

subprocess.run("taskkill /f /im mspaint.exe", shell=True, capture_output=True)
