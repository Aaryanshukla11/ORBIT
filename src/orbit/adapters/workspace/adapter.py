"""Production Workspace Adapter integrating native AppBar management, geometry coordination, and watchdog resilience."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Callable, Dict, Optional

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityInitializationError,
    CapabilityUnavailableError,
    WorkspaceError,
)
from orbit.adapters.workspace.abi import validate_workspace_abi
from orbit.adapters.workspace.appbar import (
    AppBarOperationResult,
    NativeAppBarDriver,
)
from orbit.adapters.workspace.geometry import (
    CoordinateValidationResult,
    WorkspaceGeometryCoordinator,
)
from orbit.adapters.workspace.state import (
    WorkspaceStateManager,
)
from orbit.adapters.workspace.telemetry import (
    WorkspaceTelemetryRecorder,
)
from orbit.adapters.workspace.types import (
    DockEdge,
    WorkspaceGeometry,
    WorkspaceHealthDetails,
    WorkspaceState,
)
from orbit.adapters.workspace.watchdog import (
    WorkspaceFailureCategory,
    WorkspaceHealthStatus,
    WorkspaceProbeResult,
    WorkspaceWatchdog,
    WorkspaceWatchdogPolicy,
)
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
    WorkspaceCapability,
)
from orbit.models.common import BoundingBox

logger = logging.getLogger(__name__)


class ProductionWorkspaceAdapter(BaseCapabilityAdapter, WorkspaceCapability):
    """Production workspace capability adapter coordinating native AppBar, display topology, and resilience watchdog."""

    def __init__(
        self,
        enable_live_appbar: bool = True,
        default_dock_edge: DockEdge = DockEdge.RIGHT,
        default_reservation_px: int = 480,
        auto_start_watchdog: bool = True,
        watchdog_policy: Optional[WorkspaceWatchdogPolicy] = None,
        is_takeover_active_fn: Optional[Callable[[], bool]] = None,
        # Dependency Injection Overrides for Testing
        state_manager: Optional[WorkspaceStateManager] = None,
        geometry_coordinator: Optional[WorkspaceGeometryCoordinator] = None,
        appbar_driver: Optional[NativeAppBarDriver] = None,
        watchdog: Optional[WorkspaceWatchdog] = None,
        telemetry: Optional[WorkspaceTelemetryRecorder] = None,
    ) -> None:
        super().__init__(
            capability_name="ProductionWorkspace",
            capability_type=CapabilityType.WORKSPACE,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self._enable_live_appbar = enable_live_appbar
        self.default_dock_edge = default_dock_edge
        self.default_reservation_px = default_reservation_px
        self.auto_start_watchdog = auto_start_watchdog
        self.watchdog_policy = watchdog_policy or WorkspaceWatchdogPolicy()
        self.is_takeover_active_fn = is_takeover_active_fn

        # Core Subsystems
        self.state_manager = state_manager or WorkspaceStateManager()
        self.telemetry = telemetry or WorkspaceTelemetryRecorder()
        self.geometry_coordinator = geometry_coordinator or WorkspaceGeometryCoordinator(
            state_manager=self.state_manager,
            telemetry=self.telemetry,
        )
        self.appbar_driver = appbar_driver or NativeAppBarDriver()

        def _check_takeover() -> bool:
            if self.is_takeover_active_fn:
                try:
                    return bool(self.is_takeover_active_fn())
                except Exception:
                    return False
            return False

        self.watchdog = watchdog or WorkspaceWatchdog(
            state_manager=self.state_manager,
            geometry_coordinator=self.geometry_coordinator,
            appbar_driver=self.appbar_driver,
            policy=self.watchdog_policy,
            is_takeover_active_fn=_check_takeover,
            telemetry=self.telemetry,
        )

        self._lock = asyncio.Lock()

    async def _on_initialize(self) -> None:
        """Initialize Win32 ABI gate, verify topology, setup state, and start watchdog."""
        try:
            if not self._enable_live_appbar:
                self._details["integration_status"] = "LIVE_APPBAR_DISABLED"
                raise WorkspaceError(
                    "Production workspace live AppBar is disabled via enable_live_appbar=False",
                    recoverable=False,
                )

            # 1. Verify Win32 AMD64 ABI Gate
            abi_report = validate_workspace_abi()
            if not abi_report["is_valid"]:
                raise WorkspaceError(
                    f"Win32 AMD64 Workspace ABI validation failed closed: {abi_report}",
                    recoverable=False,
                )

            # 2. Transition State to READY_FLOATING
            if self.state_manager.current_state == WorkspaceState.UNINITIALIZED:
                self.state_manager.transition_to(WorkspaceState.READY_FLOATING, reason="Adapter initialization")

            # 3. Query Initial Display Geometry
            initial_geom = self.geometry_coordinator.query_current_geometry(is_docked=False)

            # 4. Start Watchdog if Configured
            if self.auto_start_watchdog:
                await self.watchdog.start()

            # 5. Populate Capability Details
            self._details = {
                "state": self.state_manager.current_state.value,
                "desktop_generation_id": self.state_manager.desktop_generation_id,
                "topology_generation_id": self.state_manager.topology_generation_id,
                "monitor_count": len(initial_geom.monitors),
                "primary_dpi": initial_geom.dpi,
                "primary_scale_factor": initial_geom.scale_factor,
                "watchdog_active": self.watchdog.is_running,
            }
            logger.info(
                "ProductionWorkspaceAdapter initialized (State: %s, Monitors: %d, DPI: %d)",
                self.state_manager.current_state.value,
                len(initial_geom.monitors),
                initial_geom.dpi,
            )

        except Exception as ex:
            logger.error("Failed to initialize ProductionWorkspaceAdapter: %s", ex, exc_info=True)
            self.state_manager.transition_to(WorkspaceState.FAILED, reason=str(ex))
            raise CapabilityInitializationError(self._capability_type, str(ex)) from ex

    async def _on_shutdown(self) -> None:
        """Deterministically stop watchdog, unregister AppBar, release window, and stop state manager."""
        logger.info("ProductionWorkspaceAdapter shutting down...")
        async with self._lock:
            # 1. Stop Watchdog
            if self.watchdog and self.watchdog.is_running:
                try:
                    await self.watchdog.stop()
                except Exception as ex:
                    logger.warning("Error stopping workspace watchdog during shutdown: %s", ex)

            # 2. Unregister AppBar if DOCKED
            if self.state_manager.is_docked:
                try:
                    await asyncio.to_thread(
                        self.appbar_driver.unregister_and_release,
                        state_manager=self.state_manager,
                    )
                except Exception as ex:
                    logger.warning("Error unregistering AppBar during shutdown: %s", ex)

            # 3. Transition to STOPPED
            try:
                if self.state_manager.can_transition_to(WorkspaceState.STOPPED):
                    self.state_manager.transition_to(WorkspaceState.STOPPED, reason="Adapter shutdown")
            except Exception as ex:
                logger.warning("Error transitioning workspace state manager to STOPPED: %s", ex)

            logger.info("ProductionWorkspaceAdapter shutdown completed cleanly")

    async def register_appbar(self, edge: str, size: int) -> bool:
        """Reserve screen edge for ORBIT window via transactional ABM lifecycle."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production workspace adapter is not ready",
            )

        async with self._lock:
            dock_edge = DockEdge.from_string(edge)
            if dock_edge == DockEdge.NONE:
                raise WorkspaceError(f"Cannot dock to DockEdge.NONE (requested: '{edge}')")

            # Execute transactional registration in worker thread
            res: AppBarOperationResult = await asyncio.to_thread(
                self.appbar_driver.register_and_dock,
                edge=dock_edge,
                requested_size_px=size,
                state_manager=self.state_manager,
            )

            if not res.success:
                raise WorkspaceError(
                    f"AppBar registration failed at stage '{res.operation}': {res.error_message}",
                    recoverable=True,
                )

            # Refresh and cache updated geometry
            updated_geom = self.geometry_coordinator.query_current_geometry(
                dock_edge=dock_edge,
                docked_bounds=res.final_rect,
                is_docked=True,
            )

            self._details["state"] = self.state_manager.current_state.value
            self._details["desktop_generation_id"] = self.state_manager.desktop_generation_id
            self._details["docked_bounds"] = res.final_rect.model_dump() if res.final_rect else None

            logger.info(
                "AppBar docked successfully on edge %s with size %dpx (Generation: %d)",
                dock_edge.value,
                size,
                self.state_manager.desktop_generation_id,
            )
            return True

    async def unregister_appbar(self) -> bool:
        """Restore standard desktop work area and release AppBar reservation."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production workspace adapter is not ready",
            )

        async with self._lock:
            if not self.state_manager.is_docked:
                # Idempotent return if already floating
                return True

            # Unregister in worker thread
            res: AppBarOperationResult = await asyncio.to_thread(
                self.appbar_driver.unregister_and_release,
                state_manager=self.state_manager,
            )

            # Refresh floating geometry
            self.geometry_coordinator.query_current_geometry(is_docked=False)
            self._details["state"] = self.state_manager.current_state.value
            self._details["desktop_generation_id"] = self.state_manager.desktop_generation_id
            self._details["docked_bounds"] = None

            logger.info("AppBar unmounted and work area restored (Generation: %d)", self.state_manager.desktop_generation_id)
            return True

    async def get_work_area(self) -> BoundingBox:
        """Query available desktop work area after subtracting dock reservations."""
        geom = await self.get_geometry()
        return geom.work_area

    async def get_geometry(self) -> WorkspaceGeometry:
        """Query authoritative WorkspaceGeometry snapshot."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production workspace adapter is not ready",
            )

        return self.geometry_coordinator.query_current_geometry(
            dock_edge=self.appbar_driver.dock_edge if self.state_manager.is_docked else DockEdge.NONE,
            docked_bounds=self.appbar_driver.docked_bounds if self.state_manager.is_docked else None,
            is_docked=self.state_manager.is_docked,
        )

    def get_desktop_generation(self) -> int:
        """Get the authoritative active desktop generation ID."""
        return self.state_manager.desktop_generation_id

    def validate_coordinate(
        self,
        x: int,
        y: int,
        expected_generation: Optional[int] = None,
    ) -> CoordinateValidationResult:
        """Validate target coordinate against active workspace geometry and generation parity."""
        return self.geometry_coordinator.validate_coordinate(
            x=x,
            y=y,
            expected_generation=expected_generation,
        )

    async def launch_process(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Launch a Windows desktop application process."""
        try:
            import subprocess
            import ctypes
            clean_name = app_name.strip().lower()

            # Map known Windows 10/11 Packaged / Modern Apps to their AppsFolder AUMIDs
            known_aumids = {
                "mspaint": "Microsoft.Paint_8wekyb3d8bbwe!App",
                "paint": "Microsoft.Paint_8wekyb3d8bbwe!App",
                "notepad": "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
                "calc": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                "calculator": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                "terminal": "Microsoft.WindowsTerminal_8wekyb3d8bbwe!App",
                "photos": "Microsoft.Windows.Photos_8wekyb3d8bbwe!App",
            }

            logger.info("WORKSPACE LAUNCH_PROCESS: app_name='%s'", clean_name)

            if sys.platform == "win32":
                lookup_key = clean_name.replace(".exe", "")
                aumid = known_aumids.get(lookup_key)
                if aumid:
                    # Launch modern Packaged/AppX Windows App via explorer.exe shell:AppsFolder
                    try:
                        ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", f"shell:AppsFolder\\{aumid}", None, 1)
                    except Exception:
                        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{aumid}"])
                else:
                    exe_name = clean_name if clean_name.endswith(".exe") else f"{clean_name}.exe"
                    res = ctypes.windll.shell32.ShellExecuteW(None, "open", exe_name, None, None, 1)
                    if res <= 32:
                        subprocess.Popen(["cmd.exe", "/c", "start", "", exe_name])
            else:
                subprocess.Popen(clean_name, shell=True)

            await asyncio.sleep(2.5)
            return {"app_name": app_name}
        except Exception as ex:
            logger.warning("launch_process error for %s: %s", app_name, ex, exc_info=True)
            return None

    async def set_focus_window(self, hwnd: int) -> bool:
        """Set foreground window focus via Win32."""
        if sys.platform != "win32":
            return True
        try:
            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
            EvidenceBasedTargetLocator._force_foreground_window(int(hwnd))
            await asyncio.sleep(0.3)
            return True
        except Exception as ex:
            logger.warning("set_focus_window error for HWND %s: %s", hwnd, ex)
            return False

    async def list_windows(self) -> List[Any]:
        """List top-level visible desktop windows."""
        from orbit.runtime.cognitive.observer import CurrentStateObserver
        obs = CurrentStateObserver()
        raw_wins = obs._enumerate_visible_windows()
        class WinInfo:
            def __init__(self, hwnd: int, title: str, class_name: str):
                self.hwnd = hwnd
                self.title = title
                self.class_name = class_name
        return [WinInfo(w["hwnd"], w["title"], w.get("class_name", "")) for w in raw_wins]

    async def recover_workspace(self, recovery_token: Optional[str] = None) -> bool:
        """Attempt recovery from degraded or failed workspace states."""
        async with self._lock:
            # If FAILED or DEGRADED, attempt reset via state manager token
            if self.state_manager.current_state in {WorkspaceState.DEGRADED, WorkspaceState.FAILED}:
                token = recovery_token or ("CONFIRM_RESET" if self.state_manager.current_state == WorkspaceState.DEGRADED else "CONFIRM_OPERATOR_MANUAL_RESET")
                self.state_manager.transition_to(WorkspaceState.READY_FLOATING, recovery_token=token)
                self.geometry_coordinator.query_current_geometry(is_docked=False)
                return True

            # If watchdog detected anomaly, run watchdog recovery
            probe = self.watchdog.probe_health()
            if not probe.is_healthy:
                return await self.watchdog.attempt_recovery(probe)

            return True

    async def get_health(self) -> CapabilityHealth:
        """Generate structured CapabilityHealth diagnostic report."""
        st = self.state_manager.current_state
        probe = self.watchdog.probe_health() if self.watchdog else None

        if self._lifecycle_state == CapabilityLifecycleState.FAILED or st == WorkspaceState.FAILED:
            health_status = CapabilityHealthStatus.FAILED
        elif self._lifecycle_state != CapabilityLifecycleState.READY:
            health_status = CapabilityHealthStatus.UNAVAILABLE
        elif st == WorkspaceState.DEGRADED or (probe and not probe.is_healthy):
            health_status = CapabilityHealthStatus.DEGRADED
        else:
            health_status = CapabilityHealthStatus.HEALTHY

        details = WorkspaceHealthDetails(
            state=st,
            dock_edge=self.appbar_driver.dock_edge if self.appbar_driver else DockEdge.NONE,
            is_docked=self.state_manager.is_docked,
            desktop_generation_id=self.state_manager.desktop_generation_id,
            topology_generation_id=self.state_manager.topology_generation_id,
            monitor_count=len(self.geometry_coordinator.gateway.enumerate_monitors()),
            primary_dpi=self.geometry_coordinator.gateway.get_system_dpi(),
            watchdog_active=self.watchdog.is_running if self.watchdog else False,
            last_error=self.state_manager.last_error or (probe.error_message if probe else None),
        )

        return CapabilityHealth(
            capability_name=self._capability_name,
            capability_type=self._capability_type,
            adapter_mode=self._adapter_mode,
            lifecycle_state=self._lifecycle_state,
            status=health_status,
            error_count=self._error_count,
            last_error=self._last_error or self.state_manager.last_error,
            details=details.model_dump(),
        )
