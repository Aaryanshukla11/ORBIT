"""Production Human Takeover Adapter integrating native low-level hooks into ORBIT capability lifecycle."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityInitializationError,
    CapabilityUnavailableError,
    HumanTakeoverError,
)
from orbit.adapters.takeover.classifier import TakeoverEvidence
from orbit.adapters.takeover.hook import NativeHookInstallationError, NativeInputMonitor
from orbit.adapters.takeover.safety import TakeoverAbiGate
from orbit.adapters.takeover.state import TakeoverState, TakeoverStateManager
from orbit.adapters.takeover.telemetry import TakeoverTelemetryLogger, TakeoverTelemetrySnapshot
from orbit.config import is_human_takeover_enabled
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
    HumanTakeoverCapability,
)

logger = logging.getLogger(__name__)


class ProductionHumanTakeoverAdapter(BaseCapabilityAdapter, HumanTakeoverCapability):
    """Production low-level hook adapter detecting physical human intervention with sub-millisecond latency."""

    def __init__(
        self,
        enable_live_hooks: bool = True,
        quiet_period_seconds: float = 1.0,
        human_takeover_enabled: Optional[bool] = None,
    ) -> None:
        super().__init__(
            capability_name="ProductionHumanTakeover",
            capability_type=CapabilityType.HUMAN_TAKEOVER,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self._enable_live_hooks = enable_live_hooks
        self._human_takeover_enabled = human_takeover_enabled
        self._state_manager = TakeoverStateManager(quiet_period_seconds=quiet_period_seconds)
        self._monitor = NativeInputMonitor()
        self.telemetry = TakeoverTelemetryLogger()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._on_takeover_cb: Optional[Callable[..., Any]] = None

        self._details = {
            "integration_status": "ACTIVE" if enable_live_hooks else "MOCK_ONLY",
            "live_hooks_enabled": enable_live_hooks,
            "human_takeover_enabled": self.is_feature_enabled,
            "hooks_active": False,
        }

    @property
    def is_feature_enabled(self) -> bool:
        if self._human_takeover_enabled is not None:
            return self._human_takeover_enabled
        return is_human_takeover_enabled()


    @property
    def state_manager(self) -> TakeoverStateManager:
        return self._state_manager

    @property
    def current_state(self) -> TakeoverState:
        return self._state_manager.current_state

    async def _on_initialize(self) -> None:
        """Validates 64-bit AMD64 Win32 Hook C ABI before entering READY state."""
        if not self._enable_live_hooks:
            self._details["integration_status"] = "LIVE_HOOKS_DISABLED"
            raise HumanTakeoverError("Live Win32 hooks are disabled in adapter configuration", recoverable=False)

        abi_res = TakeoverAbiGate.validate_abi()
        if not abi_res.is_valid:
            self._details["abi_error"] = abi_res.error_message
            raise CapabilityInitializationError(
                CapabilityType.HUMAN_TAKEOVER,
                f"AMD64 Win32 Hook ABI check failed: {abi_res.error_message}",
            )

        self._details["abi_validation"] = "PASSED"
        self._details["pointer_size"] = abi_res.pointer_size
        self._details["integration_status"] = "ACTIVE"
        logger.info("ProductionHumanTakeoverAdapter initialized successfully with valid AMD64 ABI")

    async def _on_shutdown(self) -> None:
        """Cleanly unhooks and joins native message pump thread on adapter shutdown."""
        await self.stop_monitoring()
        self._state_manager.transition_to(TakeoverState.STOPPED, reason="Adapter shutdown")
        self._details["hooks_active"] = False

    async def start_monitoring(
        self,
        on_takeover_detected: Callable[..., Any],
    ) -> bool:
        """Installs native low-level hooks and starts background message pump."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "ProductionHumanTakeoverAdapter is not in READY state",
            )

        self._loop = asyncio.get_running_loop()
        self._on_takeover_cb = on_takeover_detected

        if self._monitor.is_running:
            return True

        self._state_manager.transition_to(TakeoverState.STARTING, reason="Starting input monitor")

        def _on_hook_evidence(evidence: TakeoverEvidence) -> None:
            # Executes on native hook thread! Keep non-blocking (<50 microseconds).
            t_now = time.perf_counter_ns()
            hook_to_sig_us = max(0.0, (t_now - evidence.timestamp_ns) / 1000.0)

            is_primary_trigger = False
            # Only trigger takeover if the feature is actively enabled
            if self.is_feature_enabled and evidence.should_trigger_takeover:
                is_primary_trigger = self._state_manager.handle_takeover_event(evidence)

            self.telemetry.log_evidence(
                evidence=evidence,
                is_primary_trigger=is_primary_trigger,
                hook_to_signal_us=hook_to_sig_us,
            )

            # If this is a new primary takeover trigger, cross into asyncio event loop
            if is_primary_trigger and self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._dispatch_takeover_callback, evidence)

        try:
            self._monitor.start(on_event_callback=_on_hook_evidence)
            self._state_manager.transition_to(TakeoverState.MONITORING, reason="Hooks active")
            self._details["hooks_active"] = True
            logger.info("Human Takeover monitoring active (feature_enabled=%s)", self.is_feature_enabled)
            return True
        except NativeHookInstallationError as ex:
            self._state_manager.transition_to(TakeoverState.FAILED, reason=str(ex))
            self._health_status = CapabilityHealthStatus.FAILED
            self._last_error = str(ex)
            self._details["hooks_active"] = False
            logger.error("Failed to start takeover monitoring: %s", ex)
            return False

    def _dispatch_takeover_callback(self, evidence: TakeoverEvidence) -> None:
        """Executes inside asyncio event loop thread."""
        if not self.is_feature_enabled:
            return
        if self._on_takeover_cb:
            try:
                res = self._on_takeover_cb()
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except TypeError:
                # Callback might accept evidence parameter
                try:
                    res = self._on_takeover_cb(evidence)
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(res)
                except Exception as ex:
                    logger.warning("Error invoking takeover callback with evidence: %s", ex)
            except Exception as ex:
                logger.warning("Error invoking takeover callback: %s", ex)

    async def stop_monitoring(self) -> bool:
        """Uninstalls low-level hooks and stops message pump."""
        if self._monitor.is_running:
            self._monitor.stop()
        self._details["hooks_active"] = False
        if self._state_manager.current_state != TakeoverState.STOPPED:
            self._state_manager.transition_to(TakeoverState.STOPPED, reason="Monitoring stopped")
        return True

    async def is_takeover_active(self) -> bool:
        """Query whether human takeover is actively preempting."""
        if not self.is_feature_enabled:
            return False
        return self._state_manager.is_takeover_active

    async def reset_takeover_state(self) -> bool:
        """Acknowledge and release human takeover, returning state to MONITORING or STOPPED."""
        if self._state_manager.is_takeover_active:
            self._state_manager.transition_to(TakeoverState.RELEASING, reason="Operator release requested")
            if self._monitor.is_running:
                self._state_manager.transition_to(TakeoverState.MONITORING, reason="Returned to autonomous monitoring")
            else:
                self._state_manager.transition_to(TakeoverState.STOPPED, reason="Returned to stopped state")
            logger.info("Human Takeover state successfully released")
            return True
        return False

    async def get_takeover_metrics(self) -> Dict[str, Any]:
        """Query aggregated latency and event statistics."""
        return self.telemetry.get_snapshot().model_dump()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Query detailed takeover state diagnostics."""
        diag = self._state_manager.get_diagnostics()
        diag["is_monitoring"] = self._monitor.is_running
        diag["hooks_active"] = self._details.get("hooks_active", False)
        diag["human_takeover_enabled"] = self.is_feature_enabled
        return diag

    async def get_health(self) -> CapabilityHealth:
        """Query subsystem health."""
        details = dict(self._details)
        details["human_takeover_enabled"] = self.is_feature_enabled
        details["current_takeover_state"] = self._state_manager.current_state.value
        details["is_takeover_active"] = self._state_manager.is_takeover_active if self.is_feature_enabled else False
        details["is_monitoring"] = self._monitor.is_running
        details["telemetry"] = self.telemetry.get_snapshot().model_dump()

        last_ev = self._state_manager.last_evidence
        if last_ev:
            details["last_takeover_evidence"] = last_ev.model_dump()

        status = CapabilityHealthStatus.HEALTHY
        if self._state_manager.current_state == TakeoverState.FAILED or not self.is_ready:
            status = CapabilityHealthStatus.FAILED
        elif self.is_feature_enabled and self._state_manager.is_takeover_active:
            status = CapabilityHealthStatus.DEGRADED

        return CapabilityHealth(
            capability_name=self._capability_name,
            capability_type=self._capability_type,
            adapter_mode=self._adapter_mode,
            lifecycle_state=self._lifecycle_state,
            status=status,
            message=f"TakeoverState={self._state_manager.current_state.value}, Hooks={self._monitor.is_running}, Enabled={self.is_feature_enabled}",
            details=details,
        )
