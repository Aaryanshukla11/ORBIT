"""Mapping functions translating pointer movement results and coordinates for ORBIT."""

from __future__ import annotations

from typing import Any, Dict, Optional
from orbit.adapters.pointer.movement import MovementResult
from orbit.models.common import ScreenPoint


def map_movement_result_to_dict(result: MovementResult) -> Dict[str, Any]:
    """Convert MovementResult to JSON-serializable dictionary for event bus / gateway."""
    return result.model_dump(mode="json")


def map_screen_point_to_coords(point: ScreenPoint) -> tuple[int, int]:
    """Extract physical x, y integers from ScreenPoint."""
    return int(point.x), int(point.y)
