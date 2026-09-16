import os
import sys
import ctypes
from ctypes import wintypes
import time

sys.path.insert(0, os.path.abspath("src"))

ctypes.windll.ole32.CoInitializeEx(None, 0)

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

CLSID_CUIAutomation = GUID(
    0xFF48DBA4,
    0x0DB2,
    0x4CE8,
    (ctypes.c_ubyte * 8)(0x88, 0x33, 0x4D, 0x34, 0xB3, 0xB4, 0x20, 0xCE),
)
IID_IUIAutomation = GUID(
    0x30CBE57D,
    0xD9D0,
    0x452A,
    (ctypes.c_ubyte * 8)(0xAB, 0x13, 0x7A, 0xC5, 0xAC, 0x48, 0x25, 0xEE),
)

pUIA = ctypes.c_void_p()
hr = ctypes.windll.ole32.CoCreateInstance(
    ctypes.byref(CLSID_CUIAutomation),
    None,
    1,
    ctypes.byref(IID_IUIAutomation),
    ctypes.byref(pUIA)
)
print(f"CoCreateInstance hr=0x{hr & 0xFFFFFFFF:08X}, pUIA={pUIA.value}")

vtable_uia = ctypes.cast(pUIA.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

# Find Calculator or any top window using native Win32WindowObserver
from orbit.runtime.perception.windows import Win32WindowObserver
wt = Win32WindowObserver()
_, wins = wt.observe_windows()
print(f"Win32WindowObserver found {len(wins)} windows:")
found_h = 0
for w in wins:
    print(f"  HWND={w.hwnd}, title='{w.title}', proc='{w.process_name}'")
    if "calc" in (w.title or "").lower() or "calc" in (w.process_name or "").lower():
        found_h = w.hwnd

if not found_h:
    import subprocess
    subprocess.Popen(["calc.exe"])
    time.sleep(2.0)
    _, wins = wt.observe_windows()
    for w in wins:
        if "calc" in (w.title or "").lower() or "calc" in (w.process_name or "").lower():
            found_h = w.hwnd
            break

if found_h:
    # ElementFromHandle (vtable index 6)
    ELEMENT_FROM_HANDLE_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p))
    ElementFromHandle = ELEMENT_FROM_HANDLE_TYPE(vtable_uia[6])
    pRoot = ctypes.c_void_p()
    hr_elem = ElementFromHandle(pUIA.value, found_h, ctypes.byref(pRoot))
    print(f"ElementFromHandle hr=0x{hr_elem & 0xFFFFFFFF:08X}, pRoot={pRoot.value}")

    if pRoot.value:
        vtable_e = ctypes.cast(pRoot.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        for idx in [19, 20, 21, 22, 23, 24, 27, 28, 29, 32, 35, 37, 42, 43]:
            try:
                bstr = wintypes.LPWSTR()
                hr_call = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_e[idx])(pRoot.value, ctypes.byref(bstr))
                print(f"  vtable[{idx}] as BSTR -> hr=0x{hr_call & 0xFFFFFFFF:08X}, val={repr(bstr.value)}")
            except Exception as ex:
                print(f"  vtable[{idx}] -> ex: {ex}")
