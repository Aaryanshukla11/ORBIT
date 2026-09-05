"""
Core Type Contracts and Data Models for ORBIT Prototype E.
(Safe Pointer Action & Click Execution Engine — Foundation Contracts)

Strictly defines immutable data structures, enums, coordinate frames,
validation results, ABI validation structures, and diagnostic failure reasons.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any, List


# ----------------------------------------------------------------------
# 1. Coordinate & Spatial Enums
# ----------------------------------------------------------------------

class CoordinateFrame(str, Enum):
    """Explicit coordinate reference systems."""
    PHYSICAL_PIXELS = "PHYSICAL_PIXELS"
    VIRTUAL_DESKTOP = "VIRTUAL_DESKTOP"
    WIN32_NORMALIZED_ABSOLUTE = "WIN32_NORMALIZED_ABSOLUTE"
    WINDOW_EXTENDED_FRAME = "WINDOW_EXTENDED_FRAME"
    CLIENT_COORDINATES = "CLIENT_COORDINATES"


class PointerButton(str, Enum):
    """Mouse button identifiers."""
    NONE = "NONE"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    MIDDLE = "MIDDLE"


class DragPhase(str, Enum):
    """Phases of a multi-stage drag transaction."""
    NOT_DRAGGING = "NOT_DRAGGING"
    MOVING_TO_START = "MOVING_TO_START"
    BUTTON_DOWN = "BUTTON_DOWN"
    DRAGGING = "DRAGGING"
    BUTTON_UP = "BUTTON_UP"
    ABORTED_SANITIZING = "ABORTED_SANITIZING"


# ----------------------------------------------------------------------
# 2. ABI & Platform Enums
# ----------------------------------------------------------------------

class AbiValidationStatus(str, Enum):
    """Win32 SendInput C ABI validation status."""
    ABI_VALID = "ABI_VALID"
    ABI_MISMATCH = "ABI_MISMATCH"
    UNSUPPORTED_PROCESS_ARCHITECTURE = "UNSUPPORTED_PROCESS_ARCHITECTURE"
    NOT_EVALUATED = "NOT_EVALUATED"


# ----------------------------------------------------------------------
# 3. Validation & Safety Enums
# ----------------------------------------------------------------------

class TargetValidationStatus(str, Enum):
    """High-level target validation outcome."""
    VALID = "VALID"
    REJECTED = "REJECTED"


class ValidationFailureReason(str, Enum):
    """Granular, diagnostic reasons for target or coordinate validation failure."""
    NONE = "NONE"
    HWND_NOT_FOUND = "HWND_NOT_FOUND"
    HWND_DESTROYED = "HWND_DESTROYED"
    PID_MISMATCH = "PID_MISMATCH"
    GENERATION_MISMATCH = "GENERATION_MISMATCH"
    SNAPSHOT_TTL_EXPIRED = "SNAPSHOT_TTL_EXPIRED"
    FOREGROUND_LOST = "FOREGROUND_LOST"
    WINDOW_IS_MINIMIZED = "WINDOW_IS_MINIMIZED"
    RECT_MUTATED = "RECT_MUTATED"
    COORDINATE_OUT_OF_BOUNDS = "COORDINATE_OUT_OF_BOUNDS"
    TOPOLOGY_MUTATED = "TOPOLOGY_MUTATED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    ADAPTER_MISSING_REQUIRED_FIELD = "ADAPTER_MISSING_REQUIRED_FIELD"
    ACTION_CANCELLED = "ACTION_CANCELLED"
    INVALID_VIRTUAL_DIMENSIONS = "INVALID_VIRTUAL_DIMENSIONS"
    ABI_MISMATCH = "ABI_MISMATCH"
    UNKNOWN = "UNKNOWN"


class PointerExecutionStatus(str, Enum):
    """Execution status definitions for downstream pointer transactions."""
    NOT_DISPATCHED = "NOT_DISPATCHED"
    DISPATCH_SUCCESS = "DISPATCH_SUCCESS"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    CANCELLED_DURING_TRAJECTORY = "CANCELLED_DURING_TRAJECTORY"
    CANCELLED_DURING_HOLD = "CANCELLED_DURING_HOLD"
    TARGET_VALIDATION_FAILED = "TARGET_VALIDATION_FAILED"
    SENDINPUT_FAILED = "SENDINPUT_FAILED"
    PARTIAL_DISPATCH = "PARTIAL_DISPATCH"
    DISPATCHED_BUT_UNVERIFIED = "DISPATCHED_BUT_UNVERIFIED"
    POST_VERIFICATION_FAILED = "POST_VERIFICATION_FAILED"
    UNRESOLVED_POINTER_STATE = "UNRESOLVED_POINTER_STATE"


class MovementExecutionStatus(str, Enum):
    """Movement-specific execution status."""
    NOT_DISPATCHED = "NOT_DISPATCHED"
    DISPATCH_ACCEPTED = "DISPATCH_ACCEPTED"
    MOVEMENT_VERIFIED = "MOVEMENT_VERIFIED"
    DISPATCHED_BUT_MOVEMENT_UNVERIFIED = "DISPATCHED_BUT_MOVEMENT_UNVERIFIED"
    CURSOR_READBACK_MISMATCH = "CURSOR_READBACK_MISMATCH"
    DISPATCH_ZERO = "DISPATCH_ZERO"
    DISPATCH_PARTIAL_NOT_APPLICABLE = "DISPATCH_PARTIAL_NOT_APPLICABLE"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    CANCELLED_AFTER_DISPATCH = "CANCELLED_AFTER_DISPATCH"
    REJECTED_OUT_OF_BOUNDS = "REJECTED_OUT_OF_BOUNDS"
    REJECTED_TOPOLOGY_MUTATED = "REJECTED_TOPOLOGY_MUTATED"
    ABI_INVALID = "ABI_INVALID"
    REJECTED_PRECONDITION = "REJECTED_PRECONDITION"


class MovementDiagnosticReason(str, Enum):
    """Granular diagnostic reason for movement outcomes."""
    NONE = "NONE"
    EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE = "EXTERNAL_CURSOR_INTERFERENCE_POSSIBLE"
    TOPOLOGY_CHANGE_POSSIBLE = "TOPOLOGY_CHANGE_POSSIBLE"
    EXTERNAL_INPUT_POSSIBLE = "EXTERNAL_INPUT_POSSIBLE"
    QUANTIZATION_VARIANCE = "QUANTIZATION_VARIANCE"
    SENDINPUT_FAILED = "SENDINPUT_FAILED"
    TOPOLOGY_MUTATED = "TOPOLOGY_MUTATED"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    ABI_MISMATCH = "ABI_MISMATCH"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


# ----------------------------------------------------------------------
# 4. Geometry & Spatial Models
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Rect:
    """Inclusive-exclusive bounding rectangle in virtual desktop coordinates."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def contains_point(self, x: int, y: int) -> bool:
        """Returns True if (x, y) is strictly within [left, right) and [top, bottom)."""
        return self.left <= x < self.right and self.top <= y < self.bottom

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


