import ctypes
import ctypes.wintypes as w
import subprocess
import sys
import time

title = 'TEST_TK_123'
code = f'import tkinter as tk\nroot = tk.Tk()\nroot.title("{title}")\nroot.mainloop()'
proc = subprocess.Popen([sys.executable, '-c', code])
time.sleep(1.0)

u32 = ctypes.windll.user32
h = u32.FindWindowW(None, title)
print(f"HWND: {h}")

all_enum = []
def cb(hwnd, lparam):
    all_enum.append(hwnd)
    return True

proc_cb = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb)
u32.EnumWindows(proc_cb, 0)
print(f"EnumWindows saw target hwnd? {h in all_enum}, total: {len(all_enum)}")

h_desk = u32.OpenInputDesktop(0, False, 0x1FF)
all_desk = []
def cb2(hwnd, lparam):
    all_desk.append(hwnd)
    return True

proc_cb2 = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb2)
u32.EnumDesktopWindows(h_desk, proc_cb2, 0)
print(f"EnumDesktopWindows saw target hwnd? {h in all_desk}, total: {len(all_desk)}")

proc.terminate()
