"""Clipboard Paste Capability Executor (M1.9)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executors.base import BaseCapabilityExecutor

logger = logging.getLogger(__name__)


class ClipboardPasteExecutor(BaseCapabilityExecutor):
    """Executes CLIPBOARD_PASTE by sending Ctrl+V hotkey to active control."""

    def __init__(self, keyboard: Optional[Any] = None) -> None:
        super().__init__(capability_id="CLIPBOARD_PASTE")
        self._keyboard = keyboard

    def is_available(self) -> bool:
        return self._keyboard is not None

    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        return True, None

    async def _execute_internal(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        if self._keyboard is None:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="REQUIRED_ADAPTER_MISSING",
                failure_reason="KeyboardCapability adapter is not provided",
            )

        logger.info("[ClipboardPasteExecutor] Dispatching Ctrl+V paste")
        await self._keyboard.press_key("ctrl")
        await self._keyboard.press_key("v")
        await asyncio.sleep(0.05)
        await self._keyboard.release_key("v")
        await self._keyboard.release_key("ctrl")
        await asyncio.sleep(0.2)

        return CapabilityExecutionResult(
            capability_id=self.capability_id,
            stage_index=request.stage_index,
            dispatch_success=True,
            execution_success=True,
            stage_status=StageOutcomeStatus.DISPATCHED,
            output={"pasted": True},
            evidence={"action": "Ctrl+V"},
        )
