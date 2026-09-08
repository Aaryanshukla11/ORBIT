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
vtable_uia = ctypes.cast(pUIA.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
# Test GetRootElement (index 5)
GetRootElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_uia[5])
pDesktopRoot = ctypes.c_void_p()
hr_dr = GetRootElement(pUIA.value, ctypes.byref(pDesktopRoot))
print(f"GetRootElement hr=0x{hr_dr & 0xFFFFFFFF:08X}, pDesktopRoot={pDesktopRoot.value}")

if pDesktopRoot.value:
    get_ControlViewWalker = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_uia[14])
    pWalker = ctypes.c_void_p()
    hr_w = get_ControlViewWalker(pUIA.value, ctypes.byref(pWalker))
    vtable_w = ctypes.cast(pWalker.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    GetFirstChildElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_w[3])
    GetNextSiblingElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_w[5])

    pChild = ctypes.c_void_p()
    GetFirstChildElement(pWalker.value, pDesktopRoot.value, ctypes.byref(pChild))
    curr = pChild.value
    count = 0
    while curr:
        vt = ctypes.cast(curr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        nm = wintypes.LPWSTR()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vt[23])(curr, ctypes.byref(nm))
        aid = wintypes.LPWSTR()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vt[29])(curr, ctypes.byref(aid))
        rect = wintypes.RECT()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))(vt[43])(curr, ctypes.byref(rect))
        print(f"Desktop Top-Level [{count}]: Name='{nm.value}', AID='{aid.value}', Bounds=({rect.left},{rect.top},{rect.right},{rect.bottom})")
        count += 1
        pNext = ctypes.c_void_p()
        GetNextSiblingElement(pWalker.value, curr, ctypes.byref(pNext))
        curr = pNext.value


