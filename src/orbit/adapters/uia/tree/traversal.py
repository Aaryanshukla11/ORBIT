"""UIA Tree Traversal and Perception Normalization Subsystem.

Provides depth-bounded, deduplicated UI Automation accessibility tree traversal.
Translates native/cached COM controls into canonical ORBIT UIElementObservation models.

Architectural Invariants:
1. Sensory infrastructure only (zero clicks, keypresses, mouse movements, or window mutations).
2. Never invokes planning, world model mutation, or physical actuation.
3. Fails safely on dead, disabled, or inaccessible COM elements without crashing.
4. Produces canonical UIElementObservation contracts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional, Set, Tuple
from uuid import uuid4

from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import UIElementObservation
from orbit.adapters.uia.core import Rect
from orbit.adapters.uia.controls import Control
from orbit.adapters.uia.enums import ControlType
from orbit.adapters.uia.exceptions import (
    UIADeadElementError,
    UIANotEnabledError,
    UIARetryableError,
    UIAException,
)
from orbit.adapters.uia.tree.cache_utils import CachedControlHelper

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


def _get_property_safe(control: Any, prop_name: str, cached_prop_name: str, default: Any = None) -> Any:
    """Read a property preferentially from cache if control is cached, falling back to live access."""
    is_cached = getattr(control, "_is_cached", False)
    if is_cached:
        try:
            val = getattr(control, cached_prop_name)
            if val is not None:
                return val
        except (UIADeadElementError, UIANotEnabledError):
            raise
        except Exception:
            pass  # Fall back to live access

    try:
        val = getattr(control, prop_name, default)
        return val if val is not None else default
    except (UIADeadElementError, UIANotEnabledError):
        raise
    except Exception:
        return default


def extract_observation_from_control(
    control: Any,
    parent_context: str = "",
    target_hwnd: Optional[int] = None,
    is_focused: bool = False,
) -> Optional[UIElementObservation]:
    """Convert a native or cached Control instance into a canonical UIElementObservation.

    Args:
        control: The Control instance to inspect.
        parent_context: Context string (e.g. window title).
        target_hwnd: Scoped HWND identifier.
        is_focused: Whether this control is known to be the active keyboard focus.

    Returns:
        UIElementObservation if the control is interactive or has semantic identity; None otherwise.
    """
    try:
        ctrl_type_id = _get_property_safe(control, "ControlType", "CachedControlType", 0)
        type_name = _get_property_safe(control, "ControlTypeName", "CachedControlTypeName", "Control")
        name = _get_property_safe(control, "Name", "CachedName", "")
        auto_id = _get_property_safe(control, "AutomationId", "CachedAutomationId", "")
        cls_name = _get_property_safe(control, "ClassName", "CachedClassName", "")
        is_enabled = bool(_get_property_safe(control, "IsEnabled", "CachedIsEnabled", False))
        has_focus = is_focused or bool(_get_property_safe(control, "HasKeyboardFocus", "CachedHasKeyboardFocus", False))

        # Check BoundingRectangle
        rect = _get_property_safe(control, "BoundingRectangle", "CachedBoundingRectangle", None)
        b_box: Optional[BoundingBox] = None
        if rect is not None:
            try:
                w = rect.width() if callable(getattr(rect, "width", None)) else getattr(rect, "width", 0)
                h = rect.height() if callable(getattr(rect, "height", None)) else getattr(rect, "height", 0)
                left = getattr(rect, "left", 0)
                top = getattr(rect, "top", 0)
                if w > 0 and h > 0:
                    b_box = BoundingBox(left=left, top=top, width=w, height=h)
            except Exception:
                b_box = None

        # Offscreen check: if element is marked offscreen and doesn't have focus, it may not be visible
        is_offscreen = bool(_get_property_safe(control, "IsOffscreen", "CachedIsOffscreen", False))
        if is_offscreen and not has_focus and type_name != "EditControl":
            # Invisible or offscreen without focus
            return None

        # Determine if interactive or informative
        is_interactive = ctrl_type_id in INTERACTIVE_CONTROL_TYPES or bool(name) or bool(auto_id)
        if not is_interactive and not has_focus:
            return None

        native_hwnd = _get_property_safe(control, "NativeWindowHandle", "CachedNativeWindowHandle", None)

        return UIElementObservation(
            element_id=f"uia_{uuid4().hex[:8]}",
            name=name or None,
            control_type=type_name or "Control",
            automation_id=auto_id or None,
            class_name=cls_name or None,
            is_enabled=is_enabled,
            is_visible=True if b_box else False,
            has_keyboard_focus=has_focus,
            bounding_box=b_box,
            parent_context=parent_context or None,
            hwnd=target_hwnd or native_hwnd,
        )
    except (UIADeadElementError, UIANotEnabledError):
        return None
    except Exception as ex:
        logger.debug("Failed converting Control to UIElementObservation: %s", ex)
        return None


def traverse_tree(
    root_control: Any,
    max_depth: int = 8,
    max_elements: int = 50,
    timeout_sec: float = 2.5,
    cache_request: Optional[Any] = None,
    parent_context: str = "",
    target_hwnd: Optional[int] = None,
) -> List[UIElementObservation]:
    """Execute bounded depth-limited traversal over the accessibility tree.

    Leverages CachedControlHelper for batch child retrieval and cached property access.
    Enforces element count, depth, and wall-clock timeout boundaries.

    Args:
        root_control: Starting root Control node.
        max_depth: Maximum recursion depth from root.
        max_elements: Maximum number of elements to extract.
        timeout_sec: Maximum time in seconds to spend traversing.
        cache_request: Optional CacheRequest for pre-caching.
        parent_context: Context string (e.g. window title).
        target_hwnd: Target HWND handle.

    Returns:
        List of canonical UIElementObservation objects matching interactive criteria.
    """
    seen_ids: Set[str] = set()
    extracted_elements: List[UIElementObservation] = []
    stack: List[Tuple[Control, int]] = [(root_control, 0)]
    t_start = time.perf_counter()

    while stack and len(extracted_elements) < max_elements:
        if (time.perf_counter() - t_start) > timeout_sec:
            logger.debug("UIA tree traversal reached timeout (%.2fs)", timeout_sec)
            break

        curr_ctrl, depth = stack.pop()
        if depth > max_depth:
            continue

        try:
            # Process non-root elements for observation extraction
            if curr_ctrl != root_control:
                obs = extract_observation_from_control(
                    control=curr_ctrl,
                    parent_context=parent_context,
                    target_hwnd=target_hwnd,
                    is_focused=False,
                )
                if obs and obs.bounding_box and obs.bounding_box.width > 0 and obs.bounding_box.height > 0:
                    elem_key = None
                    try:
                        if hasattr(curr_ctrl, "GetRuntimeId"):
                            r_id = curr_ctrl.GetRuntimeId()
                            if r_id:
                                elem_key = f"rid:{':'.join(str(x) for x in r_id)}"
                    except Exception:
                        elem_key = None

                    if not elem_key:
                        elem_key = (
                            f"{obs.control_type}:{obs.name or ''}:{obs.automation_id or ''}:"
                            f"{obs.bounding_box.left}_{obs.bounding_box.top}_{obs.bounding_box.width}_{obs.bounding_box.height}"
                        )

                    if elem_key not in seen_ids:
                        seen_ids.add(elem_key)
                        extracted_elements.append(obs)

            # Retrieve children (using pre-cached child retrieval when available)
            children = CachedControlHelper.get_cached_children(curr_ctrl, cache_request)
            # Push in reverse order so that earlier children are popped and traversed first
            for child in reversed(children):
                stack.append((child, depth + 1))

        except (UIADeadElementError, UIANotEnabledError):
            # Element was destroyed or disabled during traversal; smoothly skip
            continue
        except (UIARetryableError, UIAException, Exception) as c_err:
            logger.debug("UIA node traversal step error: %s", c_err)
            continue

    return extracted_elements
