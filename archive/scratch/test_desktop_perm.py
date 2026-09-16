import ctypes
from ctypes import wintypes
import sys

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

h_input = user32.OpenInputDesktop(0, False, 0x01FF)
err1 = kernel32.GetLastError()
print(f"OpenInputDesktop: handle={h_input}, err={err1}")

h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)
err2 = kernel32.GetLastError()
print(f"OpenDesktopW('Default'): handle={h_default}, err={err2}")

if h_default:
    res = user32.SetThreadDesktop(h_default)
    err3 = kernel32.GetLastError()
    print(f"SetThreadDesktop: res={res}, err={err3}")

cur_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
name_buf = ctypes.create_unicode_buffer(256)
needed = wintypes.DWORD()
user32.GetUserObjectInformationW(cur_desk, 2, name_buf, 256, ctypes.byref(needed))
print(f"Current Thread Desktop: handle={cur_desk}, Name={name_buf.value}")
