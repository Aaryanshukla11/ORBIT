"""Target resolution and safe action point domain subsystem."""

from orbit.runtime.targeting.action_point import (
    WIN32_COORD_MAX,
    WIN32_COORD_MIN,
    calculate_safe_action_point,
)
from orbit.runtime.targeting.locator import (
    EvidenceBasedTargetLocator,
    TargetLocator,
)
from orbit.runtime.targeting.models import (
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetIntent,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetStrategy,
)

__all__ = [
    "WIN32_COORD_MAX",
    "WIN32_COORD_MIN",
    "EvidenceBasedTargetLocator",
    "ResolvedTarget",
    "SafeActionPoint",
    "TargetBoundingBox",
    "TargetEvidence",
    "TargetIntent",
    "TargetLocator",
    "TargetResolutionResult",
    "TargetResolutionStatus",
    "TargetStrategy",
    "calculate_safe_action_point",
]
