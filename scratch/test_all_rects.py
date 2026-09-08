import ctypes
import ctypes.wintypes
from orbit.adapters.pointer.safety import attached_to_input_desktop

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
user32.GetWindowRect.restype = ctypes.wintypes.BOOL

with attached_to_input_desktop():
    wins = []
    def proc(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                rect = ctypes.wintypes.RECT()
                ok = user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
                wins.append((hwnd, buf.value, cls_buf.value, ok, rect.left, rect.top, rect.right, rect.bottom))
        return True
    cb = WNDENUMPROC(proc)
    user32.EnumWindows(cb, 0)
    for w in wins:
        print(w)
