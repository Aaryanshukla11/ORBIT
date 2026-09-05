"""
Native Win32 MSAA / IAccessible Provider for ORBIT Prototype D.
Traverses accessible UI hierarchy via oleacc.dll with depth boundaries, cooperative cancellation,
and structured ProviderResult generation.
"""

import ctypes
from ctypes import wintypes
import time
import threading
from typing import List, Optional, Tuple, Any

from app_types import (
    Rect,
    UIElementObservation,
    ProviderResult,
    ProviderStatus,
    ProviderErrorReason,
    ConfidenceLevel,
    EvidenceSource,
)

ole32 = ctypes.windll.ole32
oleacc = ctypes.windll.oleacc
user32 = ctypes.windll.user32

# GUID Struct
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

ole32.IIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
ole32.IIDFromString.restype = wintypes.LONG

IID_IAccessible = GUID()
ole32.IIDFromString("{618736e0-3c3d-11cf-810c-00aa00389b71}", ctypes.byref(IID_IAccessible))

OBJID_CLIENT = 0xFFFFFFFC
CHILDID_SELF = 0

oleacc.AccessibleObjectFromWindow.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
]
oleacc.AccessibleObjectFromWindow.restype = wintypes.LONG

oleacc.AccessibleChildren.argtypes = [
    ctypes.c_void_p, wintypes.LONG, wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LONG)
]
oleacc.AccessibleChildren.restype = wintypes.LONG

BSTR = wintypes.LPWSTR

# VARIANT structure for MSAA COM calls
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

# MSAA Role Strings
ROLE_NAMES = {
    0x0A: "Client",
    0x0E: "Grouping",
    0x14: "CheckButton",
    0x15: "RadioButton",
    0x18: "ComboBox",
    0x1E: "StaticText",
    0x24: "Text",
    0x2B: "PushButton",
    0x2C: "MenuBar",
    0x2D: "MenuItem",
    0x38: "Window",
}


