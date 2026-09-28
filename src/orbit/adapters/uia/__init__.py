"""ORBIT Native UI Automation Adapter Package (Phase 1).

Provides high-performance, COM-based Windows UI Automation interaction and
accessibility element tree extraction without external fragile dependencies.
"""

from orbit.adapters.uia.enums import ControlType, PatternId, PropertyId
from orbit.adapters.uia.exceptions import (
    UIADeadElementError,
    UIANotEnabledError,
    UIARetryableError,
    UIAException,
)
from orbit.adapters.uia.tree import (
    CacheRequestFactory,
    CachedControlHelper,
    TreeService,
    create_tree_traversal_cache,
    traverse_tree,
)
from orbit.adapters.uia.tree_extractor import UIAElementTreeExtractor

__all__ = [
    "ControlType",
    "PatternId",
    "PropertyId",
    "UIAException",
    "UIADeadElementError",
    "UIARetryableError",
    "UIANotEnabledError",
    "UIAElementTreeExtractor",
    "TreeService",
    "CacheRequestFactory",
    "CachedControlHelper",
    "create_tree_traversal_cache",
    "traverse_tree",
]
