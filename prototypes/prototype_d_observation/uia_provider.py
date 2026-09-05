"""
Genuine Windows UI Automation Provider for ORBIT Prototype D v1.3.1.
Directly communicates with Windows UI Automation infrastructure (UIAutomationCore.dll / IUIAutomation COM interfaces).
Traverses live IUIAutomationElement hierarchies with cooperative cancellation, depth limits, and structured ProviderResult emission.
STRICT RULE: Emits evidence tagged as UI_AUTOMATION; never substitutes Win32 HWND enumeration as UIA.
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
    UIA_CONTROL_TYPE_NAMES,
)

ole32 = ctypes.windll.ole32
user32 = ctypes.windll.user32

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

ole32.IIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
ole32.IIDFromString.restype = wintypes.LONG

CLSID_CUIAutomation = GUID()
IID_IUIAutomation = GUID()
ole32.IIDFromString("{ff48dba4-60ef-4201-aa87-54103eef594e}", ctypes.byref(CLSID_CUIAutomation))
ole32.IIDFromString("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}", ctypes.byref(IID_IUIAutomation))

CLSCTX_INPROC_SERVER = 1


class UIAutomationProvider:
    """
    Genuine Microsoft Windows UI Automation COM Provider.
    Interacts directly with UIAutomationCore.dll.
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
        Traverses genuine IUIAutomation elements for target window handle.
        """
        t0 = time.perf_counter()
        if not hwnd or not user32.IsWindow(hwnd):
            return ProviderResult(
                provider_name="UI_AUTOMATION",
                status=ProviderStatus.FAILED,
                error_reason=ProviderErrorReason.INVALID_HWND,
                elements=(),
                is_partial=False,
                duration_ms=0.0,
                timeout_occurred=False,
                error_message=f"HWND {hwnd} is invalid or closed",
                worker_state="WORKER_EXIT_CONFIRMED",
            )

        # 1. Instantiate IUIAutomation COM object
        pUIA = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_CUIAutomation),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(IID_IUIAutomation),
            ctypes.byref(pUIA)
        )

        if hr != 0 or not pUIA.value:
            return ProviderResult(
                provider_name="UI_AUTOMATION",
                status=ProviderStatus.UNAVAILABLE,
                error_reason=ProviderErrorReason.COM_FAILURE,
                elements=(),
                is_partial=False,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                timeout_occurred=False,
                error_message=f"CoCreateInstance(CLSID_CUIAutomation) failed with hr=0x{hr & 0xFFFFFFFF:08X}",
                worker_state="WORKER_EXIT_CONFIRMED",
            )

        elements: List[UIElementObservation] = []
        timed_out = False

        try:
            vtable_uia = ctypes.cast(pUIA.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            
            # ElementFromHandle (vtable index 6)
            ELEMENT_FROM_HANDLE_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p))
            ElementFromHandle = ELEMENT_FROM_HANDLE_TYPE(vtable_uia[6])
            
            pRootElem = ctypes.c_void_p()
            hr_elem = ElementFromHandle(pUIA.value, hwnd, ctypes.byref(pRootElem))
            if hr_elem != 0 or not pRootElem.value:
                return ProviderResult(
                    provider_name="UI_AUTOMATION",
                    status=ProviderStatus.UNAVAILABLE,
                    error_reason=ProviderErrorReason.PROVIDER_UNAVAILABLE,
                    elements=(),
                    is_partial=False,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    timeout_occurred=False,
                    error_message=f"ElementFromHandle returned hr=0x{hr_elem & 0xFFFFFFFF:08X}",
                    worker_state="WORKER_EXIT_CONFIRMED",
                )

            # get_ControlViewWalker (vtable index 14)
            GET_WALKER_TYPE = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
            get_ControlViewWalker = GET_WALKER_TYPE(vtable_uia[14])
            pWalker = ctypes.c_void_p()
            hr_walker = get_ControlViewWalker(pUIA.value, ctypes.byref(pWalker))
            if hr_walker != 0 or not pWalker.value:
                return ProviderResult(
                    provider_name="UI_AUTOMATION",
                    status=ProviderStatus.UNAVAILABLE,
                    error_reason=ProviderErrorReason.COM_FAILURE,
                    elements=(),
                    is_partial=False,
                    duration_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    timeout_occurred=False,
                    error_message=f"get_ControlViewWalker failed with hr=0x{hr_walker & 0xFFFFFFFF:08X}",
                    worker_state="WORKER_EXIT_CONFIRMED",
                )

            # Extract root element properties first
            self._extract_element(pRootElem.value, hwnd, 0, generation_id, elements)

            # Traverse descendants via TreeWalker
            self._traverse_tree(
                pWalker_ptr=pWalker.value,
                pElem_ptr=pRootElem.value,
                hwnd=hwnd,
                depth=1,
                max_depth=max_depth,
                generation_id=generation_id,
                elements_out=elements,
                cancellation_event=cancellation_event,
            )

        except Exception as e:
            t1 = time.perf_counter()
            return ProviderResult(
                provider_name="UI_AUTOMATION",
                status=ProviderStatus.PARTIAL_SUCCESS if elements else ProviderStatus.FAILED,
                error_reason=ProviderErrorReason.PROVIDER_EXCEPTION,
                elements=tuple(elements),
                is_partial=True,
                duration_ms=round((t1 - t0) * 1000.0, 2),
                timeout_occurred=False,
                error_message=str(e),
                worker_state="WORKER_EXIT_CONFIRMED",
            )

        t1 = time.perf_counter()
        duration_ms = round((t1 - t0) * 1000.0, 2)
        if cancellation_event and cancellation_event.is_set():
            timed_out = True

        status = ProviderStatus.SUCCESS if elements and not timed_out else (
            ProviderStatus.PARTIAL_SUCCESS if elements else (
                ProviderStatus.TIMEOUT if timed_out else ProviderStatus.UNAVAILABLE
            )
        )

        return ProviderResult(
            provider_name="UI_AUTOMATION",
            status=status,
            error_reason=ProviderErrorReason.NONE if status in (ProviderStatus.SUCCESS, ProviderStatus.PARTIAL_SUCCESS) else ProviderErrorReason.PROVIDER_UNAVAILABLE,
            elements=tuple(elements),
            is_partial=timed_out or (len(elements) == 0),
            duration_ms=duration_ms,
            timeout_occurred=timed_out,
            error_message=None,
            worker_state="WORKER_EXIT_CONFIRMED",
        )

    def _extract_element(
        self,
        pElem_ptr: int,
        hwnd: int,
        depth: int,
        generation_id: int,
        elements_out: List[UIElementObservation],
    ):
        vtable_e = ctypes.cast(pElem_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

        # 23: get_CurrentName
        bstr_name = wintypes.LPWSTR()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_e[23])(pElem_ptr, ctypes.byref(bstr_name))
        name = bstr_name.value if bstr_name.value else None

        # 21: get_CurrentControlType
        ct_id = wintypes.LONG(0)
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LONG))(vtable_e[21])(pElem_ptr, ctypes.byref(ct_id))
        ctrl_type_str = UIA_CONTROL_TYPE_NAMES.get(ct_id.value, f"UiaControl_0x{ct_id.value:04X}")

        # 22: get_CurrentLocalizedControlType
        loc_ct = wintypes.LPWSTR()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_e[22])(pElem_ptr, ctypes.byref(loc_ct))
        role_str = loc_ct.value if loc_ct.value else ctrl_type_str

        # 28: get_CurrentIsEnabled
        is_en = wintypes.BOOL(0)
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL))(vtable_e[28])(pElem_ptr, ctypes.byref(is_en))

        # 29: get_CurrentAutomationId
        auto_id = wintypes.LPWSTR()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_e[29])(pElem_ptr, ctypes.byref(auto_id))
        automation_id = auto_id.value if auto_id.value else None

        # 30: get_CurrentClassName
        cls_name = wintypes.LPWSTR()
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))(vtable_e[30])(pElem_ptr, ctypes.byref(cls_name))

        # 36: get_CurrentNativeWindowHandle
        native_hwnd = wintypes.HWND(0)
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.HWND))(vtable_e[36])(pElem_ptr, ctypes.byref(native_hwnd))

        # 38: get_CurrentIsOffscreen
        is_off = wintypes.BOOL(0)
        ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL))(vtable_e[38])(pElem_ptr, ctypes.byref(is_off))

        # 43: get_CurrentBoundingRectangle
        rect = wintypes.RECT()
        hr_rect = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT))(vtable_e[43])(pElem_ptr, ctypes.byref(rect))

        if hr_rect == 0 and (rect.right - rect.left > 0) and (rect.bottom - rect.top > 0):
            elem_rect = Rect(left=rect.left, top=rect.top, right=rect.right, bottom=rect.bottom)
            elem_id = f"uia_{hwnd}_{depth}_{len(elements_out)}_{elem_rect.left}_{elem_rect.top}"
            elem = UIElementObservation(
                element_id=elem_id,
                evidence_source=EvidenceSource.UI_AUTOMATION.value,
                name=name,
                role=role_str,
                control_type=ctrl_type_str,
                automation_id=automation_id,
                bounds=elem_rect,
                is_enabled=bool(is_en.value),
                is_focused=False,
                is_offscreen=bool(is_off.value),
                timestamp_ns=time.perf_counter_ns(),
                generation_id=generation_id,
                confidence=ConfidenceLevel.PARTIALLY_CONFIRMED,
                class_name=cls_name.value if cls_name.value else None,
                native_hwnd=native_hwnd.value if native_hwnd.value else None,
            )
            elements_out.append(elem)

    def _traverse_tree(
        self,
        pWalker_ptr: int,
        pElem_ptr: int,
        hwnd: int,
        depth: int,
        max_depth: int,
        generation_id: int,
        elements_out: List[UIElementObservation],
        cancellation_event: Optional[threading.Event],
    ):
        if depth > max_depth or (cancellation_event and cancellation_event.is_set()):
            return

        vtable_walker = ctypes.cast(pWalker_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        # 4: GetFirstChildElement
        GetFirstChildElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_walker[4])
        # 6: GetNextSiblingElement
        GetNextSiblingElement = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_walker[6])

        pChild = ctypes.c_void_p()
        hr_child = GetFirstChildElement(pWalker_ptr, pElem_ptr, ctypes.byref(pChild))
        if hr_child != 0 or not pChild.value:
            return

        curr = pChild.value
        while curr:
            if cancellation_event and cancellation_event.is_set():
                break

            self._extract_element(curr, hwnd, depth, generation_id, elements_out)

            # Recursive descent
            if depth < max_depth:
                self._traverse_tree(
                    pWalker_ptr=pWalker_ptr,
                    pElem_ptr=curr,
                    hwnd=hwnd,
                    depth=depth + 1,
                    max_depth=max_depth,
                    generation_id=generation_id,
                    elements_out=elements_out,
                    cancellation_event=cancellation_event,
                )

            pNext = ctypes.c_void_p()
            hr_next = GetNextSiblingElement(pWalker_ptr, curr, ctypes.byref(pNext))
            curr = pNext.value if (hr_next == 0 and pNext.value) else None