@dataclass(frozen=True)
class VirtualDesktopMetrics:
    """Raw physical virtual desktop display metrics from Win32."""
    x_origin: int
    y_origin: int
    width: int
    height: int
    is_valid: bool
    timestamp_ns: int

    @property
    def right(self) -> int:
        return self.x_origin + self.width

    @property
    def bottom(self) -> int:
        return self.y_origin + self.height

    def contains_point(self, x: int, y: int) -> bool:
        return self.x_origin <= x < self.right and self.y_origin <= y < self.bottom


@dataclass(frozen=True)
class VirtualDesktopTopologyIdentity:
    """
    Stable display topology identity properties.
    Separates structural topology identity from observation timestamps.
    """
    origin_x: int
    origin_y: int
    width: int
    height: int
    monitor_count: int

    def matches(self, other: "VirtualDesktopTopologyIdentity") -> bool:
        return (
            self.origin_x == other.origin_x
            and self.origin_y == other.origin_y
            and self.width == other.width
            and self.height == other.height
            and self.monitor_count == other.monitor_count
        )


@dataclass(frozen=True)
class VirtualDesktopTopologyObservation:
    """Observation of display topology at a specific point in time."""
    identity: VirtualDesktopTopologyIdentity
    observed_at_ns: int


@dataclass(frozen=True)
class NormalizedCoordinate:
    """Win32 SendInput normalized 0..65535 coordinate structure."""
    norm_x: int
    norm_y: int
    raw_x: int
    raw_y: int
    is_clamped: bool
    was_out_of_bounds: bool


@dataclass(frozen=True)
class DpiAwarenessStatus:
    """Process DPI-awareness configuration status."""
    is_per_monitor_v2: bool
    raw_context: Optional[int]
    init_succeeded: bool
    error_code: int
    error_message: Optional[str] = None


# ----------------------------------------------------------------------
# 5. ABI & Foundation Models
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class AbiValidationResult:
    """Detailed runtime verification result for Win32 SendInput C ABI structures."""
    is_valid: bool
    status: AbiValidationStatus
    platform_system: str
    machine_arch: str
    pointer_width_bytes: int
    sizeof_mouseinput: int
    sizeof_input: int
    offset_dx: int
    offset_dwflags: int
    offset_dwextrainfo: int
    offset_input_union: int
    is_pointer_sized_extrainfo: bool
    error_message: Optional[str] = None
    validation_timestamp_ns: int = 0


