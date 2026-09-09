"""Base capability executor providing common telemetry and timing (M1.9)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    CapabilityExecutor,
    StageOutcomeStatus,
)

logger = logging.getLogger(__name__)


class BaseCapabilityExecutor(CapabilityExecutor):
    """Convenience base class providing standardized timing and error wrapping."""

    async def execute(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        t0 = time.perf_counter()
        valid, err = self.validate_inputs(request.parameters)
        if not valid:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="INVALID_PARAMETERS",
                failure_reason=err or "Invalid parameters schema",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        if not self.is_available():
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="CAPABILITY_UNAVAILABLE",
                failure_reason=f"Capability executor '{self.capability_id}' is not operational or required adapters are missing",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        try:
            res = await self._execute_internal(request)
            res.duration_ms = (time.perf_counter() - t0) * 1000.0
            return res
        except Exception as ex:
            logger.error("Unhandled exception in executor '%s': %s", self.capability_id, ex, exc_info=True)
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="PHYSICAL_DISPATCH_FAILED",
                failure_reason=str(ex),
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

    async def _execute_internal(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        """Internal execution logic to be overridden by subclasses."""
        raise NotImplementedError
