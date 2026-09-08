"""UI Automation Accessibility Perception Observer (Step 3).

Interrogates live Windows UI Automation (UIA) COM accessibility trees:
- Discovers named controls (Buttons, Textboxes, Checkboxes, Menus, Documents, Canvas)
- Captures physical bounding boxes, automation IDs, and class names
- Identifies the currently focused interactive element
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import UIElementObservation

logger = logging.getLogger(__name__)


class UIAElementObserver:
    """Production UI Automation accessibility tree walker and element observer."""

    def __init__(self) -> None:
        self._is_win32 = sys.platform == "win32"

    def _ensure_desktop_attached(self) -> None:
        """Ensure current thread is attached to interactive desktop WinSta0\\Default."""
        if not self._is_win32:
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            h_desk = user32.OpenInputDesktop(0, False, 0x01FF)
            if not h_desk:
                h_desk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if h_desk:
                user32.SetThreadDesktop(h_desk)
        except Exception as ex:
            logger.debug("Desktop attach notice in UIA: %s", ex)

    def observe_elements(
        self,
        target_hwnd: Optional[int] = None,
        max_elements: int = 50,
    ) -> Tuple[Optional[UIElementObservation], List[UIElementObservation]]:
        """Interrogate UI Automation tree scoped to target HWND or foreground window."""
        if not self._is_win32:
            return None, []

        self._ensure_desktop_attached()

        try:
            # 1. Try pywinauto.uia backend if available
            try:
                import pywinauto
                from pywinauto import Desktop  
                desktop = Desktop(backend="uia") 
                if target_hwnd:
                    app_win = desktop.window(handle=target_hwnd)
                else:
                    app_win = desktop.active()

                elements: List[UIElementObservation] = []
                focused_elem = None

                # Walk descendants of active/target window
                descendants = app_win.descendants()
                for el in descendants[:max_elements]:
                    try:
                        name = el.window_text().strip()
                        ctrl_type = el.element_info.control_type
                        auto_id = el.element_info.automation_id
                        cls_name = el.element_info.class_name
                        rect = el.rectangle()

                        # Skip 0-dimension elements
                        w = rect.width()
                        h = rect.height()
                        if w <= 0 or h <= 0:
                            continue

                        is_vis = el.is_visible()
                        if not is_vis:
                            continue

                        has_focus = False
                        try:
                            has_focus = bool(el.has_keyboard_focus())
                        except Exception:
                            pass

                        bbox = BoundingBox(left=rect.left, top=rect.top, width=w, height=h)
                        obs = UIElementObservation(
                            element_id=f"uia_{uuid4().hex[:8]}",
                            name=name if name else None,
                            control_type=ctrl_type,
                            automation_id=auto_id if auto_id else None,
                            class_name=cls_name if cls_name else None,
                            is_enabled=el.is_enabled(),
                            is_visible=True,
                            has_keyboard_focus=has_focus,
                            bounding_box=bbox,
                            parent_context=app_win.window_text(),
                            hwnd=target_hwnd or el.handle,
                        )
                        elements.append(obs)
                        if has_focus and focused_elem is None:
                            focused_elem = obs

                    except Exception:
                        continue

                return focused_elem, elements

            except ImportError:
                pass
            except Exception as pywin_err:
                logger.debug("pywinauto UIA traversal notice: %s", pywin_err)

            # 2. Fallback to native EnumChildWindows for Win32 controls
            return self._observe_win32_controls(target_hwnd)

        except Exception as ex:
            logger.debug("UIA element observation notice: %s", ex)
            return None, []

    def _observe_win32_controls(
        self,
        parent_hwnd: Optional[int] = None,
    ) -> Tuple[Optional[UIElementObservation], List[UIElementObservation]]:
        """Fallback Win32 child window control discovery."""
        if not parent_hwnd:
            return None, []

        try:
            import ctypes
            import ctypes.wintypes
            user32 = ctypes.windll.user32

            elements: List[UIElementObservation] = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

            def enum_child_proc(hwnd: int, lparam: Any) -> bool:
                if not user32.IsWindowVisible(hwnd):
                    return True

                length = user32.GetWindowTextLengthW(hwnd)
                title = ""
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()

                cls_buff = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buff, 256)
                cls_name = cls_buff.value

                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top

                if w > 0 and h > 0:
                    elements.append(
                        UIElementObservation(
                            element_id=f"win32_{uuid4().hex[:8]}",
                            name=title if title else None,
                            control_type=self._map_class_to_control_type(cls_name),
                            automation_id=None,
                            class_name=cls_name,
                            is_enabled=True,
                            is_visible=True,
                            has_keyboard_focus=False,
                            bounding_box=BoundingBox(left=rect.left, top=rect.top, width=w, height=h),
                            hwnd=hwnd,
                        )
                    )
                return True

            user32.EnumChildWindows(parent_hwnd, WNDENUMPROC(enum_child_proc), 0)
            return None, elements

        except Exception:
            return None, []

    def _map_class_to_control_type(self, cls_name: str) -> str:
        """Map standard Win32 window classes to semantic control types."""
        cls_low = cls_name.lower()
        if "button" in cls_low:
            return "Button"
        elif "edit" in cls_low:
            return "Edit"
        elif "combobox" in cls_low:
            return "ComboBox"
        elif "listbox" in cls_low:
            return "ListBox"
        elif "static" in cls_low:
            return "Text"
        elif "richedit" in cls_low:
            return "Document"
        return "Custom"