class MSAAProvider:
    """
    Independent MSAA / IAccessible observation driver.
    """

    def __init__(self):
        try:
            ole32.CoInitialize(None)
        except Exception:
            pass

    def traverse_window(
        self,
        hwnd: int,
        max_depth: int = 5,
        cancellation_event: Optional[threading.Event] = None,
        generation_id: int = 0,
    ) -> ProviderResult:
        """
        Traverses IAccessible hierarchy for the specified window handle.
        Returns a structured ProviderResult.
        """
        t0 = time.perf_counter()
        if not hwnd or not user32.IsWindow(hwnd):
            return ProviderResult(
                provider_name="MSAA",
                status=ProviderStatus.FAILED,
                error_reason=ProviderErrorReason.INVALID_HWND,
                elements=(),
                is_partial=False,
                duration_ms=0.0,
                timeout_occurred=False,
                error_message=f"HWND {hwnd} is invalid or closed",
                worker_state="EXIT_CONFIRMED",
            )

        pAcc = ctypes.c_void_p()
        hr = oleacc.AccessibleObjectFromWindow(hwnd, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(pAcc))
        if hr != 0 or not pAcc.value:
            return ProviderResult(
                provider_name="MSAA",
                status=ProviderStatus.UNAVAILABLE,
                error_reason=ProviderErrorReason.PROVIDER_UNAVAILABLE,
                elements=(),
                is_partial=False,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                timeout_occurred=False,
                error_message=f"AccessibleObjectFromWindow returned hr=0x{hr & 0xFFFFFFFF:08X}",
                worker_state="EXIT_CONFIRMED",
            )

        elements: List[UIElementObservation] = []
        is_partial = False

        try:
            self._traverse_node(
                pAcc_ptr=pAcc.value,
                depth=0,
                max_depth=max_depth,
                hwnd=hwnd,
                generation_id=generation_id,
                elements_out=elements,
                cancellation_event=cancellation_event,
            )
        except Exception as e:
            t1 = time.perf_counter()
            return ProviderResult(
                provider_name="MSAA",
                status=ProviderStatus.PARTIAL_SUCCESS if elements else ProviderStatus.FAILED,
                error_reason=ProviderErrorReason.PROVIDER_EXCEPTION,
                elements=tuple(elements),
                is_partial=True,
                duration_ms=round((t1 - t0) * 1000.0, 2),
                timeout_occurred=False,
                error_message=str(e),
                worker_state="EXIT_CONFIRMED",
            )

        t1 = time.perf_counter()
        duration_ms = round((t1 - t0) * 1000.0, 2)
        timed_out = cancellation_event.is_set() if cancellation_event else False

        if timed_out:
            status = ProviderStatus.PARTIAL_SUCCESS if elements else ProviderStatus.TIMEOUT
        else:
            status = ProviderStatus.SUCCESS if elements else ProviderStatus.PARTIAL_SUCCESS

        return ProviderResult(
            provider_name="MSAA",
            status=status,
            error_reason=ProviderErrorReason.NONE,
            elements=tuple(elements),
            is_partial=timed_out or (len(elements) == 0),
            duration_ms=duration_ms,
            timeout_occurred=timed_out,
            error_message=None,
            worker_state="EXIT_CONFIRMED",
        )

    def _traverse_node(
        self,
        pAcc_ptr: int,
        depth: int,
        max_depth: int,
        hwnd: int,
        generation_id: int,
        elements_out: List[UIElementObservation],
        cancellation_event: Optional[threading.Event],
    ):
        if depth > max_depth or (cancellation_event and cancellation_event.is_set()):
            return

        # Query vtable methods for IAccessible
        # vtable layout:
        # [0..2: IUnknown], [3..6: IDispatch]
        # [7: get_accParent], [8: get_accChildCount], [9: get_accChild]
        # [10: get_accName], [11: get_accValue], [12: get_accDescription]
        # [13: get_accRole], [14: get_accState], [15: get_accHelp]
        # [21: accLocation], [24: accDoDefaultAction]
        try:
            vtable = ctypes.cast(pAcc_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

            # 1. get_accChildCount (vtable index 8)
            # HRESULT get_accChildCount([out, retval] long *pcountChildren);
            ACC_CHILD_COUNT_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LONG))
            get_accChildCount = ACC_CHILD_COUNT_TYPE(vtable[8])

            child_count = wintypes.LONG(0)
            hr = get_accChildCount(pAcc_ptr, ctypes.byref(child_count))
            count = child_count.value if hr == 0 else 0

            # 2. get_accName (vtable index 10)
            # HRESULT get_accName(VARIANT varChild, [out, retval] BSTR *pszName);
            ACC_NAME_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, VARIANT, ctypes.POINTER(BSTR))
            get_accName = ACC_NAME_TYPE(vtable[10])

            var_self = VARIANT()
            var_self.vt = VT_I4
            var_self.lVal = CHILDID_SELF

            bstr_name = BSTR()
            hr_name = get_accName(pAcc_ptr, var_self, ctypes.byref(bstr_name))
            name = str(bstr_name.value) if (hr_name == 0 and bstr_name.value) else ""

            # 3. get_accRole (vtable index 13)
            # HRESULT get_accRole(VARIANT varChild, [out, retval] VARIANT *pvarRole);
            ACC_ROLE_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, VARIANT, ctypes.POINTER(VARIANT))
            get_accRole = ACC_ROLE_TYPE(vtable[13])

            var_role = VARIANT()
            hr_role = get_accRole(pAcc_ptr, var_self, ctypes.byref(var_role))
            role_id = var_role.lVal if (hr_role == 0 and var_role.vt == VT_I4) else 0
            role_str = ROLE_NAMES.get(role_id, f"Role_0x{role_id:02X}")

            # 4. accLocation (vtable index 21)
            # HRESULT accLocation([out] long *pxLeft, [out] long *pyTop, [out] long *pcxWidth, [out] long *pcyHeight, VARIANT varChild);
            ACC_LOC_TYPE = ctypes.WINFUNCTYPE(
                wintypes.LONG, ctypes.c_void_p,
                ctypes.POINTER(wintypes.LONG), ctypes.POINTER(wintypes.LONG),
                ctypes.POINTER(wintypes.LONG), ctypes.POINTER(wintypes.LONG),
                VARIANT
            )
            accLocation = ACC_LOC_TYPE(vtable[21])

            x, y, w, h = wintypes.LONG(0), wintypes.LONG(0), wintypes.LONG(0), wintypes.LONG(0)
            hr_loc = accLocation(pAcc_ptr, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h), var_self)

            if hr_loc == 0 and w.value > 0 and h.value > 0:
                rect = Rect(left=x.value, top=y.value, right=x.value + w.value, bottom=y.value + h.value)
                elem_id = f"msaa_{hwnd}_{depth}_{len(elements_out)}_{x.value}_{y.value}"
                elem = UIElementObservation(
                    element_id=elem_id,
                    evidence_source=EvidenceSource.MSAA.value,
                    name=name,
                    role=role_str,
                    control_type=role_str,
                    automation_id=None,
                    bounds=rect,
                    is_enabled=True,
                    is_focused=False,
                    is_offscreen=False,
                    timestamp_ns=time.perf_counter_ns(),
                    generation_id=generation_id,
                    confidence=ConfidenceLevel.PARTIALLY_CONFIRMED,
                )
                elements_out.append(elem)

            # Traverse Children via AccessibleChildren if count > 0
            if count > 0 and depth < max_depth:
                var_array = (VARIANT * count)()
                obtained = wintypes.LONG(0)
                hr_child = oleacc.AccessibleChildren(pAcc_ptr, 0, count, ctypes.byref(var_array), ctypes.byref(obtained))
                if hr_child == 0:
                    for i in range(obtained.value):
                        if cancellation_event and cancellation_event.is_set():
                            break
                        v = var_array[i]
                        if v.vt == VT_DISPATCH and v.pdispVal:
                            self._traverse_node(
                                pAcc_ptr=v.pdispVal,
                                depth=depth + 1,
                                max_depth=max_depth,
                                hwnd=hwnd,
                                generation_id=generation_id,
                                elements_out=elements_out,
                                cancellation_event=cancellation_event,
                            )
        except Exception:
            pass
