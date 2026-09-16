import asyncio
import os
import sys
import ctypes
import pyautogui

sys.path.insert(0, os.path.abspath("src"))

from orbit.runtime.perception.windows import Win32WindowObserver
from orbit.runtime.capabilities.application_launcher import ApplicationLauncher

pyautogui.FAILSAFE = False

async def main():
    target_path = os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "test.png")
    if os.path.exists(target_path):
        os.remove(target_path)

    # Launch Paint
    launcher = ApplicationLauncher()
    launcher.launch("mspaint")
    await asyncio.sleep(2.5)

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
        # Click on center of canvas to focus Paint canvas
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(paint_hwnd, ctypes.byref(rect))
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        print(f"Clicking center of canvas at ({cx}, {cy})...")
        pyautogui.click(cx, cy)
        await asyncio.sleep(0.5)

        # Draw a stroke so canvas is dirty
        pyautogui.dragTo(cx + 100, cy + 100, duration=0.3, button='left')
        await asyncio.sleep(0.5)

        # Send Ctrl+S via SendInput
        print("Sending Ctrl+S...")
        pyautogui.hotkey("ctrl", "s")
        await asyncio.sleep(1.5)

        fg_after, visible_after = observer.observe_windows()
        print("FG after Ctrl+S:", fg_after.title if fg_after else None, "Class:", fg_after.window_class if fg_after else None)
        for w in visible_after:
            if "save" in (w.title or "").lower():
                print("  Found Save window:", w.title, w.hwnd)

        # Type target path and enter
        print(f"Typing path: {target_path}")
        pyautogui.write(target_path, interval=0.01)
        await asyncio.sleep(0.5)

        print("Pressing Enter...")
        pyautogui.press("enter")
        await asyncio.sleep(1.5)

        # Confirm overwrite if needed
        pyautogui.hotkey("alt", "y")
        await asyncio.sleep(1.0)

        print("File exists on disk:", os.path.exists(target_path), f"Size: {os.path.getsize(target_path) if os.path.exists(target_path) else 0}")

if __name__ == "__main__":
    asyncio.run(main())
