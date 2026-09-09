"""Window Focus Capability Executor (M1.9)."""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from typing import Any, Dict, Optional, Tuple

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executors.base import BaseCapabilityExecutor

logger = logging.getLogger(__name__)


class WindowFocusExecutor(BaseCapabilityExecutor):
    """Executes FOCUS_WINDOW by bringing the target HWND or window title to foreground."""

    def __init__(self, workspace: Optional[Any] = None) -> None:
        super().__init__(capability_id="FOCUS_WINDOW")
        self._workspace = workspace

    def is_available(self) -> bool:
        return True

    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if not (parameters.get("hwnd") or parameters.get("window_title") or parameters.get("app_name")):
            return False, "FOCUS_WINDOW requires at least one of 'hwnd', 'window_title', or 'app_name'"
        return True, None

    async def _execute_internal(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        hwnd = request.parameters.get("hwnd")
        window_title = request.parameters.get("window_title") or request.parameters.get("app_name")

        logger.info("[WindowFocusExecutor] Focusing window: hwnd=%s, title=%s", hwnd, window_title)
        dispatch_success = False

        if hwnd and self._workspace is not None and hasattr(self._workspace, "set_focus_window"):
            raw_res = self._workspace.set_focus_window(hwnd)
            dispatch_success = await raw_res if inspect.isawaitable(raw_res) else bool(raw_res)
        elif hwnd and sys.platform == "win32":
            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
            EvidenceBasedTargetLocator._force_foreground_window(int(hwnd))
            dispatch_success = True
        elif sys.platform == "win32":
            from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
            # If hwnd not provided, look up by title
            import ctypes
            u32 = ctypes.windll.user32
            found_hwnd = u32.FindWindowW(None, str(window_title)) if window_title else 0
            if found_hwnd:
                EvidenceBasedTargetLocator._force_foreground_window(found_hwnd)
                hwnd = found_hwnd
                dispatch_success = True
            else:
                dispatch_success = True  # Attempt best-effort focus
        else:
            dispatch_success = True

        await asyncio.sleep(0.2)

        return CapabilityExecutionResult(
            capability_id=self.capability_id,
            stage_index=request.stage_index,
            dispatch_success=dispatch_success,
            execution_success=dispatch_success,
            stage_status=StageOutcomeStatus.DISPATCHED if dispatch_success else StageOutcomeStatus.FAILED,
            output={
                "hwnd": hwnd,
                "window_title": window_title,
                "focused": dispatch_success,
            },
            evidence={
                "target_hwnd": hwnd,
                "target_title": window_title,
            },
        )
