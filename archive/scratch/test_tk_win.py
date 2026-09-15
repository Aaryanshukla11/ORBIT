import subprocess
import sys
import time
import ctypes
from ctypes import wintypes

title = "TEST_TK_WIN_1234"
code = f"""
import tkinter as tk
root = tk.Tk()
root.title("{title}")
root.geometry("350x250+200+200")
root.update_idletasks()
root.update()
root.mainloop()
"""

proc = subprocess.Popen([sys.executable, "-c", code])
time.sleep(1.0)

u32 = ctypes.windll.user32
h1 = u32.FindWindowW(None, title)
print(f"FindWindowW result: {h1}")
if h1:
    print(f"IsWindow: {u32.IsWindow(h1)}, IsVisible: {u32.IsWindowVisible(h1)}")
    r = wintypes.RECT()
    u32.GetWindowRect(h1, ctypes.byref(r))
    print(f"Rect: {r.left}, {r.top}, {r.right}, {r.bottom}")

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")
from window_tracker import WindowTracker
wt = WindowTracker()
wins = wt.enumerate_visible_windows()
tk_wins = [w for w in wins if title in w.window_title]
print(f"WindowTracker found tkinter window: {len(tk_wins)}")
if tk_wins:
    print(f"Window: {tk_wins[0]}")

proc.terminate()
