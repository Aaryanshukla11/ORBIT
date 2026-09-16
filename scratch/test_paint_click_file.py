import asyncio
import os
import sys
import ctypes
import pyautogui

pyautogui.FAILSAFE = False

def main():
    user32 = ctypes.windll.user32
    # Find Paint HWND
    def enum_cb(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            cls_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buff, 256)
            if "MSPaintApp" in cls_buff.value or ("Paint" in buff.value and "antigravity" not in buff.value.lower() and not buff.value.endswith(".py")):
                lparam.append((hwnd, buff.value, cls_buff.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.POINTER(ctypes.c_void_p))
    found = []
    cb = WNDENUMPROC(lambda h, l: enum_cb(h, found))
    user32.EnumWindows(cb, 0)
    print("Found Paint windows:", found)
    if found:
        hwnd = found[0][0]
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        print(f"Paint Rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom})")

        # Bring to foreground
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time_sleep = 0.5

        # Test clicking File menu (around top-left inside window)
        file_x = rect.left + 50
        file_y = rect.top + 70
        print(f"Clicking File menu button at ({file_x}, {file_y})...")
        pyautogui.click(file_x, file_y)

if __name__ == "__main__":
    main()
