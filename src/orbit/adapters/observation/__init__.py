"""Production Observation Adapter and Snapshot Models."""

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.observation.freshness import FreshnessEvaluator
from orbit.adapters.observation.health import ObservationHealthTracker, ProviderHealthRecord
from orbit.adapters.observation.mapper import (
    map_confidence_level,
    map_detected_target,
    map_prototype_snapshot,
    map_rect_to_bounding_box,
    map_ui_element,
    map_window_observation,
)
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedTarget,
    ObservedWindow,
)

__all__ = [
    "CoordinateSpace",
    "FreshnessEvaluator",
    "FreshnessState",
    "ObservationConfidence",
    "ObservationHealthTracker",
    "ObservationSnapshot",
    "ObservedElement",
    "ObservedTarget",
    "ObservedWindow",
    "ProductionObservationAdapter",
    "ProviderHealthRecord",
    "map_confidence_level",
    "map_detected_target",
    "map_prototype_snapshot",
    "map_rect_to_bounding_box",
    "map_ui_element",
    "map_window_observation",
]
