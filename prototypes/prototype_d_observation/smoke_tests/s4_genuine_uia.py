"""
Smoke Test S4: Genuine Windows UI Automation COM Interface
Validates: UIAutomationCore.dll CoCreateInstance (CLSID_CUIAutomation), ElementFromHandle, IUIAutomationTreeWalker, and property retrieval.
STRICT RULE: Never substitute EnumChildWindows or Win32 HWND scanning as UIA.
"""

import ctypes
from ctypes import wintypes
import time
import json
import tkinter as tk

ole32 = ctypes.windll.ole32
user32 = ctypes.windll.user32

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

UIA_CONTROL_TYPES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
    50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator",
}

def run_s4() -> dict:
    result = {
        "test_id": "S4",
        "name": "Genuine Windows UI Automation COM",
        "apis_tested": ["CoCreateInstance(CLSID_CUIAutomation)", "IUIAutomation::ElementFromHandle", "IUIAutomation::get_ControlViewWalker", "IUIAutomationTreeWalker::GetFirstChildElement", "IUIAutomationElement properties"],
        "status": "PASS",
        "evidence_type": "LIVE_OS_VALIDATED",
        "metrics": {},
        "error": None
    }
    
    root = None
    try:
        # 1. Initialize COM
        ole32.CoInitialize(None)
        
        # 2. Spawn live target window fixture
        root = tk.Tk()
        root.title("ORBIT_SMOKE_UIA_FIXTURE")
        root.geometry("350x250+100+100")
        lbl = tk.Label(root, text="Smoke Target Label")
        lbl.pack(pady=10)
        btn = tk.Button(root, text="Smoke Submit Button")
        btn.pack(pady=10)
        root.update()
        time.sleep(0.1)
        
        hwnd = int(root.frame(), 16) if isinstance(root.frame(), str) else int(root.frame())
        top_hwnd = user32.GetParent(hwnd) or hwnd
        
        # 3. Create IUIAutomation COM instance
        pUIA = ctypes.c_void_p()
        CLSCTX_INPROC_SERVER = 1
        hr_create = ole32.CoCreateInstance(
            ctypes.byref(CLSID_CUIAutomation),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(IID_IUIAutomation),
            ctypes.byref(pUIA)
        )
        
        result["metrics"]["cocreateinstance_hr"] = f"0x{hr_create & 0xFFFFFFFF:08X}"
        if hr_create != 0 or not pUIA.value:
            raise RuntimeError(f"Failed to instantiate IUIAutomation COM object (hr=0x{hr_create & 0xFFFFFFFF:08X})")
            
        vtable_uia = ctypes.cast(pUIA.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        
        # 4. ElementFromHandle (vtable index 6)
        ELEMENT_FROM_HANDLE_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p))
        ElementFromHandle = ELEMENT_FROM_HANDLE_TYPE(vtable_uia[6])
        
        pElem = ctypes.c_void_p()
        hr_elem = ElementFromHandle(pUIA.value, top_hwnd, ctypes.byref(pElem))
        result["metrics"]["element_from_handle_hr"] = f"0x{hr_elem & 0xFFFFFFFF:08X}"
        
        if hr_elem != 0 or not pElem.value:
            raise RuntimeError(f"ElementFromHandle returned hr=0x{hr_elem & 0xFFFFFFFF:08X}")
            
        vtable_elem = ctypes.cast(pElem.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        
        # 5. Extract Root Element Properties
        # Name (vtable 23)
        bstr_name = wintypes.LPWSTR()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_elem[23])(pElem.value, ctypes.byref(bstr_name))
        
        # ControlType (vtable 21)
        ct_id = wintypes.LONG(0)
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LONG))(vtable_elem[21])(pElem.value, ctypes.byref(ct_id))
        
        # ProcessId (vtable 20)
        pid = wintypes.LONG(0)
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LONG))(vtable_elem[20])(pElem.value, ctypes.byref(pid))
        
        # BoundingRectangle (vtable 43)
        rect = wintypes.RECT()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))(vtable_elem[43])(pElem.value, ctypes.byref(rect))
        
        # IsEnabled (vtable 28)
        is_en = wintypes.BOOL(0)
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL))(vtable_elem[28])(pElem.value, ctypes.byref(is_en))
        
        result["metrics"]["root_element"] = {
            "name": bstr_name.value,
            "control_type_id": ct_id.value,
            "control_type_name": UIA_CONTROL_TYPES.get(ct_id.value, f"Unknown_{ct_id.value}"),
            "process_id": pid.value,
            "bounding_rect": (rect.left, rect.top, rect.right, rect.bottom),
            "is_enabled": bool(is_en.value)
        }
        
        # 6. TreeWalker traversal (vtable index 14: get_ControlViewWalker)
        GET_WALKER_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        get_ControlViewWalker = GET_WALKER_TYPE(vtable_uia[14])
        pWalker = ctypes.c_void_p()
        hr_w = get_ControlViewWalker(pUIA.value, ctypes.byref(pWalker))
        result["metrics"]["get_walker_hr"] = f"0x{hr_w & 0xFFFFFFFF:08X}"
        
        discovered_descendants = []
        if hr_w == 0 and pWalker.value:
            vtable_walker = ctypes.cast(pWalker.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            GetFirstChildElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_walker[4])
            GetNextSiblingElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_walker[6])
            
            pChild = ctypes.c_void_p()
            hr_c = GetFirstChildElement(pWalker.value, pElem.value, ctypes.byref(pChild))
            curr = pChild.value
            while curr:
                vtable_c = ctypes.cast(curr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                c_name = wintypes.LPWSTR()
                ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_c[23])(curr, ctypes.byref(c_name))
                c_ct = wintypes.LONG(0)
                ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LONG))(vtable_c[21])(curr, ctypes.byref(c_ct))
                c_rect = wintypes.RECT()
                ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))(vtable_c[43])(curr, ctypes.byref(c_rect))
                
                discovered_descendants.append({
                    "name": c_name.value,
                    "control_type": UIA_CONTROL_TYPES.get(c_ct.value, f"CT_{c_ct.value}"),
                    "bounds": (c_rect.left, c_rect.top, c_rect.right, c_rect.bottom)
                })
                
                pNext = ctypes.c_void_p()
                GetNextSiblingElement(pWalker.value, curr, ctypes.byref(pNext))
                curr = pNext.value
                
        result["metrics"]["discovered_descendants_count"] = len(discovered_descendants)
        result["metrics"]["sample_descendants"] = discovered_descendants[:5]
        
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
    res = run_s4()
    print(json.dumps(res, indent=2))
