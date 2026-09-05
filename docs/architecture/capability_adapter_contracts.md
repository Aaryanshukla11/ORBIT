# ORBIT Capability Adapter Contracts & Boundary Interfaces Specification
**Document Version:** 1.0.0  
**Package Namespace:** `orbit.contracts` / `orbit.adapters`  
**Status:** APPROVED ADAPTER CONTRACTS  

---

## 1. Design Philosophy & Zero-Coupling Invariants

To maintain clean architectural boundaries and preserve the validated, frozen state of prototypes:

1. **Zero Prototype Modification**: Prototypes A, B, C, D, and E remain untouched R&D baselines.
2. **Abstract Protocol Isolation**: All ORBIT Core Runtime modules interact exclusively with abstract protocols defined in `orbit.contracts`.
3. **Single Adapter per Prototype**: Each capability prototype is wrapped by exactly one authoritative adapter residing in `orbit.adapters`.
4. **Data Model Translation**: Adapters ingest clean `orbit.contracts` data structures and translate them to/from prototype-internal formats.
5. **Thread & Process Isolation**: Adapters isolate prototype-specific threading models (e.g., Win32 message pumps, COM STA/MTA apartments) from the main AsyncIO event loop.

---

## 2. Core Capability Protocol Interfaces

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           orbit.contracts                               │
│                                                                         │
│   ┌───────────────────────────┐       ┌─────────────────────────────┐   │
│   │    WorkspaceCapability    │       │   HumanTakeoverCapability   │   │
│   └─────────────┬─────────────┘       └──────────────┬──────────────┘   │
│                 │                                    │                  │
│   ┌─────────────┴─────────────┐       ┌──────────────┴──────────────┐   │
│   │    KeyboardCapability     │       │    ObservationCapability    │   │
│   └─────────────┬─────────────┘       └──────────────┬──────────────┘   │
│                 │                                    │                  │
│                 └─────────────┬──────────────────────┘                  │
│                               ▼                                         │
│                   ┌───────────────────────┐                             │
│                   │   PointerCapability   │                             │
│                   └───────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 2.1 `WorkspaceCapability` (Prototype A Adapter)

```python
from typing import Protocol, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class DockEdge(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    BOTTOM = "BOTTOM"

@dataclass(frozen=True)
class WorkAreaRect:
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int

@dataclass(frozen=True)
class MonitorMetrics:
    monitor_index: int
    is_primary: bool
    workarea: WorkAreaRect
    full_bounds: WorkAreaRect
    dpi_scale: float

@dataclass(frozen=True)
class WorkspaceReservationResult:
    is_docked: bool
    dock_edge: DockEdge
    docked_hwnd: int
    reserved_rect: WorkAreaRect
    available_workarea: WorkAreaRect
    error_message: Optional[str] = None

class WorkspaceCapability(Protocol):
    """Authoritative boundary interface for Windows AppBar workspace management."""

    async def dock(
        self,
        hwnd: int,
        edge: DockEdge = DockEdge.RIGHT,
        desired_width_px: int = 440,
        monitor_index: int = 0,
    ) -> WorkspaceReservationResult:
        """Docks the specified window HWND as an AppBar, modifying the desktop work area."""
        ...

    async def undock(self) -> bool:
        """Undocks the active AppBar and restores original desktop work area."""
        ...

    async def get_current_workarea(self, monitor_index: int = 0) -> WorkAreaRect:
        """Retrieves the live desktop work area."""
        ...

    async def enumerate_monitors(self) -> List[MonitorMetrics]:
        """Enumerates active monitors, display geometry, and DPI scaling factors."""
        ...

    async def ensure_watchdog_active(self, parent_pid: int) -> bool:
        """Spawns or verifies the detached crash recovery watchdog process."""
        ...
```

---

### 2.2 `HumanTakeoverCapability` (Prototype B Adapter)

```python
from typing import Protocol, Callable, List, Optional
from dataclasses import dataclass
from enum import Enum

class TakeoverState(str, Enum):
    IDLE = "IDLE"
    EXECUTING = "EXECUTING"
    SUSPECTED_TAKEOVER = "SUSPECTED_TAKEOVER"
    PAUSED_BY_USER = "PAUSED_BY_USER"

@dataclass(frozen=True)
class TrajectoryCorridor:
    trajectory_id: str
    points: List[Tuple[int, int, int]]  # (x, y, timestamp_ns)
    allowed_corridor_radius_px: float
    max_expected_velocity_px_ms: float

@dataclass(frozen=True)
class TakeoverEvent:
    timestamp_ns: int
    state: TakeoverState
    trigger_reason: str
    detected_pos: Tuple[int, int]
    detection_latency_us: float

class HumanTakeoverCapability(Protocol):
    """Authoritative boundary interface for low-level input monitoring and takeover detection."""

    async def start_monitoring(
        self,
        on_takeover_callback: Callable[[TakeoverEvent], None],
    ) -> bool:
        """Initializes low-level hooks on a dedicated background message pump thread."""
        ...

    async def stop_monitoring(self) -> bool:
        """Unhooks low-level mouse/keyboard hooks and terminates background thread."""
        ...

    async def declare_expected_trajectory(self, corridor: TrajectoryCorridor) -> None:
        """Informs the takeover detector of an imminent AI-controlled mouse trajectory."""
        ...

    async def clear_expected_trajectory(self) -> None:
        """Clears active expected trajectory upon movement completion."""
        ...

    async def get_takeover_state(self) -> TakeoverState:
        """Queries current human takeover state."""
        ...
```

