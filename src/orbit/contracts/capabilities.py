"""Abstract capability protocols and health models for ORBIT adapters."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field

from orbit.models.common import BoundingBox, Resolution, ScreenPoint


class CapabilityType(str, Enum):
    """Canonical identities for ORBIT capability subsystems."""

    OBSERVATION = "OBSERVATION"
    POINTER = "POINTER"
    KEYBOARD = "KEYBOARD"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    WORKSPACE = "WORKSPACE"
    SAFETY = "SAFETY"


class AdapterMode(str, Enum):
    """Execution mode of a capability adapter."""

    MOCK = "MOCK"
    PRODUCTION = "PRODUCTION"


class CapabilityLifecycleState(str, Enum):
    """Explicit lifecycle state of a capability adapter."""

    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    FAILED = "FAILED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class CapabilityHealthStatus(str, Enum):
    """Health status of an individual capability subsystem."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class CapabilityHealth(BaseModel):
    """Health diagnostic report from a capability adapter."""

    capability_name: str = Field(..., description="Canonical capability identifier")
    capability_type: Optional[CapabilityType] = Field(default=None, description="Typed capability classification")
    adapter_mode: AdapterMode = Field(default=AdapterMode.MOCK, description="Adapter execution mode")
    lifecycle_state: CapabilityLifecycleState = Field(
        default=CapabilityLifecycleState.CREATED,
        description="Current lifecycle state",
    )
    status: CapabilityHealthStatus = Field(default=CapabilityHealthStatus.HEALTHY)
    error_count: int = Field(default=0, ge=0)
    last_error: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class DisplayMetrics(BaseModel):
    """Physical and virtual coordinates of an attached display."""

    display_index: int = Field(0, ge=0)
    bounds: BoundingBox
    resolution: Resolution
    is_primary: bool = True


class FrameData(BaseModel):
    """Observation frame payload containing image buffer and metadata."""

    frame_id: str = Field(..., description="Unique frame identifier")
    timestamp_ns: int = Field(..., description="Monotonic timestamp in nanoseconds")
    resolution: Resolution
    raw_bytes: bytes = Field(..., description="Encoded image bytes or uncompressed raw buffer")
    format: str = Field(default="jpeg", description="Buffer format: jpeg, png, raw_bgra")
    roi: Optional[BoundingBox] = None


@runtime_checkable
class ObservationCapability(Protocol):
    """Protocol for screen capture and UI visual observation."""

    async def capture_screen(self, display_index: int = 0) -> FrameData:
        """Capture the current screen or region of interest."""
        ...

    async def get_display_metrics(self) -> List[DisplayMetrics]:
        """Query attached monitor topologies and DPI metrics."""
        ...

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        ...


@runtime_checkable
class PointerCapability(Protocol):
    """Protocol for mouse movement, clicking, and button transactions."""

    async def move_to(self, x: int, y: int, duration_ms: float = 0.0) -> bool:
        """Move cursor smoothly or instantly to physical coordinate."""
        ...

    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        count: int = 1,
        dwell_ms: float = 50.0,
    ) -> bool:
        """Perform a single or multi-click transaction at target coordinates."""
        ...


    async def press_down(self, button: str = "left") -> bool:
        """Hold down a mouse button."""
        ...

    async def release_up(self, button: str = "left") -> bool:
        """Release a held mouse button."""
        ...

    async def get_cursor_position(self) -> ScreenPoint:
        """Query current physical cursor position."""
        ...

    async def emergency_release_all(self) -> bool:
        """Release all held buttons fail-closed."""
        ...

    async def get_lockout_state(self) -> str:
        """Query hardware lockout state e.g. NORMAL, LOCKED."""
        ...

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        ...


@runtime_checkable
class KeyboardCapability(Protocol):
    """Protocol for typing, key combinations, and shortcut dispatch."""

    async def type_text(self, text: str, delay_ms: float = 2.0, target_hwnd: Optional[int] = None) -> bool:
        """Type a sequence of Unicode characters."""
        ...

    async def press_shortcut(self, combination: str, target_hwnd: Optional[int] = None) -> bool:
        """Execute a modifier key shortcut (e.g. 'ctrl+c', 'alt+tab')."""
        ...

    async def press_key(self, key_code: str) -> bool:
        """Press down a specific virtual key."""
        ...

    async def release_key(self, key_code: str) -> bool:
        """Release a specific virtual key."""
        ...

    async def emergency_release_all(self) -> bool:
        """Release all held keys fail-closed."""
        ...

    async def get_lockout_state(self) -> str:
        """Query keyboard lockout state e.g. NORMAL, UNRESOLVED_LOCKED."""
        ...

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        ...



@runtime_checkable
class HumanTakeoverCapability(Protocol):
    """Protocol for human input preemption detection."""

    async def start_monitoring(self, on_takeover_detected: Callable[[], None]) -> bool:
        """Start low-level input hooks and register takeover callback."""
        ...

    async def stop_monitoring(self) -> bool:
        """Stop input hooks."""
        ...

    async def is_takeover_active(self) -> bool:
        """Query whether human takeover is actively preempting."""
        ...

    async def reset_takeover_state(self) -> bool:
        """Clear takeover state and return control to agent."""
        ...

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        ...


@runtime_checkable
class WorkspaceCapability(Protocol):
    """Protocol for Windows desktop work area and AppBar management."""

    async def register_appbar(self, edge: str, size: int) -> bool:
        """Reserve screen edge for ORBIT window."""
        ...

    async def unregister_appbar(self) -> bool:
        """Restore standard desktop work area."""
        ...

    async def get_work_area(self) -> BoundingBox:
        """Query available desktop work area."""
        ...

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        ...

    def get_desktop_generation(self) -> int:
        """Query authoritative active desktop generation ID."""
        ...

    def validate_coordinate(
        self,
        x: int,
        y: int,
        expected_generation: Optional[int] = None,
    ) -> Any:
        """Validate target coordinate against active workspace geometry and generation parity."""
        ...



@runtime_checkable
class EmergencySafetyCoordinator(Protocol):
    """Protocol for global fail-safe emergency shutdowns."""

    async def emergency_stop_all(self) -> bool:
        """Halt all active actions and sanitize physical hardware states."""
        ...

    async def is_safe_state(self) -> bool:
        """Verify all hardware locks and buttons are in known resting states."""
        ...
