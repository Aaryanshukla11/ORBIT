import asyncio
import os
import sys
import ctypes
import pyautogui
pyautogui.FAILSAFE = False

sys.path.insert(0, os.path.abspath("src"))

from orbit.runtime.perception.windows import Win32WindowObserver
from orbit.runtime.capabilities.application_launcher import ApplicationLauncher

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

    return True

async def main():
    target_path = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "test.png")
    if os.path.exists(target_path):
        os.remove(target_path)

    # Launch Paint
    launcher = ApplicationLauncher()
    launcher.launch("mspaint")
    await asyncio.sleep(2.0)

    observer = Win32WindowObserver()
    fg, visible = observer.observe_windows()

    paint_hwnd = None
    for w in visible:
        t = (w.title or "").lower()
        c = (w.window_class or "").lower()
        p = (w.process_name or "").lower()
        if "antigravity" in t or "code" in t:
            continue
        if "mspaint" in p or "paint" in t or "mspaintapp" in c:
            paint_hwnd = w.hwnd
            break

    print("Found Paint HWND:", paint_hwnd)
    if paint_hwnd:
        force_focus(paint_hwnd)
        await asyncio.sleep(0.5)

    # Draw something first
    pyautogui.moveTo(500, 500)
    pyautogui.dragTo(600, 600, duration=0.5, button='left')
    await asyncio.sleep(0.5)

    # Trigger Save As via F12 / Ctrl+Shift+S
    print("Sending F12 (Save As)...")
    pyautogui.press("f12")
    await asyncio.sleep(1.2)

    fg_save, _ = observer.observe_windows()
    print("FG after F12:", fg_save.title if fg_save else None, "Class:", fg_save.window_class if fg_save else None)

    print(f"Typing: {target_path}")
    pyautogui.write(target_path, interval=0.01)
    await asyncio.sleep(0.5)

    print("Sending Enter...")
    pyautogui.press("enter")
    await asyncio.sleep(1.2)

    # Accept potential replace dialog
    pyautogui.hotkey("alt", "y")
    await asyncio.sleep(1.0)

    print("File exists on disk:", os.path.exists(target_path), f"Size: {os.path.getsize(target_path) if os.path.exists(target_path) else 0}")

if __name__ == "__main__":
    asyncio.run(main())
