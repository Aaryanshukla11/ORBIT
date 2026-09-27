"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/agent/tree/service.py & cache_utils.py
ORBIT Destination:    src/orbit/adapters/uia/tree_extractor.py
Integration Paradigm: Transduced Body Perceiver (Brain-Body Separation)

Adaptations Applied:
- Removed agent LLM prompt formatting templates (to_prompt_string, index numbering).
- Stripped all autonomous target selection and action logic.
- Retained depth-bounded recursive UIA tree traversal and interactive element filtering.
- Transduced raw COM elements into ORBIT's canonical UIElementObservation and BoundingBox contracts.
- Enforced strict invariant: The tree is purely sensory evidence for EvidenceBasedTargetLocator.
======================================
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import UIElementObservation
from orbit.adapters.uia.core import Rect
from orbit.adapters.uia.controls import (
    Control,
    ControlFromHandle,
    GetFocusedControl,
    GetRootControl,
)
from orbit.adapters.uia.enums import ControlType
from orbit.adapters.uia.exceptions import (
    UIADeadElementError,
    UIANotEnabledError,
    UIARetryableError,
    UIAException,
)

logger = logging.getLogger(__name__)

# Control types that are generally interactive or informative for desktop agents
INTERACTIVE_CONTROL_TYPES: Set[int] = {
    ControlType.ButtonControl,
    ControlType.EditControl,
    ControlType.CheckBoxControl,
    ControlType.RadioButtonControl,
    ControlType.ComboBoxControl,
    ControlType.ListControl,
    ControlType.ListItemControl,
    ControlType.MenuControl,
    ControlType.MenuBarControl,
    ControlType.MenuItemControl,
    ControlType.TabControl,
    ControlType.TabItemControl,
    ControlType.TreeControl,
    ControlType.TreeItemControl,
    ControlType.HyperlinkControl,
    ControlType.DocumentControl,
    ControlType.CustomControl,
    ControlType.ScrollBarControl,
    ControlType.SliderControl,
    ControlType.SpinnerControl,
    ControlType.SplitButtonControl,
    ControlType.ToolBarControl,
    ControlType.HeaderControl,
    ControlType.HeaderItemControl,
    ControlType.TableControl,
    ControlType.DataGridControl,
    ControlType.DataItemControl,
}


