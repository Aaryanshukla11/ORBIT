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
hr = ole32.CoCreateInstance(
    ctypes.byref(CLSID_CUIAutomation),
    None,
    1,
    ctypes.byref(IID_IID := IID_IUIAutomation),
    ctypes.byref(pUIA)
)
print("CoCreateInstance hr:", hr)

wt = WindowTracker()
calc_wins = [w for w in wt.enumerate_visible_windows() if 'calc' in w.process_name.lower() or 'calc' in (w.window_title or '').lower()]
if not calc_wins:
    os.system("start calculator:")
    time.sleep(2)
    calc_wins = [w for w in wt.enumerate_visible_windows() if 'calc' in w.process_name.lower() or 'calc' in (w.window_title or '').lower()]

print("Found calc windows:", [(w.hwnd, w.window_title, w.process_name) for w in calc_wins])

if calc_wins:
    hwnd = calc_wins[0].hwnd
    vtable_uia = ctypes.cast(pUIA.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    
    # ElementFromHandle (vtable index 6)
    ELEMENT_FROM_HANDLE_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p))
    ElementFromHandle = ELEMENT_FROM_HANDLE_TYPE(vtable_uia[6])
    
    pRoot = ctypes.c_void_p()
    hr_elem = ElementFromHandle(pUIA.value, hwnd, ctypes.byref(pRoot))
    print(f"ElementFromHandle({hwnd}) hr: {hr_elem}, pRoot: {pRoot.value}")
    
    # CreateTrueCondition (vtable index 21)
    CREATE_TRUE_COND_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    CreateTrueCondition = CREATE_TRUE_COND_TYPE(vtable_uia[21])
    pCond = ctypes.c_void_p()
    CreateTrueCondition(pUIA.value, ctypes.byref(pCond))
    
    # FindAll (IUIAutomationElement vtable index 6)
    # TreeScope_Descendants = 4, TreeScope_Subtree = 5, TreeScope_Children = 2
    if pRoot.value:
        vtable_e = ctypes.cast(pRoot.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        FIND_ALL_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        FindAll = FIND_ALL_TYPE(vtable_e[6])
        
        pElemArray = ctypes.c_void_p()
        hr_find = FindAll(pRoot.value, 4, pCond.value, ctypes.byref(pElemArray))
        print(f"FindAll(TreeScope_Descendants) hr: {hr_find}, pElemArray: {pElemArray.value}")
        
        if pElemArray.value:
            vtable_arr = ctypes.cast(pElemArray.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            # get_Length (vtable index 3)
            GET_LEN_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
            get_Length = GET_LEN_TYPE(vtable_arr[3])
            # GetElement (vtable index 4)
            GET_ELEM_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
            GetElement = GET_ELEM_TYPE(vtable_arr[4])
            
            arr_len = ctypes.c_int(0)
            get_Length(pElemArray.value, ctypes.byref(arr_len))
            print(f"Total elements found via FindAll: {arr_len.value}")
            
            for i in range(min(arr_len.value, 30)):
                pChild = ctypes.c_void_p()
                GetElement(pElemArray.value, i, ctypes.byref(pChild))
                if pChild.value:
                    vtable_c = ctypes.cast(pChild.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                    bstr_name = wintypes.LPWSTR()
                    ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_c[23])(pChild.value, ctypes.byref(bstr_name))
                    bstr_aid = wintypes.LPWSTR()
                    ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_c[29])(pChild.value, ctypes.byref(bstr_aid))
                    print(f"  [{i}] Name: '{bstr_name.value}', Aid: '{bstr_aid.value}'")