@dataclass
class ActionCounter:
    """Audit counter confirming action tracking and non-invasiveness."""
    sendinput_calls: int = 0
    setcursorpos_calls: int = 0
    synthetic_down_calls: int = 0
    synthetic_up_calls: int = 0
    synthetic_move_calls: int = 0

    @property
    def total_actions(self) -> int:
        return (
            self.sendinput_calls
            + self.setcursorpos_calls
            + self.synthetic_down_calls
            + self.synthetic_up_calls
            + self.synthetic_move_calls
        )

    def record_sendinput(self, count: int = 1) -> None:
        self.sendinput_calls += count

    def record_down(self, count: int = 1) -> None:
        self.synthetic_down_calls += count

    def record_up(self, count: int = 1) -> None:
        self.synthetic_up_calls += count

    def record_move(self, count: int = 1) -> None:
        self.synthetic_move_calls += count


# ----------------------------------------------------------------------
# 6. Target & Validation Contracts
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class PointerTarget:
    """Raw unvalidated pointer action target request."""
    target_id: str
    native_hwnd: int
    process_id: int
    click_point: Tuple[int, int]
    expected_bounds: Rect
    source_generation_id: int
    source_snapshot_timestamp_ns: int
    confidence: str = "HIGH"
    class_name: Optional[str] = None
    require_foreground: bool = True
    validity_ttl_ms: float = 500.0


@dataclass(frozen=True)
class ValidatedPointerTarget:
    """Immutable, contract-verified pointer target approved for execution."""
    target_id: str
    native_hwnd: int
    process_id: int
    class_name: Optional[str]
    expected_bounds: Rect
    click_point: Tuple[int, int]
    source_generation_id: int
    source_snapshot_timestamp_ns: int
    confidence: str
    require_foreground: bool = True
    validity_ttl_ms: float = 500.0


@dataclass(frozen=True)
class PointerValidationResult:
    """Structured result of target or coordinate validation."""
    is_valid: bool
    status: TargetValidationStatus
    failure_reason: ValidationFailureReason
    diagnostic_message: Optional[str] = None
    metrics_snapshot: Optional[VirtualDesktopMetrics] = None
    validation_duration_us: float = 0.0


@dataclass(frozen=True)
class SnapshotValidationResult:
    """Result of adapting and verifying an external observation snapshot."""
    is_valid: bool
    failure_reason: ValidationFailureReason
    target: Optional[ValidatedPointerTarget] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class ActionCancellationState:
    """Atomic cancellation state record."""
    is_cancelled: bool
    reason: str
    timestamp_ns: int


@dataclass(frozen=True)
class MovementRequest:
    """Standalone coordinate movement request."""
    target_x: int
    target_y: int
    tolerance_px: int = 1
    cancellation_token: Optional[Any] = None
    timeout_ms: float = 100.0


@dataclass(frozen=True)
class NativeDispatchResult:
    """
    Exact return outcome from the single designated NativeDispatchGateway.
    Maintains strict separation between API injection acceptance and readback.
    """
    requested_packets: int
    accepted_packets: int
    win32_last_error: int
    duration_us: float
    dispatch_timestamp_ns: int


@dataclass(frozen=True)
class MovementExecutionResult:
    """Structured result of a cursor movement operation."""
    status: MovementExecutionStatus
    diagnostic_reason: MovementDiagnosticReason
    requested_pos: Tuple[int, int]
    observed_pos: Optional[Tuple[int, int]]
    delta_px: Optional[Tuple[int, int]]
    accepted_packets: int
    duration_us: float
    error_message: Optional[str] = None


@dataclass(frozen=True)
class PointerTelemetryRecord:
    """Structured telemetry record for operations."""
    operation_name: str
    timestamp_ns: int
    duration_us: float
    is_success: bool
    failure_reason: ValidationFailureReason = ValidationFailureReason.NONE
    details: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# 7. Phase 2C Button Ownership, State Machine & Lockout Models
# ----------------------------------------------------------------------

class ButtonTransactionState(str, Enum):
    """
    Authoritative state machine states for ORBIT synthetic button transactions.
    Primary invariant: ORBIT must never lose track of synthetic button states.
    """
    IDLE = "IDLE"
    DOWN_DISPATCH_PENDING = "DOWN_DISPATCH_PENDING"
    ORBIT_BUTTON_DOWN = "ORBIT_BUTTON_DOWN"
    UP_DISPATCH_PENDING = "UP_DISPATCH_PENDING"
    PARTIAL_OR_FAILED_DISPATCH = "PARTIAL_OR_FAILED_DISPATCH"
    SANITIZATION_PENDING = "SANITIZATION_PENDING"
    SANITIZED_RECOVERED = "SANITIZED_RECOVERED"
    UNRESOLVED_LOCKED = "UNRESOLVED_LOCKED"


