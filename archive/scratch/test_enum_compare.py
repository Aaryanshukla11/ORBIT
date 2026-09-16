import ctypes
from ctypes import wintypes
import sys
import os

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Method 1: EnumWindows
wins_enum = []
def cb1(h, l):
    if user32.IsWindow(h) and user32.IsWindowVisible(h):
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(h, buf, 512)
        if buf.value:
            wins_enum.append((h, buf.value))
    return True

user32.EnumWindows(WNDENUMPROC(cb1), 0)
print(f"EnumWindows found {len(wins_enum)} windows with titles:")
for h, t in wins_enum:
    print(f"  {h}: {t}")

# Method 2: OpenInputDesktop + EnumDesktopWindows
wins_desk = []
def cb2(h, l):
    if user32.IsWindow(h) and user32.IsWindowVisible(h):
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(h, buf, 512)
        if buf.value:
            wins_desk.append((h, buf.value))
    return True

hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
print(f"\nOpenInputDesktop handle: {hdesk}")
if hdesk:
    user32.EnumDesktopWindows(hdesk, WNDENUMPROC(cb2), 0)
    user32.CloseDesktop(hdesk)

print(f"EnumDesktopWindows found {len(wins_desk)} windows with titles:")
for h, t in wins_desk:
    print(f"  {h}: {t}")
