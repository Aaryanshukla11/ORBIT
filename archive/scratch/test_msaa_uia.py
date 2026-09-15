import ctypes
from ctypes import wintypes
import time

user32 = ctypes.windll.user32
oleacc = ctypes.windll.oleacc
ole32 = ctypes.windll.ole32

ole32.CoInitialize(None)

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

IID_IAccessible = GUID()
ole32.IIDFromString("{618736e0-3c3d-11cf-810c-00aa00389b71}", ctypes.byref(IID_IAccessible))
OBJID_CLIENT = 0xFFFFFFFC

hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
wins = []
def cb(h, l):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(h, buf, 512)
    if 'calc' in buf.value.lower():
        wins.append(h)
    return True

user32.EnumDesktopWindows(hdesk, ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
user32.CloseDesktop(hdesk)

print("Found Calculator HWNDs:", wins)

for h in wins:
    pAcc = ctypes.c_void_p()
    hr = oleacc.AccessibleObjectFromWindow(h, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pAcc))
    print(f"AccessibleObjectFromWindow({h}) hr: 0x{hr & 0xFFFFFFFF:08X}, pAcc: {pAcc.value}")
    if hr == 0 and pAcc.value:
        vtable_acc = ctypes.cast(pAcc.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        # get_accChildCount (vtable index 8)
        GET_CC_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_long))
        get_accChildCount = GET_CC_TYPE(vtable_acc[8])
        cc = ctypes.c_long(0)
        get_accChildCount(pAcc.value, ctypes.byref(cc))
        print(f"  Child count: {cc.value}")