class SyntheticButtonState(str, Enum):
    """Internal ORBIT-owned synthetic mouse button state."""
    RELEASED = "RELEASED"
    PRESSED = "PRESSED"
    INDETERMINATE = "INDETERMINATE"


class LockoutReason(str, Enum):
    """Diagnostic reason for entering UNRESOLVED_LOCKED fail-closed state."""
    NONE = "NONE"
    SANITIZATION_DISPATCH_FAILED = "SANITIZATION_DISPATCH_FAILED"
    INDETERMINATE_PARTIAL_STATE = "INDETERMINATE_PARTIAL_STATE"
    DISPATCH_EXCEPTION = "DISPATCH_EXCEPTION"
    MANUAL_LOCKOUT = "MANUAL_LOCKOUT"


class ButtonExecutionStatus(str, Enum):
    """Execution status for single button operations."""
    SUCCESS = "SUCCESS"
    REJECTED_LOCKED = "REJECTED_LOCKED"
    REJECTED_ALREADY_DOWN = "REJECTED_ALREADY_DOWN"
    REJECTED_ALREADY_UP = "REJECTED_ALREADY_UP"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"
    DISPATCH_ZERO = "DISPATCH_ZERO"
    DISPATCH_PARTIAL = "DISPATCH_PARTIAL"
    SANITIZED_AFTER_FAILURE = "SANITIZED_AFTER_FAILURE"
    UNRESOLVED_LOCKOUT = "UNRESOLVED_LOCKOUT"
    ABI_INVALID = "ABI_INVALID"


class ClickExecutionStatus(str, Enum):
    """Execution status for complete press-and-release click transactions."""
    SUCCESS = "SUCCESS"
    REJECTED_LOCKED = "REJECTED_LOCKED"
    CANCELLED_BEFORE_DOWN = "CANCELLED_BEFORE_DOWN"
    CANCELLED_BEFORE_UP = "CANCELLED_BEFORE_UP"
    DOWN_FAILED = "DOWN_FAILED"
    UP_FAILED_SANITIZED = "UP_FAILED_SANITIZED"
    UP_FAILED_LOCKED = "UP_FAILED_LOCKED"
    PARTIAL_DISPATCH_SANITIZED = "PARTIAL_DISPATCH_SANITIZED"
    PARTIAL_DISPATCH_LOCKED = "PARTIAL_DISPATCH_LOCKED"
    ABI_INVALID = "ABI_INVALID"


class ButtonDiagnosticReason(str, Enum):
    """Diagnostic reasons for button and click outcomes."""
    NONE = "NONE"
    ALREADY_IN_REQUESTED_STATE = "ALREADY_IN_REQUESTED_STATE"
    STATE_MACHINE_LOCKED = "STATE_MACHINE_LOCKED"
    SENDINPUT_FAILED = "SENDINPUT_FAILED"
    PARTIAL_DISPATCH = "PARTIAL_DISPATCH"
    SANITIZATION_FAILED = "SANITIZATION_FAILED"
    CANCELLED = "CANCELLED"
    ABI_MISMATCH = "ABI_MISMATCH"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ButtonExecutionResult:
    """Structured result of a single button DOWN or UP operation."""
    status: ButtonExecutionStatus
    button: PointerButton
    target_state: SyntheticButtonState
    resulting_state: SyntheticButtonState
    transaction_state: ButtonTransactionState
    accepted_packets: int
    duration_us: float
    diagnostic_reason: ButtonDiagnosticReason
    error_message: Optional[str] = None


@dataclass(frozen=True)
class ClickExecutionResult:
    """Structured result of a complete Click transaction."""
    status: ClickExecutionStatus
    button: PointerButton
    resulting_state: SyntheticButtonState
    transaction_state: ButtonTransactionState
    dwell_ms: float
    total_accepted_packets: int
    duration_us: float
    diagnostic_reason: ButtonDiagnosticReason
    error_message: Optional[str] = None


@dataclass(frozen=True)
class PointerStateSnapshot:
    """Immutable snapshot of the current pointer state machine state."""
    transaction_state: ButtonTransactionState
    left_button_state: SyntheticButtonState
    is_locked: bool
    lockout_reason: LockoutReason
    consecutive_sanitizations: int
    last_transition_timestamp_ns: int

