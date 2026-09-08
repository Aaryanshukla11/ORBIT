import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

def enum_handler(hwnd, lparam):
    if user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        if buff.value:
            print(f"{hwnd}: '{buff.value}'")
    return True

user32.EnumWindows(EnumWindowsProc(enum_handler), 0)
