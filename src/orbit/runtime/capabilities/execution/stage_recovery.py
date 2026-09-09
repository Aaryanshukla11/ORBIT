"""Stage Recovery Manager for Unverified or Stalled Stages (M1.9 Component 11).

INVARIANT:
Recovery attempts are bounded (max 2 per stage).
Never infinite loop. If recovery fails to produce the expected effect, fail closed honestly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    CapabilityExecutor,
    StageOutcomeStatus,
)
from orbit.runtime.cognitive.observer import CurrentStateObserver

logger = logging.getLogger(__name__)


class StageRecoveryManager:
    """Manages bounded recovery when a strategy stage was dispatched but effect remains unverified."""

    def __init__(self, max_recovery_attempts: int = 2) -> None:
        self._max_recovery_attempts = max_recovery_attempts
        self._stage_attempts: Dict[int, int] = {}

    def get_attempts(self, stage_index: int) -> int:
        return self._stage_attempts.get(stage_index, 0)

    def can_attempt_recovery(self, stage_index: int) -> bool:
        return self._stage_attempts.get(stage_index, 0) < self._max_recovery_attempts

    async def attempt_recovery(
        self,
        executor: CapabilityExecutor,
        request: CapabilityExecutionRequest,
        observer: Optional[CurrentStateObserver] = None,
    ) -> CapabilityExecutionResult:
        """Attempt bounded recovery for an unverified stage."""
        stage_idx = request.stage_index
        self._stage_attempts[stage_idx] = self._stage_attempts.get(stage_idx, 0) + 1
        attempt_num = self._stage_attempts[stage_idx]

        logger.warning(
            "[StageRecoveryManager] Attempting recovery %d/%d for stage %d (%s)",
            attempt_num,
            self._max_recovery_attempts,
            stage_idx,
            executor.capability_id,
        )

        # 1. Settling sleep to allow slow UI updates to materialize
        await asyncio.sleep(0.5)

        # 2. Refocus window if target application known
        app_name = request.parameters.get("application_name") or request.parameters.get("app_name")
        if app_name:
            try:
                import sys
                if sys.platform == "win32":
                    from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
                    import ctypes
                    hwnd = ctypes.windll.user32.FindWindowW(None, str(app_name))
                    if hwnd:
                        EvidenceBasedTargetLocator._force_foreground_window(hwnd)
            except Exception:
                pass

        # 3. Re-capture fresh desktop state if observer available
        if observer is not None:
            try:
                fresh_obs = await observer.observe()
                request.context["current_observation"] = fresh_obs
            except Exception as ex:
                logger.debug("Recovery observation recapture notice: %s", ex)

        # 4. Retry capability execution
        retry_result = await executor.execute(request)
        if retry_result.dispatch_success:
            retry_result.stage_status = StageOutcomeStatus.RECOVERING
        return retry_result
