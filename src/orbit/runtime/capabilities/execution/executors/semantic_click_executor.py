"""Semantic Click Capability Executor (M1.9 Component 9).

Enforces Semantic Targeting Invariant: Screen coordinates are NEVER hardcoded in strategy
stages; they are resolved dynamically at runtime by TargetLocator.
Fails closed if PointerCapability is missing or target resolution fails.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, Optional, Tuple

from orbit.runtime.agent.contracts import SemanticTarget
from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executors.base import BaseCapabilityExecutor
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator, TargetLocator
from orbit.runtime.targeting.models import TargetIntent, TargetResolutionStatus, TargetStrategy

logger = logging.getLogger(__name__)


class SemanticClickExecutor(BaseCapabilityExecutor):
    """Resolves semantic target dynamically and clicks via PointerCapability."""

    def __init__(
        self,
        pointer: Optional[Any] = None,
        target_locator: Optional[TargetLocator] = None,
        capability_id: str = "CLICK",
    ) -> None:
        super().__init__(capability_id=capability_id)
        self._pointer = pointer
        self._target_locator = target_locator or EvidenceBasedTargetLocator()

    def is_available(self) -> bool:
        return self._pointer is not None

    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if "target" not in parameters and "target_name" not in parameters:
            return False, f"{self.capability_id} requires a semantic 'target' or 'target_name'"
        return True, None

    async def _execute_internal(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        if self._pointer is None:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="REQUIRED_ADAPTER_MISSING",
                failure_reason="PointerCapability adapter is not provided",
            )

        target_param = request.parameters.get("target") or request.parameters.get("target_name")
        target_name = getattr(target_param, "name", str(target_param))
        target_role = getattr(target_param, "role", "button")

        observation = request.context.get("current_observation")
        target_intent = TargetIntent(
            name=target_name,
            role=target_role,
            strategy=TargetStrategy.ACCESSIBILITY_ELEMENT,
        )

        resolved_coords: Optional[Tuple[int, int]] = None
        if self._target_locator is not None:
            locate_fn = getattr(self._target_locator, "locate_target", None) or getattr(self._target_locator, "resolve", None)
            if locate_fn:
                res_raw = locate_fn(target_intent, observation)
                res = await res_raw if inspect.isawaitable(res_raw) else res_raw
                is_res = getattr(res, "is_resolved", False) or (getattr(res, "status", None) == TargetResolutionStatus.RESOLVED if hasattr(res, "status") else False)
                tgt = getattr(res, "target", None) or getattr(res, "resolved_target", None)
                if is_res and tgt and hasattr(tgt, "bounding_box"):
                    resolved_coords = (int(tgt.bounding_box.center_x), int(tgt.bounding_box.center_y))
                elif is_res and tgt and hasattr(tgt, "bounds"):
                    resolved_coords = (int(tgt.bounds.center_x), int(tgt.bounds.center_y))
                elif is_res and tgt and hasattr(tgt, "safe_point"):
                    resolved_coords = (int(tgt.safe_point.x), int(tgt.safe_point.y))

        if not resolved_coords:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="TARGET_RESOLUTION_FAILED",
                failure_reason=f"TargetLocator could not resolve dynamic coordinates for semantic target '{target_name}'",
            )

        x, y = resolved_coords
        logger.info("[SemanticClickExecutor] Clicking '%s' at dynamic coordinates (%d, %d)", target_name, x, y)

        await self._pointer.move_to(x, y)
        await asyncio.sleep(0.05)
        await self._pointer.click()

        return CapabilityExecutionResult(
            capability_id=self.capability_id,
            stage_index=request.stage_index,
            dispatch_success=True,
            execution_success=True,
            stage_status=StageOutcomeStatus.DISPATCHED,
            output={
                "target_name": target_name,
                "coordinates": [x, y],
                "clicked": True,
            },
            evidence={
                "target_name": target_name,
                "resolved_coords": [x, y],
            },
        )
