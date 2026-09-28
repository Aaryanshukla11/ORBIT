"""UIA Element Tree Extractor (Backward-Compatibility Layer).

Provides backward-compatible interface wrapping the ORBIT-native UIA Tree subsystem:
orbit.adapters.uia.tree.service.TreeService
orbit.adapters.uia.tree.cache_utils.CacheRequestFactory
orbit.adapters.uia.tree.traversal.traverse_tree

Ensures existing callers (such as UIAElementObserver and legacy unit tests) continue
to function seamlessly without duplicating the production observation pipeline.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set, Tuple

from orbit.runtime.perception.models import UIElementObservation
from orbit.adapters.uia.controls import Control
from orbit.adapters.uia.tree.service import TreeService
from orbit.adapters.uia.tree.traversal import (
    INTERACTIVE_CONTROL_TYPES,
    extract_observation_from_control,
)

logger = logging.getLogger(__name__)

# Re-export for callers importing INTERACTIVE_CONTROL_TYPES from this module
__all__ = ["INTERACTIVE_CONTROL_TYPES", "UIAElementTreeExtractor"]


class UIAElementTreeExtractor:
    """Production UI Automation accessibility tree walker (compatibility facade around TreeService)."""

    def __init__(self, tree_service: Optional[TreeService] = None) -> None:
        self._tree_service = tree_service or TreeService()

    @property
    def tree_service(self) -> TreeService:
        """Access the underlying TreeService instance."""
        return self._tree_service

    def _ensure_desktop_attached(self) -> None:
        """Delegate desktop attachment to TreeService."""
        self._tree_service._ensure_desktop_attached()

    def observe_elements(
        self,
        target_hwnd: Optional[int] = None,
        max_elements: int = 50,
    ) -> Tuple[Optional[UIElementObservation], List[UIElementObservation]]:
        """Extract UI Automation elements scoped to a target window HWND or foreground window.

        Delegates to the authoritative TreeService.

        Returns:
            Tuple of (focused_element, list_of_interactive_elements)
        """
        return self._tree_service.observe_window_elements(
            target_hwnd=target_hwnd,
            max_elements=max_elements,
        )

    def _control_to_observation(
        self,
        control: Control,
        parent_context: str = "",
        target_hwnd: Optional[int] = None,
        is_focused: bool = False,
    ) -> Optional[UIElementObservation]:
        """Compatibility wrapper for converting a Control instance to UIElementObservation."""
        return extract_observation_from_control(
            control=control,
            parent_context=parent_context,
            target_hwnd=target_hwnd,
            is_focused=is_focused,
        )
