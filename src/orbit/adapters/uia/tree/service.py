"""ORBIT Native UIA Tree Service.

Provides lifecycle coordination, window/root resolution, focused control interrogation,
and cached tree traversal for desktop accessibility observation.

Architectural Guarantees:
- Sensory perception infrastructure only (never plans, never executes physical actions).
- Strictly maintains single authoritative observation path into WorldModel / PerceptionFusionEngine.
- Never crashes on dead HWNDs, closed windows, or destroyed COM elements.
"""

from __future__ import annotations

import logging
import sys
from typing import Dict, List, Optional, Tuple

from orbit.runtime.perception.models import UIElementObservation
from orbit.adapters.uia.controls import (
    Control,
    ControlFromHandle,
    GetFocusedControl,
    GetRootControl,
)
from orbit.adapters.uia.exceptions import (
    UIADeadElementError,
    UIANotEnabledError,
    UIARetryableError,
    UIAException,
)
from orbit.adapters.uia.tree.cache_utils import CacheRequestFactory
from orbit.adapters.uia.tree.traversal import (
    extract_observation_from_control,
    traverse_tree,
)

logger = logging.getLogger(__name__)


class TreeService:
    """Production coordinator for accessibility tree observation, root resolution, and cached traversal."""

    def __init__(self) -> None:
        self._is_win32 = sys.platform == "win32"

    def _ensure_desktop_attached(self) -> None:
        """Ensure current thread is attached to the interactive desktop WinSta0\\Default."""
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
            logger.debug("Desktop attach notice in TreeService: %s", ex)

    def resolve_root_control(self, target_hwnd: Optional[int] = None) -> Tuple[Optional[Control], str]:
        """Resolve the root Control node for a target HWND or desktop root.

        Args:
            target_hwnd: Optional window handle.

        Returns:
            Tuple of (root_control, window_title_or_context).
        """
        if target_hwnd and target_hwnd > 0:
            try:
                root_ctrl = ControlFromHandle(target_hwnd)
                if root_ctrl and root_ctrl.Element:
                    window_title = root_ctrl.Name or ""
                    return root_ctrl, window_title
                return None, ""
            except (UIADeadElementError, Exception) as h_err:
                logger.debug("ControlFromHandle failed for HWND %s (window may be dead): %s", target_hwnd, h_err)
                return None, ""

        try:
            root_ctrl = GetRootControl()
            window_title = "Desktop"
            return root_ctrl, window_title
        except Exception as r_err:
            logger.debug("GetRootControl failed: %s", r_err)
            return None, ""

    def get_focused_element(
        self,
        parent_context: str = "",
        target_hwnd: Optional[int] = None,
    ) -> Optional[UIElementObservation]:
        """Extract the currently focused UI element as an observation."""
        try:
            focused_ctrl = GetFocusedControl()
            if focused_ctrl and focused_ctrl.Element:
                # If target_hwnd is specified, ensure the focused control belongs to that window hierarchy
                if target_hwnd and target_hwnd > 0:
                    ctrl_hwnd = getattr(focused_ctrl, "NativeWindowHandle", None)
                    if ctrl_hwnd:
                        try:
                            import ctypes
                            # GA_ROOT = 2
                            root_hwnd = ctypes.windll.user32.GetAncestor(ctrl_hwnd, 2)
                            effective_hwnd = root_hwnd if root_hwnd else ctrl_hwnd
                            if effective_hwnd != target_hwnd:
                                return None
                        except Exception:
                            if ctrl_hwnd != target_hwnd:
                                return None
                    else:
                        return None

                return extract_observation_from_control(
                    control=focused_ctrl,
                    parent_context=parent_context,
                    target_hwnd=target_hwnd,
                    is_focused=True,
                )
        except (UIADeadElementError, UIARetryableError, UIANotEnabledError):
            return None
        except Exception as f_err:
            logger.debug("GetFocusedControl notice: %s", f_err)
            return None
        return None

    def observe_window_elements(
        self,
        target_hwnd: Optional[int] = None,
        max_elements: int = 50,
        max_depth: int = 8,
        timeout_sec: float = 2.5,
    ) -> Tuple[Optional[UIElementObservation], List[UIElementObservation]]:
        """Observe interactive UI elements scoped to a target window HWND or foreground desktop.

        Coordinates root resolution, focus interrogation, cache creation, and bounded traversal.

        Args:
            target_hwnd: Optional target window HWND.
            max_elements: Maximum number of elements to extract.
            max_depth: Maximum tree depth to traverse.
            timeout_sec: Wall-clock timeout for traversal.

        Returns:
            Tuple of (focused_element, list_of_interactive_elements).
        """
        if not self._is_win32:
            return None, []

        self._ensure_desktop_attached()

        try:
            # 1. Resolve root control
            root_ctrl, window_title = self.resolve_root_control(target_hwnd=target_hwnd)
            if not root_ctrl:
                return None, []

            # 2. Extract focused control
            focused_obs = self.get_focused_element(
                parent_context=window_title,
                target_hwnd=target_hwnd,
            )

            # 3. Create tree traversal cache request
            cache_request = CacheRequestFactory.create_tree_traversal_cache()

            # 4. Execute bounded cached traversal
            extracted_elements = traverse_tree(
                root_control=root_ctrl,
                max_depth=max_depth,
                max_elements=max_elements,
                timeout_sec=timeout_sec,
                cache_request=cache_request,
                parent_context=window_title,
                target_hwnd=target_hwnd,
            )

            return focused_obs, extracted_elements

        except UIADeadElementError as dead_err:
            logger.debug("TreeService encountered dead element / destroyed window: %s", dead_err)
            return None, []
        except Exception as ex:
            logger.warning("[TreeService] observe_window_elements failed: %s", ex)
            return None, []

    def get_window_wise_nodes(
        self,
        windows_handles: List[int],
        max_elements_per_window: int = 40,
    ) -> Dict[int, List[UIElementObservation]]:
        """Process windows sequentially to maintain STA (Single-Threaded Apartment) safety.

        Args:
            windows_handles: List of HWND handles to inspect.
            max_elements_per_window: Maximum elements to extract per window.

        Returns:
            Dictionary mapping HWND -> List of UIElementObservation.
        """
        results: Dict[int, List[UIElementObservation]] = {}
        if not self._is_win32:
            return results

        self._ensure_desktop_attached()
        cache_request = CacheRequestFactory.create_tree_traversal_cache()

        for hwnd in windows_handles:
            if not hwnd or hwnd <= 0:
                continue
            try:
                root_ctrl, title = self.resolve_root_control(target_hwnd=hwnd)
                if not root_ctrl:
                    continue

                elements = traverse_tree(
                    root_control=root_ctrl,
                    max_depth=6,
                    max_elements=max_elements_per_window,
                    timeout_sec=1.0,
                    cache_request=cache_request,
                    parent_context=title,
                    target_hwnd=hwnd,
                )
                results[hwnd] = elements
            except (UIADeadElementError, Exception) as ex:
                logger.debug("Skipping window handle %s due to error: %s", hwnd, ex)
                continue

        return results
