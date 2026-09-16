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
