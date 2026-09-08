import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
user32.GetWindowRect.restype = ctypes.wintypes.BOOL

rect = ctypes.wintypes.RECT()
hwnd = 594078
ctypes.set_last_error(0)
ok = user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
err = ctypes.get_last_error()
print(f"ok={ok}, err={err}, left={rect.left}, top={rect.top}, right={rect.right}, bottom={rect.bottom}")
