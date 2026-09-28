"""ORBIT Native UIA Tree & Cache Subsystem.

Sensory perception infrastructure providing high-performance accessibility tree
interrogation and cached traversal for Windows UI Automation.
"""

from orbit.adapters.uia.tree.cache_utils import (
    CacheRequestFactory,
    CachedControlHelper,
    create_tree_traversal_cache,
)
from orbit.adapters.uia.tree.service import TreeService
from orbit.adapters.uia.tree.traversal import (
    INTERACTIVE_CONTROL_TYPES,
    extract_observation_from_control,
    traverse_tree,
)

__all__ = [
    "CacheRequestFactory",
    "CachedControlHelper",
    "create_tree_traversal_cache",
    "TreeService",
    "INTERACTIVE_CONTROL_TYPES",
    "extract_observation_from_control",
    "traverse_tree",
]