---

### 2.3 `KeyboardCapability` (Prototype C Adapter)

```python
from typing import Protocol, List, Optional
from dataclasses import dataclass
from enum import Enum

class KeyboardExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FOCUS_LOST = "FOCUS_LOST"
    CANCELLED = "CANCELLED"
    RESTRICTED_SHORTCUT = "RESTRICTED_SHORTCUT"
    DISPATCH_FAILED = "DISPATCH_FAILED"

@dataclass(frozen=True)
class KeyboardExecutionResult:
    status: KeyboardExecutionStatus
    typed_length: int
    accepted_packets: int
    duration_us: float
    error_message: Optional[str] = None

class KeyboardCapability(Protocol):
    """Authoritative boundary interface for safe keyboard typing and shortcut dispatch."""

    async def type_text(
        self,
        text: str,
        target_hwnd: Optional[int] = None,
        cancellation_token: Optional[object] = None,
    ) -> KeyboardExecutionResult:
        """Types Unicode or ASCII text into the target window with pre-dispatch focus verification."""
        ...

    async def send_shortcut(
        self,
        chord: List[str],  # e.g. ["CTRL", "SHIFT", "P"]
        target_hwnd: Optional[int] = None,
        cancellation_token: Optional[object] = None,
    ) -> KeyboardExecutionResult:
        """Dispatches multi-key shortcut sequences validated against ShortcutPolicy."""
        ...

    async def emergency_sanitize(self) -> bool:
        """Releases any active synthetic modifiers or keys currently held down."""
        ...
```

---

### 2.4 `ObservationCapability` (Prototype D Adapter)

```python
from typing import Protocol, List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

class TargetConfidence(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
    VISUAL_FALLBACK = "VISUAL_FALLBACK"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"

@dataclass(frozen=True)
class UIElementNode:
    element_id: str
    name: str
    control_type: str
    bounding_box: Tuple[int, int, int, int]  # left, top, right, bottom
    confidence: TargetConfidence
    native_hwnd: int
    process_id: int
    source_channels: List[str]

@dataclass(frozen=True)
class FusedObservationSnapshot:
    snapshot_id: str
    generation_id: int
    timestamp_ns: int
    foreground_hwnd: int
    foreground_title: str
    foreground_pid: int
    virtual_desktop_bounds: Tuple[int, int, int, int]
    elements: List[UIElementNode]
    raw_frame_bytes: Optional[bytes] = None

class ObservationCapability(Protocol):
    """Authoritative boundary interface for multi-source screen observation and evidence fusion."""

    async def capture_snapshot(
        self,
        target_hwnd: Optional[int] = None,
        include_visual_buffer: bool = True,
        max_timeout_ms: float = 2000.0,
    ) -> FusedObservationSnapshot:
        """Captures fused accessibility (UIA/MSAA/Win32) and visual/OCR observation snapshot."""
        ...

    async def locate_element_by_id(
        self,
        element_id: str,
        snapshot: FusedObservationSnapshot,
    ) -> Optional[UIElementNode]:
        """Finds a specific UI element within an observation snapshot."""
        ...

    async def check_provider_health(self) -> Dict[str, Any]:
        """Returns health status and circuit-breaker states of observation providers."""
        ...
```

---

### 2.5 `PointerCapability` (Prototype E Adapter)

```python
from typing import Protocol, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class PointerActionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    MOVEMENT_VERIFIED = "MOVEMENT_VERIFIED"
    TARGET_REJECTED = "TARGET_REJECTED"
    CANCELLED = "CANCELLED"
    LOCKED = "LOCKED"
    FAILED = "FAILED"

@dataclass(frozen=True)
class PointerMovementResult:
    status: PointerActionStatus
    requested_pos: Tuple[int, int]
    observed_pos: Optional[Tuple[int, int]]
    delta_px: Optional[Tuple[int, int]]
    accepted_packets: int
    duration_us: float
    error_message: Optional[str] = None

@dataclass(frozen=True)
class PointerClickResult:
    status: PointerActionStatus
    target_pos: Tuple[int, int]
    dwell_ms: float
    total_accepted_packets: int
    duration_us: float
    error_message: Optional[str] = None

class PointerCapability(Protocol):
    """Authoritative boundary interface for safe pointer movement, clicks, and lockout."""

    async def move_to(
        self,
        target_x: int,
        target_y: int,
        tolerance_px: int = 1,
        cancellation_token: Optional[object] = None,
    ) -> PointerMovementResult:
        """Executes 12-step deterministic absolute cursor movement via single gateway."""
        ...

    async def click(
        self,
        target_x: int,
        target_y: int,
        dwell_ms: float = 10.0,
        cancellation_token: Optional[object] = None,
    ) -> PointerClickResult:
        """Executes combined move and press-and-release click with pre/post verification."""
        ...

    async def emergency_sanitize(self) -> bool:
        """Releases any active synthetic mouse buttons."""
        ...

    async def recover_manual_lockout(self, confirmation_token: str) -> bool:
        """Resets the pointer state machine from UNRESOLVED_LOCKED fail-closed state."""
        ...
```