class UIAElementTreeExtractor:
    """Production UI Automation accessibility tree walker and element extractor."""

    def __init__(self) -> None:
        self._is_win32 = sys.platform == "win32"

    def _ensure_desktop_attached(self) -> None:
        """Ensure current worker thread is attached to interactive desktop WinSta0\\Default."""
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
            logger.debug("Desktop attach notice in UIA tree extractor: %s", ex)

    def observe_elements(
        self,
        target_hwnd: Optional[int] = None,
        max_elements: int = 50,
    ) -> Tuple[Optional[UIElementObservation], List[UIElementObservation]]:
        """Extract UI Automation elements scoped to a target window HWND or foreground window.

        Returns:
            Tuple of (focused_element, list_of_interactive_elements)
        """
        if not self._is_win32:
            return None, []

        self._ensure_desktop_attached()

        focused_obs: Optional[UIElementObservation] = None
        extracted_elements: List[UIElementObservation] = []

        try:
            # 1. Identify Root Scope Control
            root_ctrl: Optional[Control] = None
            window_title = ""
            if target_hwnd and target_hwnd > 0:
                try:
                    root_ctrl = ControlFromHandle(target_hwnd)
                    if root_ctrl:
                        window_title = root_ctrl.Name or ""
                except Exception as h_err:
                    logger.debug("ControlFromHandle failed for HWND %s: %s", target_hwnd, h_err)

            if not root_ctrl:
                try:
                    root_ctrl = GetRootControl()
                except Exception as r_err:
                    logger.debug("GetRootControl failed: %s", r_err)
                    return None, []

            if not root_ctrl:
                return None, []

            # 2. Check Currently Focused Control
            focused_ctrl: Optional[Control] = None
            try:
                focused_ctrl = GetFocusedControl()
                if focused_ctrl:
                    focused_obs = self._control_to_observation(
                        control=focused_ctrl,
                        parent_context=window_title,
                        target_hwnd=target_hwnd,
                        is_focused=True,
                    )
            except (UIADeadElementError, UIARetryableError, Exception) as f_err:
                logger.debug("GetFocusedControl notice: %s", f_err)

            # 3. Depth-Limited Tree Traversal for Interactive Elements
            seen_ids: Set[str] = set()
            stack: List[Tuple[Control, int]] = [(root_ctrl, 0)]
            max_depth = 8
            t_start = time.perf_counter()
            timeout_sec = 2.5

            while stack and len(extracted_elements) < max_elements:
                if (time.perf_counter() - t_start) > timeout_sec:
                    logger.debug("UIA tree traversal hit timeout (%ss)", timeout_sec)
                    break

                curr_ctrl, depth = stack.pop()
                if depth > max_depth:
                    continue

                try:
                    # Skip offscreen or invisible subtrees when possible
                    if curr_ctrl != root_ctrl:
                        # Extract observation if interactive
                        obs = self._control_to_observation(
                            control=curr_ctrl,
                            parent_context=window_title,
                            target_hwnd=target_hwnd,
                            is_focused=False,
                        )
                        if obs and obs.bounding_box and obs.bounding_box.width > 0 and obs.bounding_box.height > 0:
                            # Unique identifier dedup
                            elem_key = f"{obs.control_type}:{obs.name}:{obs.automation_id}:{obs.bounding_box.left}_{obs.bounding_box.top}"
                            if elem_key not in seen_ids:
                                seen_ids.add(elem_key)
                                extracted_elements.append(obs)

                    # Expand children
                    children = curr_ctrl.GetChildren()
                    # Reverse so first children are processed first in pop()
                    for child in reversed(children):
                        stack.append((child, depth + 1))

                except (UIADeadElementError, UIANotEnabledError):
                    # Element died or is disabled during traversal; skip smoothly
                    continue
                except (UIARetryableError, Exception) as c_err:
                    logger.debug("UIA node traversal error: %s", c_err)
                    continue

        except Exception as ex:
            logger.warning("[UIA TREE EXTRACTOR] observe_elements failed: %s", ex)

        return focused_obs, extracted_elements

    def _control_to_observation(
        self,
        control: Control,
        parent_context: str = "",
        target_hwnd: Optional[int] = None,
        is_focused: bool = False,
    ) -> Optional[UIElementObservation]:
        """Convert a native Control instance into an immutable UIElementObservation."""
        try:
            ctrl_type_id = control.ControlType
            type_name = control.ControlTypeName or "Control"
            name = control.Name or ""
            auto_id = control.AutomationId or ""
            cls_name = control.ClassName or ""
            is_enabled = bool(control.IsEnabled)
            has_focus = is_focused or bool(control.HasKeyboardFocus)

            # Check bounding rectangle
            rect = control.BoundingRectangle
            b_box: Optional[BoundingBox] = None
            if rect and isinstance(rect, Rect):
                w = max(0, rect.width())
                h = max(0, rect.height())
                if w > 0 and h > 0:
                    b_box = BoundingBox(left=rect.left, top=rect.top, width=w, height=h)

            # Only return elements that have some semantic identity or are interactive
            is_interactive = ctrl_type_id in INTERACTIVE_CONTROL_TYPES or bool(name) or bool(auto_id)
            if not is_interactive and not has_focus:
                return None

            return UIElementObservation(
                element_id=f"uia_{uuid4().hex[:8]}",
                name=name or None,
                control_type=type_name,
                automation_id=auto_id or None,
                class_name=cls_name or None,
                is_enabled=is_enabled,
                is_visible=True if b_box else False,
                has_keyboard_focus=has_focus,
                bounding_box=b_box,
                parent_context=parent_context or None,
                hwnd=target_hwnd or getattr(control, "NativeWindowHandle", None),
            )
        except (UIADeadElementError, UIANotEnabledError, Exception):
            return None
