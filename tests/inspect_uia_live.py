import os
import sys
import ctypes
from ctypes import wintypes
import time

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("prototypes/prototype_d_observation"))

ctypes.windll.ole32.CoInitializeEx(None, 0)

from uia_provider import UIAutomationProvider, GUID, CLSID_CUIAutomation, IID_IUIAutomation

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

# Find Calculator or any top window
from window_tracker import WindowTracker
wt = WindowTracker()
wins = list(wt.enumerate_visible_windows())
print(f"WindowTracker found {len(wins)} windows:")
found_h = 0
for w in wins:
    print(f"  HWND={w.hwnd}, title='{w.window_title}', proc='{w.process_name}'")
    if "calc" in (w.window_title or "").lower() or "calc" in (w.process_name or "").lower():
        found_h = w.hwnd

if not found_h:
    import subprocess
    subprocess.Popen(["calc.exe"])
    time.sleep(2.0)
    for w in wt.enumerate_visible_windows():
        if "calc" in (w.window_title or "").lower() or "calc" in (w.process_name or "").lower():
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
        # Try index 22 vs index 23 for get_CurrentName
        for idx in [19, 20, 21, 22, 23, 24, 27, 28, 29, 32, 35, 37, 42, 43]:
            try:
                # Test as BSTR
                bstr = wintypes.LPWSTR()
                hr_call = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_e[idx])(pRoot.value, ctypes.byref(bstr))
                print(f"  vtable[{idx}] as BSTR -> hr=0x{hr_call & 0xFFFFFFFF:08X}, val={repr(bstr.value)}")
            except Exception as ex:
                print(f"  vtable[{idx}] -> ex: {ex}")
