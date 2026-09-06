"""ORBIT Production Workspace Capability Package."""

from __future__ import annotations

from orbit.adapters.workspace.types import (
    DisplayMonitorInfo,
    DockEdge,
    WorkspaceGeometry,
    WorkspaceHealthDetails,
    WorkspaceState,
)
from orbit.adapters.workspace.abi import (
    APPBARDATA,
    MONITORINFOEXW,
    RECT,
    validate_workspace_abi,
)
from orbit.adapters.workspace.state import (
    WorkspaceStateManager,
    WorkspaceStateTransitionError,
)
from orbit.adapters.workspace.telemetry import (
    WorkspaceOperationMetrics,
    WorkspaceTelemetryRecorder,
    WorkspaceTelemetrySnapshot,
    WorkspaceTransitionRecord,
)
from orbit.adapters.workspace.window import (
    NativeWorkspaceWindow,
    Win32WindowGateway,
)
from orbit.adapters.workspace.appbar import (
    AppBarNotificationRecord,
    AppBarOperationResult,
    NativeAppBarDriver,
    Win32ShellGateway,
)
from orbit.adapters.workspace.geometry import (
    CoordinateValidationResult,
    CoordinateValidationStatus,
    Win32TopologyGateway,
    WorkspaceGeometryCoordinator,
)
from orbit.adapters.workspace.watchdog import (
    WatchdogNativeGateway,
    WorkspaceFailureCategory,
    WorkspaceHealthStatus,
    WorkspaceProbeResult,
    WorkspaceWatchdog,
    WorkspaceWatchdogPolicy,
)
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter

__all__ = [
    "DisplayMonitorInfo",
    "DockEdge",
    "WorkspaceGeometry",
    "WorkspaceHealthDetails",
    "WorkspaceState",
    "APPBARDATA",
    "MONITORINFOEXW",
    "RECT",
    "validate_workspace_abi",
    "WorkspaceStateManager",
    "WorkspaceStateTransitionError",
    "WorkspaceOperationMetrics",
    "WorkspaceTelemetryRecorder",
    "WorkspaceTelemetrySnapshot",
    "WorkspaceTransitionRecord",
    "NativeWorkspaceWindow",
    "Win32WindowGateway",
    "NativeAppBarDriver",
    "Win32ShellGateway",
    "AppBarOperationResult",
    "AppBarNotificationRecord",
    "CoordinateValidationResult",
    "CoordinateValidationStatus",
    "Win32TopologyGateway",
    "WorkspaceGeometryCoordinator",
    "WatchdogNativeGateway",
    "WorkspaceFailureCategory",
    "WorkspaceHealthStatus",
    "WorkspaceProbeResult",
    "WorkspaceWatchdog",
    "WorkspaceWatchdogPolicy",
    "ProductionWorkspaceAdapter",
]
