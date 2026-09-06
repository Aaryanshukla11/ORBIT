"""Native Win32 AppBar Driver coordinating shell edge reservation and positioning."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.adapters.workspace.abi import (
    ABE_BOTTOM,
    ABE_LEFT,
    ABE_RIGHT,
    ABE_TOP,
    ABM_NEW,
    ABM_QUERYPOS,
    ABM_REMOVE,
    ABM_SETPOS,
    ABN_FULLSCREENAPP,
    ABN_POSCHANGED,
    ABN_STATECHANGE,
    ABN_WINDOWARRANGE,
    APPBARDATA,
    IS_WINDOWS,
    RECT,
    WM_APPBAR_CALLBACK,
)
from orbit.adapters.workspace.state import WorkspaceStateManager
from orbit.adapters.workspace.telemetry import WorkspaceTelemetryRecorder
from orbit.adapters.workspace.types import DockEdge, WorkspaceState
from orbit.adapters.workspace.window import NativeWorkspaceWindow
from orbit.models.common import BoundingBox

logger = logging.getLogger(__name__)


class AppBarNotificationRecord(BaseModel):
    """Notification received from Windows Shell via WM_APPBAR_CALLBACK."""

    notification_code: int
    notification_name: str
    timestamp_ns: int = Field(default_factory=time.perf_counter_ns)
    lparam: int = 0


class AppBarOperationResult(BaseModel):
    """Structured result of a native AppBar registration, positioning, or removal operation."""

    operation: str = Field(..., description="Operation performed: REGISTER, QUERYPOS, SETPOS, REMOVE")
    edge: DockEdge = Field(default=DockEdge.NONE, description="Target dock edge")
    requested_rect: BoundingBox = Field(..., description="Original requested bounding box")
    negotiated_rect: Optional[BoundingBox] = Field(default=None, description="Bounding box proposed by shell")
    final_rect: Optional[BoundingBox] = Field(default=None, description="Final committed bounding box")
    success: bool = Field(default=False, description="True if operation succeeded completely")
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    rollback_executed: bool = Field(default=False, description="True if a transactional rollback was executed")
    rollback_success: bool = Field(default=False, description="True if the rollback cleaned up completely")


class Win32ShellGateway:
    """Platform gateway dispatching Shell32 SHAppBarMessage with explicit AMD64 ABI."""

    def __init__(self) -> None:
        if IS_WINDOWS:
            self._shell32 = ctypes.windll.shell32
            self._kernel32 = ctypes.windll.kernel32

            # Configure explicit 64-bit AMD64 signatures
            self._shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
            self._shell32.SHAppBarMessage.restype = ctypes.c_uint64

            self._kernel32.GetLastError.argtypes = []
            self._kernel32.GetLastError.restype = wintypes.DWORD
        else:
            self._shell32 = None
            self._kernel32 = None

    def sh_appbar_message(self, message: int, abd: APPBARDATA) -> int:
        if not IS_WINDOWS or self._shell32 is None:
            return 0
        return int(self._shell32.SHAppBarMessage(message, ctypes.byref(abd)))

    def get_last_error(self) -> int:
        if not IS_WINDOWS or self._kernel32 is None:
            return 0
        return int(self._kernel32.GetLastError())


class NativeAppBarDriver:
    """Production driver managing the Win32 AppBar registration lifecycle with transactional rollback."""

    def __init__(
        self,
        window: Optional[NativeWorkspaceWindow] = None,
        state_manager: Optional[WorkspaceStateManager] = None,
        telemetry_recorder: Optional[WorkspaceTelemetryRecorder] = None,
        shell_gateway: Optional[Win32ShellGateway] = None,
    ) -> None:
        self._window = window or NativeWorkspaceWindow()
        self._state_manager = state_manager or WorkspaceStateManager()
        self._telemetry_recorder = telemetry_recorder or WorkspaceTelemetryRecorder()
        self._shell_gateway = shell_gateway or Win32ShellGateway()

        self._is_registered: bool = False
        self._current_edge: DockEdge = DockEdge.NONE
        self._current_rect: RECT = RECT()
        self._notifications: List[AppBarNotificationRecord] = []

        # Wire notification listener
        self._window.add_notification_listener(self._on_appbar_notification)

    @property
    def window(self) -> NativeWorkspaceWindow:
        return self._window

    @property
    def state_manager(self) -> WorkspaceStateManager:
        return self._state_manager

    @property
    def telemetry_recorder(self) -> WorkspaceTelemetryRecorder:
        return self._telemetry_recorder

    @property
    def is_registered(self) -> bool:
        return self._is_registered

    @property
    def current_edge(self) -> DockEdge:
        return self._current_edge

    @property
    def dock_edge(self) -> DockEdge:
        return self._current_edge

    @property
    def current_rect(self) -> RECT:
        return self._current_rect

    @property
    def docked_bounds(self) -> Optional[BoundingBox]:
        return self._current_rect.to_bounding_box() if self._is_registered else None

    def _map_edge_to_u_edge(self, edge: DockEdge) -> int:
        mapping = {
            DockEdge.LEFT: ABE_LEFT,
            DockEdge.TOP: ABE_TOP,
            DockEdge.RIGHT: ABE_RIGHT,
            DockEdge.BOTTOM: ABE_BOTTOM,
        }
        if edge not in mapping:
            raise ValueError(f"Unsupported DockEdge for native AppBar: {edge}")
        return mapping[edge]

    def _on_appbar_notification(self, code: int, lparam: int) -> None:
        name_map = {
            ABN_STATECHANGE: "ABN_STATECHANGE",
            ABN_POSCHANGED: "ABN_POSCHANGED",
            ABN_FULLSCREENAPP: "ABN_FULLSCREENAPP",
            ABN_WINDOWARRANGE: "ABN_WINDOWARRANGE",
        }
        notif_name = name_map.get(code, f"ABN_UNKNOWN_{code}")
        record = AppBarNotificationRecord(
            notification_code=code,
            notification_name=notif_name,
            timestamp_ns=time.perf_counter_ns(),
            lparam=lparam,
        )
        self._notifications.append(record)
        if len(self._notifications) > 100:
            self._notifications.pop(0)

        logger.info("Received AppBar notification: %s (code=%d, lparam=%d)", notif_name, code, lparam)

    def register_and_dock(
        self,
        edge: DockEdge,
        target_bounds: BoundingBox,
        monitor_bounds: Optional[BoundingBox] = None,
    ) -> AppBarOperationResult:
        """Register the window as an AppBar and position it transactionally at the target edge."""
        t_start = time.perf_counter()
        req_bbox = target_bounds

        if edge == DockEdge.NONE:
            return AppBarOperationResult(
                operation="REGISTER",
                edge=edge,
                requested_rect=req_bbox,
                success=False,
                error_message="Cannot dock to DockEdge.NONE",
            )

        # 1. Ensure Window exists
        try:
            if not self._window.is_created:
                self._window.create(bounds=req_bbox, topmost=True, visible=True)
        except Exception as ex:
            logger.error("Failed to create native window for AppBar: %s", ex)
            if self._state_manager.can_transition_to(WorkspaceState.FAILED):
                self._state_manager.transition_to(WorkspaceState.FAILED, reason=str(ex))
            self._telemetry_recorder.record_error(f"Window creation failed: {ex}")
            return AppBarOperationResult(
                operation="REGISTER",
                edge=edge,
                requested_rect=req_bbox,
                success=False,
                error_message=str(ex),
            )

        # 2. State transition to REGISTERING
        if self._state_manager.can_transition_to(WorkspaceState.REGISTERING):
            self._state_manager.transition_to(WorkspaceState.REGISTERING, reason=f"Docking to {edge.value}")

        u_edge = self._map_edge_to_u_edge(edge)
        requested_rc = RECT(
            left=req_bbox.left,
            top=req_bbox.top,
            right=req_bbox.left + req_bbox.width,
            bottom=req_bbox.top + req_bbox.height,
        )

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self._window.hwnd
        abd.uCallbackMessage = self._window.callback_message
        abd.uEdge = u_edge
        abd.rc = requested_rc
        abd.lParam = 0

        # 3. ABM_NEW registration
        if not self._is_registered:
            try:
                self._shell_gateway.sh_appbar_message(ABM_NEW, abd)
                self._is_registered = True
            except Exception as ex:
                logger.error("SHAppBarMessage(ABM_NEW) raised exception: %s", ex)
                rollback_ok = self._window.destroy()
                if self._state_manager.can_transition_to(WorkspaceState.FAILED):
                    self._state_manager.transition_to(WorkspaceState.FAILED, reason=f"ABM_NEW exception: {ex}")
                self._telemetry_recorder.record_error(f"ABM_NEW failed: {ex}")
                return AppBarOperationResult(
                    operation="REGISTER",
                    edge=edge,
                    requested_rect=req_bbox,
                    success=False,
                    error_message=str(ex),
                    rollback_executed=True,
                    rollback_success=rollback_ok,
                )

        # 4. ABM_QUERYPOS negotiation
        self._shell_gateway.sh_appbar_message(ABM_QUERYPOS, abd)
        query_rect = abd.rc.to_bounding_box()

        # 5. Geometry Re-clamping (preserve target edge width/height allocation)
        if edge in {DockEdge.LEFT, DockEdge.RIGHT}:
            if edge == DockEdge.RIGHT:
                abd.rc.left = abd.rc.right - req_bbox.width
            elif edge == DockEdge.LEFT:
                abd.rc.right = abd.rc.left + req_bbox.width
        elif edge in {DockEdge.TOP, DockEdge.BOTTOM}:
            if edge == DockEdge.BOTTOM:
                abd.rc.top = abd.rc.bottom - req_bbox.height
            elif edge == DockEdge.TOP:
                abd.rc.bottom = abd.rc.top + req_bbox.height

        # 6. ABM_SETPOS commit
        self._shell_gateway.sh_appbar_message(ABM_SETPOS, abd)
        final_rect_bbox = abd.rc.to_bounding_box()

        # 7. Reposition the native window
        pos_ok = self._window.set_position(abd.rc, topmost=True, activate=False)
        if not pos_ok:
            logger.error("Failed to position native window after ABM_SETPOS")
            # Transactional Rollback: Unregister and destroy window
            rollback_res = self.unregister_and_release(destroy_window=True)
            if self._state_manager.can_transition_to(WorkspaceState.FAILED):
                self._state_manager.transition_to(WorkspaceState.FAILED, reason="SetWindowPos failed during dock")
            self._telemetry_recorder.record_error("SetWindowPos failed during dock")
            return AppBarOperationResult(
                operation="SETPOS",
                edge=edge,
                requested_rect=req_bbox,
                negotiated_rect=query_rect,
                final_rect=final_rect_bbox,
                success=False,
                error_message="SetWindowPos failed to reposition window",
                rollback_executed=True,
                rollback_success=rollback_res.success,
            )

        self._current_edge = edge
        self._current_rect = abd.rc

        # 8. State transition to DOCKED (increments desktop_generation_id)
        if self._state_manager.can_transition_to(WorkspaceState.DOCKED):
            self._state_manager.transition_to(WorkspaceState.DOCKED, reason=f"Docked {edge.value}")

        duration_ms = (time.perf_counter() - t_start) * 1000.0
        self._telemetry_recorder.record_transition(
            from_state=WorkspaceState.REGISTERING,
            to_state=WorkspaceState.DOCKED,
            duration_ms=duration_ms,
            reason=f"Docked {edge.value}",
            desktop_generation_id=self._state_manager.desktop_generation_id,
            topology_generation_id=self._state_manager.topology_generation_id,
            dock_edge=edge,
        )

        logger.info(
            "AppBar successfully docked: edge=%s, rect=%s in %.2f ms",
            edge.value,
            final_rect_bbox,
            duration_ms,
        )

        return AppBarOperationResult(
            operation="REGISTER",
            edge=edge,
            requested_rect=req_bbox,
            negotiated_rect=query_rect,
            final_rect=final_rect_bbox,
            success=True,
        )

    def unregister_and_release(self, destroy_window: bool = False) -> AppBarOperationResult:
        """Unregister the AppBar from the Windows Shell and transition to READY_FLOATING."""
        t_start = time.perf_counter()
        curr_bbox = self._current_rect.to_bounding_box()

        if not self._is_registered:
            if destroy_window and self._window.is_created:
                self._window.destroy()
            return AppBarOperationResult(
                operation="REMOVE",
                edge=self._current_edge,
                requested_rect=curr_bbox,
                final_rect=curr_bbox,
                success=True,
            )

        # Transition to RELEASING
        if self._state_manager.can_transition_to(WorkspaceState.RELEASING):
            self._state_manager.transition_to(WorkspaceState.RELEASING, reason="Unregistering AppBar")

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self._window.hwnd

        try:
            self._shell_gateway.sh_appbar_message(ABM_REMOVE, abd)
        except Exception as ex:
            logger.error("SHAppBarMessage(ABM_REMOVE) exception: %s", ex)
            if self._state_manager.can_transition_to(WorkspaceState.DEGRADED):
                self._state_manager.transition_to(WorkspaceState.DEGRADED, reason=f"ABM_REMOVE error: {ex}")
            return AppBarOperationResult(
                operation="REMOVE",
                edge=self._current_edge,
                requested_rect=curr_bbox,
                success=False,
                error_message=str(ex),
            )

        self._is_registered = False
        self._current_edge = DockEdge.NONE

        if destroy_window:
            self._window.destroy()

        # Transition to READY_FLOATING (increments desktop_generation_id)
        if self._state_manager.can_transition_to(WorkspaceState.READY_FLOATING):
            self._state_manager.transition_to(WorkspaceState.READY_FLOATING, reason="Unregistration complete")

        duration_ms = (time.perf_counter() - t_start) * 1000.0
        self._telemetry_recorder.record_transition(
            from_state=WorkspaceState.RELEASING,
            to_state=WorkspaceState.READY_FLOATING,
            duration_ms=duration_ms,
            reason="Unregistration complete",
            desktop_generation_id=self._state_manager.desktop_generation_id,
            topology_generation_id=self._state_manager.topology_generation_id,
            dock_edge=DockEdge.NONE,
        )

        logger.info("AppBar unmounted and restored in %.2f ms", duration_ms)

        return AppBarOperationResult(
            operation="REMOVE",
            edge=DockEdge.NONE,
            requested_rect=curr_bbox,
            final_rect=curr_bbox,
            success=True,
        )

    def get_recorded_notifications(self) -> List[AppBarNotificationRecord]:
        return list(self._notifications)
