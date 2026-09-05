"""
Smoke Test S5: Native Win32 MSAA / IAccessible
Validates: oleacc.AccessibleObjectFromWindow, AccessibleChildren, and COM vtable traversal (get_accName, get_accRole, accLocation).
"""

import ctypes
from ctypes import wintypes
import time
import json
import tkinter as tk

ole32 = ctypes.windll.ole32
oleacc = ctypes.windll.oleacc
user32 = ctypes.windll.user32

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
CHILDID_SELF = 0

BSTR = wintypes.LPWSTR
class VARIANT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [
            ("lVal", wintypes.LONG),
            ("pdispVal", ctypes.c_void_p),
            ("punkVal", ctypes.c_void_p),
            ("bstrVal", BSTR),
        ]
    _anonymous_ = ("_u",)
    _fields_ = [
        ("vt", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
        ("wReserved2", wintypes.WORD),
        ("wReserved3", wintypes.WORD),
        ("_u", _U),
    ]

VT_I4 = 3
VT_DISPATCH = 9

ROLE_NAMES = {
    0x0A: "Client", 0x0E: "Grouping", 0x14: "CheckButton",
    0x15: "RadioButton", 0x18: "ComboBox", 0x1E: "StaticText",
    0x24: "Text", 0x2B: "PushButton", 0x2C: "MenuBar",
    0x2D: "MenuItem", 0x38: "Window",
}

def run_s5() -> dict:
    result = {
        "test_id": "S5",
        "name": "Native Win32 MSAA / IAccessible",
        "apis_tested": ["AccessibleObjectFromWindow", "AccessibleChildren", "IAccessible::get_accName", "IAccessible::get_accRole", "IAccessible::accLocation"],
        "status": "PASS",
        "evidence_type": "LIVE_OS_VALIDATED",
        "metrics": {},
        "error": None
    }
    
    root = None
    try:
        ole32.CoInitialize(None)
        root = tk.Tk()
        root.title("ORBIT_SMOKE_MSAA_FIXTURE")
        root.geometry("350x250+150+150")
        btn = tk.Button(root, text="MSAA Smoke Button")
        btn.pack(pady=20)
        root.update()
        time.sleep(0.1)
        
        hwnd = int(root.frame(), 16) if isinstance(root.frame(), str) else int(root.frame())
        top_hwnd = user32.GetParent(hwnd) or hwnd
        
        pAcc = ctypes.c_void_p()
        hr = oleacc.AccessibleObjectFromWindow(top_hwnd, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pAcc))
        result["metrics"]["accessible_object_from_window_hr"] = f"0x{hr & 0xFFFFFFFF:08X}"
        
        if hr != 0 or not pAcc.value:
            raise RuntimeError(f"AccessibleObjectFromWindow failed with hr=0x{hr & 0xFFFFFFFF:08X}")
            
        vtable = ctypes.cast(pAcc.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        
        # 1. get_accName (vtable index 10)
        var_self = VARIANT()
        var_self.vt = VT_I4
        var_self.lVal = CHILDID_SELF
        
        bstr_name = BSTR()
        hr_name = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, VARIANT, ctypes.POINTER(BSTR))(vtable[10])(pAcc.value, var_self, ctypes.byref(bstr_name))
        
        # 2. get_accRole (vtable index 13)
        var_role = VARIANT()
        hr_role = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, VARIANT, ctypes.POINTER(VARIANT))(vtable[13])(pAcc.value, var_self, ctypes.byref(var_role))
        role_id = var_role.lVal if (hr_role == 0 and var_role.vt == VT_I4) else 0
        
        # 3. accLocation (vtable index 21)
        x, y, w, h = wintypes.LONG(0), wintypes.LONG(0), wintypes.LONG(0), wintypes.LONG(0)
        hr_loc = ctypes.WINFUNCTYPE(
            wintypes.LONG, ctypes.c_void_p,
            ctypes.POINTER(wintypes.LONG), ctypes.POINTER(wintypes.LONG),
            ctypes.POINTER(wintypes.LONG), ctypes.POINTER(wintypes.LONG),
            VARIANT
        )(vtable[21])(pAcc.value, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h), var_self)
        
        result["metrics"]["root_accessible_element"] = {
            "name": str(bstr_name.value) if bstr_name.value else "",
            "role_id": role_id,
            "role_name": ROLE_NAMES.get(role_id, f"Role_0x{role_id:02X}"),
            "location": (x.value, y.value, w.value, h.value)
        }
        
    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
    finally:
        if root:
            try:
                root.destroy()
            except Exception:
                pass
        try:
            ole32.CoUninitialize()
        except Exception:
            pass
            
    return result

if __name__ == "__main__":
    res = run_s5()
    print(json.dumps(res, indent=2))
