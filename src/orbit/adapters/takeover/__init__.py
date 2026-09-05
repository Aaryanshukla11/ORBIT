"""ORBIT Production Human Takeover Capability package."""

from orbit.adapters.takeover.adapter import ProductionHumanTakeoverAdapter
from orbit.adapters.takeover.classifier import (
    InputDevice,
    InputEventType,
    InputSource,
    TakeoverClassifier,
    TakeoverEvidence,
)
from orbit.adapters.takeover.hook import NativeHookInstallationError, NativeInputMonitor
from orbit.adapters.takeover.safety import (
    KBDLLHOOKSTRUCT,
    MSLLHOOKSTRUCT,
    ORBIT_EXTRA_INFO_SIGNATURE,
    POINT,
    TakeoverAbiGate,
)
from orbit.adapters.takeover.state import (
    TakeoverState,
    TakeoverStateManager,
    TakeoverStateTransitionError,
)
from orbit.adapters.takeover.telemetry import (
    TakeoverTelemetryLogger,
    TakeoverTelemetrySnapshot,
)

__all__ = [
    "ProductionHumanTakeoverAdapter",
    "NativeInputMonitor",
    "NativeHookInstallationError",
    "TakeoverClassifier",
    "TakeoverEvidence",
    "InputSource",
    "InputDevice",
    "InputEventType",
    "TakeoverState",
    "TakeoverStateManager",
    "TakeoverStateTransitionError",
    "TakeoverTelemetryLogger",
    "TakeoverTelemetrySnapshot",
    "TakeoverAbiGate",
    "ORBIT_EXTRA_INFO_SIGNATURE",
    "MSLLHOOKSTRUCT",
    "KBDLLHOOKSTRUCT",
    "POINT",
]
