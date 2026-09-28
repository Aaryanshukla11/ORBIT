"""UIA Tree Caching Utilities for Performance Optimization.

Adapted from Windows-Use UIA substrate for ORBIT perception.
Provides UI Automation cache request creation and cached control navigation
to eliminate redundant cross-process COM calls during accessibility tree traversal.

Architectural Guarantees:
- Sensory infrastructure only (zero actuation, zero action planning).
- Typed COM/UIA exception handling preserving ORBIT exceptions.
- Fail-safe fallback to uncached traversal if cache request is unsupported or fails.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from orbit.adapters.uia.core import CacheRequest
from orbit.adapters.uia.controls import Control
from orbit.adapters.uia.enums import PatternId, PropertyId, TreeScope
from orbit.adapters.uia.exceptions import (
    UIADeadElementError,
    UIANotSupportedError,
    UIAException,
)

logger = logging.getLogger(__name__)

# Core properties required for accessibility tree perception and bounding-box validation
PERCEPTION_PROPERTY_IDS: List[int] = [
    # Basic identification
    PropertyId.NameProperty,
    PropertyId.AutomationIdProperty,
    PropertyId.ControlTypeProperty,
    PropertyId.LocalizedControlTypeProperty,
    PropertyId.ClassNameProperty,
    # State and focus
    PropertyId.IsEnabledProperty,
    PropertyId.IsOffscreenProperty,
    PropertyId.IsControlElementProperty,
    PropertyId.HasKeyboardFocusProperty,
    PropertyId.IsKeyboardFocusableProperty,
    PropertyId.AcceleratorKeyProperty,
    PropertyId.HelpTextProperty,
    PropertyId.IsPasswordProperty,
    # Layout and geometry
    PropertyId.BoundingRectangleProperty,
    # Legacy accessible and scroll properties
    PropertyId.LegacyIAccessibleRoleProperty,
    PropertyId.LegacyIAccessibleValueProperty,
    PropertyId.LegacyIAccessibleDefaultActionProperty,
    PropertyId.LegacyIAccessibleStateProperty,
    PropertyId.ScrollHorizontallyScrollableProperty,
    PropertyId.ScrollVerticallyScrollableProperty,
    PropertyId.WindowIsModalProperty,
]

# Patterns for container and interactive inspection
PERCEPTION_PATTERN_IDS: List[int] = [
    PatternId.LegacyIAccessiblePattern,
    PatternId.ScrollPattern,
    PatternId.WindowPattern,
]


class CacheRequestFactory:
    """Factory for creating optimized UI Automation cache requests for perception tree traversal."""

    @staticmethod
    def create_tree_traversal_cache() -> Optional[CacheRequest]:
        """Create a CacheRequest pre-configured with perception properties and patterns.

        Configures TreeScope to cache both the target element and its immediate children,
        allowing batch-retrieval of child elements with properties pre-populated in COM memory.

        Returns:
            Configured CacheRequest instance, or None if UIA caching is unavailable.
        """
        try:
            cache_request = CacheRequest()
            # Scope to cache element and children for batch property retrieval
            cache_request.TreeScope = TreeScope.TreeScope_Element | TreeScope.TreeScope_Children

            # Register required perception properties safely
            for prop_id in PERCEPTION_PROPERTY_IDS:
                try:
                    cache_request.AddProperty(prop_id)
                except Exception as p_err:
                    logger.debug("Property %s not supported in CacheRequest: %s", prop_id, p_err)

            # Register patterns safely
            for pat_id in PERCEPTION_PATTERN_IDS:
                try:
                    cache_request.AddPattern(pat_id)
                except Exception as pat_err:
                    logger.debug("Pattern %s not supported in CacheRequest: %s", pat_id, pat_err)

            return cache_request
        except (UIANotSupportedError, UIAException, Exception) as ex:
            logger.debug("CacheRequest creation failed (falling back to uncached traversal): %s", ex)
            return None


def create_tree_traversal_cache() -> Optional[CacheRequest]:
    """Convenience helper to create a tree traversal cache request."""
    return CacheRequestFactory.create_tree_traversal_cache()


class CachedControlHelper:
    """Helper for building cached controls and retrieving cached child hierarchies safely."""

    @staticmethod
    def build_cached_control(
        node: Any,
        cache_request: Optional[CacheRequest] = None,
    ) -> Any:
        """Build an updated cached version of a control.

        Args:
            node: Source Control instance.
            cache_request: Optional custom CacheRequest. If None, default traversal cache is used.

        Returns:
            Control with cached properties populated, or the original node if caching fails.
        """
        if cache_request is None:
            cache_request = CacheRequestFactory.create_tree_traversal_cache()

        if cache_request is None:
            return node

        try:
            cached_node = node.BuildUpdatedCache(cache_request)
            if cached_node is not None:
                setattr(cached_node, "_is_cached", True)
                return cached_node
            return node
        except (UIADeadElementError, UIANotSupportedError):
            return node
        except Exception as ex:
            logger.debug("Failed building cached control (returning original): %s", ex)
            return node

    @staticmethod
    def get_cached_children(
        node: Any,
        cache_request: Optional[CacheRequest] = None,
    ) -> List[Any]:
        """Retrieve child controls with pre-cached properties to eliminate round-trip COM calls.

        If cached child retrieval fails, encounters a dead element, or is unsupported,
        this method gracefully falls back to node.GetChildren().

        Args:
            node: Parent Control instance.
            cache_request: Optional CacheRequest. If None, default traversal cache is used.

        Returns:
            List of child Control instances (with cached properties when successful).
        """
        if cache_request is None:
            cache_request = CacheRequestFactory.create_tree_traversal_cache()

        if cache_request is None:
            try:
                return node.GetChildren()
            except Exception:
                return []

        try:
            req_clone = cache_request.Clone()
            req_clone.TreeScope = TreeScope.TreeScope_Children
        except Exception as clone_err:
            logger.debug("Failed cloning CacheRequest (%s); falling back to uncached GetChildren", clone_err)
            try:
                return node.GetChildren()
            except Exception:
                return []

        try:
            # Query updated element with child cache populated
            element = getattr(node, "Element", None)
            if not element:
                return node.GetChildren()

            updated_element = element.BuildUpdatedCache(req_clone.check_request)
            if not updated_element:
                return node.GetChildren()

            element_array = updated_element.GetCachedChildren()
            if not element_array:
                return []

            children: List[Any] = []
            length = getattr(element_array, "Length", 0)
            for i in range(length):
                try:
                    child_elem = element_array.GetElement(i)
                    if child_elem:
                        child_control = Control.CreateControlFromElement(child_elem)
                        if child_control:
                            setattr(child_control, "_is_cached", True)
                            children.append(child_control)
                except (UIADeadElementError, UIANotSupportedError):
                    continue
                except Exception as child_err:
                    logger.debug("Error instantiating cached child %d: %s", i, child_err)
                    continue

            return children

        except (UIADeadElementError, UIANotSupportedError):
            return []
        except Exception as ex:
            logger.debug("Cached children retrieval failed (%s); falling back to GetChildren", ex)
            try:
                return node.GetChildren()
            except Exception:
                return []
