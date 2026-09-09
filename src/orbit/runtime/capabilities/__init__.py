"""ORBIT Capabilities Subsystem."""

from __future__ import annotations

from orbit.runtime.capabilities.composition import (
    CapabilityCompositionEngine,
    CompositeCapability,
)
from orbit.runtime.capabilities.environment_discovery import (
    EnvironmentCapabilityDiscovery,
)
from orbit.runtime.capabilities.feasibility import FeasibilityAnalyzer
from orbit.runtime.capabilities.matcher import CapabilityMatchReport, CapabilityMatcher
from orbit.runtime.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilityGapReport,
    CapabilityLimitation,
    CapabilitySource,
    FeasibilityAssessment,
    FeasibilityStatus,
    GoalRequirement,
    GoalRequirementSet,
    StrategyOption,
    StrategySelectionResult,
    StrategyStage,
)
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
from orbit.runtime.capabilities.strategy_selector import StrategySelector

__all__ = [
    "Capability",
    "CapabilityCategory",
    "CapabilityCompositionEngine",
    "CapabilityGapReport",
    "CapabilityLimitation",
    "CapabilityMatchReport",
    "CapabilityMatcher",
    "CapabilityRegistry",
    "CapabilitySource",
    "CompositeCapability",
    "EnvironmentCapabilityDiscovery",
    "FeasibilityAnalyzer",
    "FeasibilityAssessment",
    "FeasibilityStatus",
    "GoalRequirement",
    "GoalRequirementExtractor",
    "GoalRequirementSet",
    "StrategyOption",
    "StrategySelectionResult",
    "StrategySelector",
    "StrategyStage",
]
