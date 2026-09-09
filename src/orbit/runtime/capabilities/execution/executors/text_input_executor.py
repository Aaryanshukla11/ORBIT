"""Text Input Capability Executor (M1.9)."""

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


class TextInputExecutor(BaseCapabilityExecutor):
    """Executes TYPE_TEXT into focused control via KeyboardCapability or atomic clipboard."""

    def __init__(self, keyboard: Optional[Any] = None) -> None:
        super().__init__(capability_id="TYPE_TEXT")
        self._keyboard = keyboard

    def is_available(self) -> bool:
        return self._keyboard is not None

    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if "text" not in parameters and "query" not in parameters:
            return False, "TYPE_TEXT requires parameter 'text' or 'query'"
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

        text = str(request.parameters.get("text", request.parameters.get("query", "")))
        press_enter = bool(request.parameters.get("press_enter", False))

        logger.info("[TextInputExecutor] Typing '%s' (len=%d, enter=%s)", text, len(text), press_enter)

        # Dispatch via keyboard adapter
        await self._keyboard.type_text(text)
        if press_enter:
            await asyncio.sleep(0.05)
            await self._keyboard.press_key("enter")
            await self._keyboard.release_key("enter")

        await asyncio.sleep(0.1)

        return CapabilityExecutionResult(
            capability_id=self.capability_id,
            stage_index=request.stage_index,
            dispatch_success=True,
            execution_success=True,
            stage_status=StageOutcomeStatus.DISPATCHED,
            output={
                "typed_text": text,
                "character_count": len(text),
            },
            evidence={
                "text_length": len(text),
                "press_enter": press_enter,
            },
        )
