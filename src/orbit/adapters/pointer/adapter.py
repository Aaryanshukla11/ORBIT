"""Production Pointer Adapter implementing absolute cursor movement and button transactions via Win32 SendInput."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Callable, Dict, Optional, Tuple

from orbit.adapters.base import (
    BaseCapabilityAdapter,
    CapabilityInitializationError,
    CapabilityUnavailableError,
    PointerError,
)
from orbit.adapters.pointer.buttons import (
    ButtonExecutionStatus,
    ButtonTransactionExecutor,
    ClickExecutionStatus,
)
from orbit.adapters.pointer.health import PointerHealthTracker
from orbit.adapters.pointer.movement import (
    MovementEvidenceLevel,
    MovementExecutor,
    MovementResult,
    MovementStatus,
    get_live_cursor_position,
)
from orbit.adapters.pointer.safety import (
    AbiGate,
    MouseButton,
    query_virtual_desktop_metrics,
    validate_runtime_abi,
)
from orbit.adapters.pointer.state import PointerStateManager
from orbit.contracts.capabilities import (
    AdapterMode,
    CapabilityHealth,
    CapabilityLifecycleState,
    CapabilityType,
    PointerCapability,
)
from orbit.models.common import ScreenPoint
from orbit.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)


class ProductionPointerAdapter(BaseCapabilityAdapter, PointerCapability):
    """Production pointer adapter backed by Win32 SendInput absolute cursor movement and button transactions."""

    def __init__(
        self,
        tolerance_px: int = 3,
        abi_override: Optional[Dict[str, Any]] = None,
        sendinput_override: Optional[Callable[[int, Any, int], int]] = None,
        cursorpos_override: Optional[Callable[[], Tuple[int, int]]] = None,
        topology_override: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            capability_name="ProductionPointer",
            capability_type=CapabilityType.POINTER,
            adapter_mode=AdapterMode.PRODUCTION,
        )
        self.tolerance_px = tolerance_px
        self._abi_override = abi_override
        self._sendinput_override = sendinput_override
        self._cursorpos_override = cursorpos_override
        self._topology_override = topology_override

        self.health_tracker = PointerHealthTracker()
        self.state_manager = PointerStateManager()
        self._abi_gate: Optional[AbiGate] = None
        self._executor: Optional[MovementExecutor] = None
        self._button_executor: Optional[ButtonTransactionExecutor] = None

    async def _on_initialize(self) -> None:
        """Initialize DPI awareness, enforce Win32 C ABI gate, and verify display topology."""
        try:
            # 1. Initialize DPI awareness if available
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                except Exception as ex:
                    logger.debug("SetProcessDpiAwarenessContext notice: %s", ex)

            # 2. Enforce Win32 SendInput C ABI Layout
            abi_res = validate_runtime_abi(simulated_override=self._abi_override)
            self.health_tracker.abi_status = abi_res.status.value

            if not abi_res.is_valid:
                raise PointerError(
                    f"Win32 SendInput ABI verification failed closed: {abi_res.status.value} "
                    f"({abi_res.error_message})"
                )

            self._abi_gate = AbiGate(validation_result=abi_res)

            # 3. Verify Virtual Desktop Dimensions
            metrics = query_virtual_desktop_metrics()
            if not metrics.is_valid or metrics.width <= 0 or metrics.height <= 0:
                raise PointerError("Invalid virtual desktop screen geometry retrieved from Win32")

            # 4. Construct Movement Executor
            self._executor = MovementExecutor(
                abi_gate=self._abi_gate,
                action_counter=self.health_tracker.action_counter,
                sendinput_override=self._sendinput_override,
                cursorpos_override=self._cursorpos_override,
                topology_override=self._topology_override,
            )

            # 5. Construct Button Transaction Executor
            self._button_executor = ButtonTransactionExecutor(
                native_gateway=self._executor.gateway,
                state_manager=self.state_manager,
                abi_gate=self._abi_gate,
                action_counter=self.health_tracker.action_counter,
            )

            self._details["virtual_desktop"] = {
                "origin_x": metrics.x_origin,
                "origin_y": metrics.y_origin,
                "width": metrics.width,
                "height": metrics.height,
            }
            logger.info(
                "ProductionPointerAdapter initialized (Virtual Desktop: %dx%d)",
                metrics.width,
                metrics.height,
            )

        except Exception as ex:
            self.health_tracker.last_error = str(ex)
            raise CapabilityInitializationError(self._capability_type, str(ex)) from ex

    async def _on_shutdown(self) -> None:
        """Clean up adapter handles and clear executor references."""
        if self._button_executor is not None and len(self.state_manager.held_buttons) > 0:
            try:
                await self.emergency_release_all()
            except Exception as ex:
                logger.warning("Emergency release on shutdown warning: %s", ex)

        self._button_executor = None
        self._executor = None
        self._abi_gate = None
        logger.info("ProductionPointerAdapter shutdown completed")

    async def move_to(
        self,
        x: int,
        y: int,
        duration_ms: float = 0.0,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Execute single-packet (N=1) absolute cursor movement to target coordinates."""
        if not self.is_ready or self._executor is None:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )

        result: MovementResult = await asyncio.to_thread(
            self._executor.execute_movement,
            target_x=x,
            target_y=y,
            tolerance_px=self.tolerance_px,
            cancellation_token=cancellation_token,
        )

        self.health_tracker.last_latency_us = result.duration_us

        if result.status == MovementStatus.MOVEMENT_VERIFIED:
            return True

        err_msg = result.error_message or f"Pointer movement failed with status: {result.status.value}"
        self.health_tracker.last_error = err_msg
        raise PointerError(f"[{result.status.value}] {err_msg}")

    async def get_cursor_position(self) -> ScreenPoint:
        """Query physical cursor position via Win32 GetCursorPos."""
        if not self.is_ready:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )

        if self._cursorpos_override:
            x, y = self._cursorpos_override()
        else:
            x, y = await asyncio.to_thread(get_live_cursor_position)

        return ScreenPoint(x=x, y=y)

    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        count: int = 1,
        dwell_ms: float = 50.0,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Perform an atomic click transaction at target or current coordinates."""
        if not self.is_ready or self._button_executor is None:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )

        try:
            btn = MouseButton(button.lower())
        except ValueError:
            raise PointerError(f"Unsupported mouse button: {button}. Supported: left, right, middle")

        # Step 1: Move to target coordinates if supplied
        if x is not None and y is not None:
            await self.move_to(x, y, cancellation_token=cancellation_token)

        # Step 2: Execute atomic clicks
        for _ in range(count):
            res = await asyncio.to_thread(
                self._button_executor.execute_click,
                button=btn,
                dwell_ms=dwell_ms,
                cancellation_token=cancellation_token,
            )
            if res.status != ClickExecutionStatus.CLICK_VERIFIED:
                if res.is_locked:
                    raise PointerError(
                        f"Pointer entered UNRESOLVED_LOCKED (reason: {res.lockout_reason.value}, token: {res.recovery_token})"
                    )
                raise PointerError(f"[{res.status.value}] Click transaction failed: {res.status.value}")

        return True

    async def press_down(
        self,
        button: str = "left",
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Hold down a synthetic mouse button."""
        if not self.is_ready or self._button_executor is None:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )

        try:
            btn = MouseButton(button.lower())
        except ValueError:
            raise PointerError(f"Unsupported mouse button: {button}. Supported: left, right, middle")

        res = await asyncio.to_thread(
            self._button_executor.execute_button_down,
            button=btn,
            cancellation_token=cancellation_token,
        )

        if res.status == ButtonExecutionStatus.BUTTON_DOWN_ACCEPTED:
            return True

        if res.is_locked:
            raise PointerError(
                f"Pointer is UNRESOLVED_LOCKED (reason: {res.lockout_reason.value}, token: {res.recovery_token})"
            )
        raise PointerError(f"[{res.status.value}] Button-down execution failed: {res.status.value}")

    async def release_up(
        self,
        button: str = "left",
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Release a held synthetic mouse button."""
        if not self.is_ready or self._button_executor is None:
            raise CapabilityUnavailableError(
                self._capability_type,
                self._lifecycle_state,
                "Production pointer adapter is not ready",
            )

        try:
            btn = MouseButton(button.lower())
        except ValueError:
            raise PointerError(f"Unsupported mouse button: {button}. Supported: left, right, middle")

        res = await asyncio.to_thread(
            self._button_executor.execute_button_up,
            button=btn,
            cancellation_token=cancellation_token,
        )

        if res.status == ButtonExecutionStatus.BUTTON_UP_ACCEPTED:
            return True

        if res.is_locked:
            raise PointerError(
                f"Pointer entered UNRESOLVED_LOCKED (reason: {res.lockout_reason.value}, token: {res.recovery_token})"
            )
        raise PointerError(f"[{res.status.value}] Button-up execution failed: {res.status.value}")

    async def emergency_release_all(
        self,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> bool:
        """Release all held synthetic buttons fail-closed."""
        if not self.is_ready or self._button_executor is None:
            return True

        res = await asyncio.to_thread(
            self._button_executor.emergency_sanitize,
            cancellation_token=cancellation_token,
        )
        return res.success

    async def get_lockout_state(self) -> str:
        """Query hardware/synthetic lockout state: LOCKED or NORMAL."""
        return "LOCKED" if self.state_manager.is_locked else "NORMAL"

    def recover_locked_state(self, recovery_token: str) -> bool:
        """Recover from UNRESOLVED_LOCKED via explicit administrative recovery token."""
        return self.state_manager.recover_locked_state(recovery_token)

    async def get_health(self) -> CapabilityHealth:
        """Generate structured CapabilityHealth diagnostic report."""
        return self.health_tracker.evaluate_health(self._lifecycle_state)
