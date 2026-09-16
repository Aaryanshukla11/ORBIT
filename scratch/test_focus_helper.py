import os
import sys
import time
import ctypes
from ctypes import wintypes

sys.path.insert(0, os.path.abspath("src"))

from orbit.runtime.perception.windows import Win32WindowObserver

def force_focus(hwnd: int) -> bool:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    cur_thread = kernel32.GetCurrentThreadId()
    fg_hwnd = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    if fg_thread != cur_thread and fg_thread != 0:
        user32.AttachThreadInput(cur_thread, fg_thread, True)
    if target_thread != cur_thread and target_thread != 0:
        user32.AttachThreadInput(cur_thread, target_thread, True)

    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)

    if fg_thread != cur_thread and fg_thread != 0:
        user32.AttachThreadInput(cur_thread, fg_thread, False)
    if target_thread != cur_thread and target_thread != 0:
        user32.AttachThreadInput(cur_thread, target_thread, False)

    time.sleep(0.3)
    new_fg = user32.GetForegroundWindow()
    return new_fg == hwnd

def main():
    observer = Win32WindowObserver()
    fg, visible = observer.observe_windows()
    paint_wins = [w for w in visible if "paint" in (w.title or "").lower() or "paint" in (w.window_class or "").lower() or "paint" in (w.process_name or "").lower()]
    print("Paint windows found:", [(w.hwnd, w.title) for w in paint_wins])
    if paint_wins:
        hwnd = paint_wins[0].hwnd
        print(f"Attempting to force focus to HWND {hwnd}...")
        success = force_focus(hwnd)
        print("Focus success:", success)
        fg_after, _ = observer.observe_windows()
        print("FG after focus:", fg_after.title if fg_after else None)

if __name__ == "__main__":
    main()
