"""
Type definitions and data models for Prototype B (Human Takeover & Input Ownership).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import time


class ActionCategory(Enum):
    IDLE = "IDLE"
    PRECISE_CLICK = "PRECISE_CLICK"
    NORMAL_MOVE = "NORMAL_MOVE"
    DRAG_OPERATION = "DRAG_OPERATION"
    TEXT_INPUT = "TEXT_INPUT"


class InputSource(Enum):
    ORBIT_EXPECTED = "ORBIT_EXPECTED"
    USER_PHYSICAL = "USER_PHYSICAL"
    INPUT_AMBIGUOUS = "INPUT_AMBIGUOUS"


class TakeoverState(Enum):
    IDLE = "IDLE"
    EXECUTING = "EXECUTING"
    SUSPECTED_TAKEOVER = "SUSPECTED_TAKEOVER"
    PAUSED_BY_USER = "PAUSED_BY_USER"
    RELEASE_PENDING = "RELEASE_PENDING"


@dataclass
class Point:
    x: int
    y: int

    def distance_to(self, other: "Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


@dataclass
class TrajectoryPoint:
    x: int
    y: int
    timestamp_ns: int
    expected_velocity: float  # px/ms
    threshold_radius: float  # px allowed corridor


@dataclass
class InputEvent:
    event_id: int
    timestamp_ns: int
    event_type: str  # "MOUSE_MOVE", "LBUTTON_DOWN", "LBUTTON_UP", "RBUTTON_DOWN", "KEY_DOWN", "KEY_UP"
    x: int
    y: int
    vk_code: Optional[int] = None
    scan_code: Optional[int] = None
    is_injected: bool = False
    extra_info: int = 0
    source_classification: InputSource = InputSource.INPUT_AMBIGUOUS


@dataclass
class TelemetryRecord:
    event_id: int
    timestamp_ms: float
    action_category: str
    state: str
    observed_pos: Tuple[int, int]
    expected_pos: Optional[Tuple[int, int]]
    deviation_px: float
    allowed_threshold_px: float
    input_source: str
    decision: str  # "CONTINUE", "PAUSE_REQUESTED", "HOLD_PAUSED", "RELEASE_DETECTED"
    decision_latency_us: float  # microseconds
