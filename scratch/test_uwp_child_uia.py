import ctypes
from ctypes import wintypes
import time
import sys
import os

sys.path.extend(['src', 'prototypes/prototype_d_observation'])
from window_tracker import WindowTracker

user32 = ctypes.windll.user32
ole32 = ctypes.windll.ole32

ole32.CoInitialize(None)

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

CLSID_CUIAutomation = GUID()
IID_IUIAutomation = GUID()
ole32.IIDFromString("{ff48dba4-60ef-4201-aa87-54103eef594e}", ctypes.byref(CLSID_CUIAutomation))
ole32.IIDFromString("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}", ctypes.byref(IID_IUIAutomation))

pUIA = ctypes.c_void_p()
ole32.CoCreateInstance(ctypes.byref(CLSID_CUIAutomation), None, 1, ctypes.byref(IID_IUIAutomation), ctypes.byref(pUIA))
vtable_uia = ctypes.cast(pUIA.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
ElementFromHandle = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p))(vtable_uia[6])
GetRootElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_uia[4])

wt = WindowTracker()
calc_wins = [w for w in wt.enumerate_visible_windows() if 'calc' in w.process_name.lower() or 'calc' in (w.window_title or '').lower()]
if not calc_wins:
    os.system("start calculator:")
    time.sleep(2)
    calc_wins = [w for w in wt.enumerate_visible_windows() if 'calc' in w.process_name.lower() or 'calc' in (w.window_title or '').lower()]

print("Found calc windows:", [(w.hwnd, w.window_title, w.process_name) for w in calc_wins])

if calc_wins:
    parent_hwnd = calc_wins[0].hwnd
    # Enumerate child windows
    child_hwnds = []
    def enum_child(h, l):
        child_hwnds.append(h)
        return True
    user32.EnumChildWindows(parent_hwnd, ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_child), 0)
    print(f"Child HWNDs of {parent_hwnd}: {child_hwnds}")
    
    for h in [parent_hwnd] + child_hwnds:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        cname = buf.value
        user32.GetWindowTextW(h, buf, 256)
        wtitle = buf.value
        pRoot = ctypes.c_void_p()
        hr = ElementFromHandle(pUIA.value, h, ctypes.byref(pRoot))
        print(f"  HWND {h} (class: '{cname}', title: '{wtitle}'): hr=0x{hr & 0xFFFFFFFF:08X}, pRoot={pRoot.value}")
        
    # Also test finding Calculator from UIA Root element
    pDesktopRoot = ctypes.c_void_p()
    GetRootElement(pUIA.value, ctypes.byref(pDesktopRoot))
    print("Desktop Root element:", pDesktopRoot.value)
    if pDesktopRoot.value:
        vtable_root = ctypes.cast(pDesktopRoot.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        # CreatePropertyCondition (vtable index 23)
        # UIA_NamePropertyId = 30005
        class VARIANT(ctypes.Structure):
            _fields_ = [("vt", wintypes.WORD), ("wReserved1", wintypes.WORD), ("wReserved2", wintypes.WORD), ("wReserved3", wintypes.WORD), ("bstrVal", wintypes.LPWSTR), ("dummy", ctypes.c_ulonglong)]
        
        var = VARIANT()
        var.vt = 8 # VT_BSTR
        var.bstrVal = "Calculator"
        
        CreatePropertyCondition = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, wintypes.LONG, VARIANT, ctypes.POINTER(ctypes.c_void_p))(vtable_uia[23])
        pCondName = ctypes.c_void_p()
        CreatePropertyCondition(pUIA.value, 30005, var, ctypes.byref(pCondName))
        
        FindFirst = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_root[5])
        pFoundCalc = ctypes.c_void_p()
        hr_ff = FindFirst(pDesktopRoot.value, 4, pCondName.value, ctypes.byref(pFoundCalc))
        print(f"FindFirst('Calculator' from desktop root): hr=0x{hr_ff & 0xFFFFFFFF:08X}, pFoundCalc={pFoundCalc.value}")
        
        if pFoundCalc.value:
            # FindAll descendants of Calculator
            CreateTrueCondition = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_uia[21])
            pTrueCond = ctypes.c_void_p()
            CreateTrueCondition(pUIA.value, ctypes.byref(pTrueCond))
            
            vtable_fc = ctypes.cast(pFoundCalc.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            FindAll = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_fc[6])
            pArray = ctypes.c_void_p()
            FindAll(pFoundCalc.value, 4, pTrueCond.value, ctypes.byref(pArray))
            if pArray.value:
                vtable_arr = ctypes.cast(pArray.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                arr_len = ctypes.c_int(0)
                ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))(vtable_arr[3])(pArray.value, ctypes.byref(arr_len))
                print(f"Total elements inside Calculator from Desktop Root: {arr_len.value}")
                GetElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(vtable_arr[4])
                for i in range(min(arr_len.value, 30)):
                    pC = ctypes.c_void_p()
                    GetElement(pArray.value, i, ctypes.byref(pC))
                    if pC.value:
                        vt_c = ctypes.cast(pC.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                        b_name = wintypes.LPWSTR()
                        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vt_c[23])(pC.value, ctypes.byref(b_name))
                        b_aid = wintypes.LPWSTR()
                        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vt_c[29])(pC.value, ctypes.byref(b_aid))
                        print(f"  [{i}] '{b_name.value}', aid='{b_aid.value}'")
