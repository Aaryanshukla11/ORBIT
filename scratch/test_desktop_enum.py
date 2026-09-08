import ctypes
import ctypes.wintypes
import sys
from orbit.adapters.pointer.safety import attached_to_input_desktop

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.wintypes.BOOL

def enum_all():
    wins = []
    def proc(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                wins.append((hwnd, buf.value, cls_buf.value))
        return True
    cb = WNDENUMPROC(proc)
    user32.EnumWindows(cb, 0)
    return wins

print("Outside attached_to_input_desktop:")
w1 = enum_all()
print(f"Count: {len(w1)}")
for w in w1:
    print("  ", w)

print("\nInside attached_to_input_desktop:")
with attached_to_input_desktop():
    w2 = enum_all()
    print(f"Count: {len(w2)}")
    for w in w2:
        print("  ", w)
