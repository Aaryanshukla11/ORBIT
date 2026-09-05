"""Production Pointer capability adapter package for ORBIT."""

from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.pointer.buttons import (
    ButtonExecutionStatus,
    ButtonTransactionExecutor,
    ButtonTransactionResult,
    ClickExecutionStatus,
    ClickTransactionResult,
    SanitizationResult,
)
from orbit.adapters.pointer.health import ActionCounter, PointerHealthTracker
from orbit.adapters.pointer.movement import (
    MovementDiagnosticReason,
    MovementEvidenceLevel,
    MovementExecutor,
    MovementResult,
    MovementStatus,
    NativeDispatchGateway,
    get_live_cursor_position,
    normalize_to_sendinput,
)
from orbit.adapters.pointer.safety import (
    AbiGate,
    AbiValidationResult,
    AbiValidationStatus,
    MouseButton,
    VirtualDesktopMetrics,
    VirtualDesktopTopologyIdentity,
    ensure_thread_input_desktop,
    query_topology_identity,
    query_virtual_desktop_metrics,
    query_windows_observable_button_pressed,
    validate_runtime_abi,
)
from orbit.adapters.pointer.state import (
    LockoutReason,
    PointerStateManager,
    PointerStateSnapshot,
    PointerTransactionState,
    SyntheticButtonState,
)

__all__ = [
    "ProductionPointerAdapter",
    "MovementExecutor",
    "MovementResult",
    "MovementStatus",
    "MovementEvidenceLevel",
    "MovementDiagnosticReason",
    "NativeDispatchGateway",
    "ButtonTransactionExecutor",
    "ButtonExecutionStatus",
    "ClickExecutionStatus",
    "ButtonTransactionResult",
    "ClickTransactionResult",
    "SanitizationResult",
    "PointerStateManager",
    "PointerTransactionState",
    "SyntheticButtonState",
    "LockoutReason",
    "PointerStateSnapshot",
    "ActionCounter",
    "PointerHealthTracker",
    "AbiGate",
    "AbiValidationResult",
    "AbiValidationStatus",
    "VirtualDesktopMetrics",
    "VirtualDesktopTopologyIdentity",
    "MouseButton",
    "ensure_thread_input_desktop",
    "query_virtual_desktop_metrics",
    "query_topology_identity",
    "validate_runtime_abi",
    "query_windows_observable_button_pressed",
]
