"""Geometry Drawing Capability Executor (M1.9)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executors.base import BaseCapabilityExecutor

logger = logging.getLogger(__name__)


class GeometryDrawingExecutor(BaseCapabilityExecutor):
    """Executes DRAW_BASIC_GEOMETRY by dispatching discrete stroke trajectories via PointerCapability."""

    def __init__(self, pointer: Optional[Any] = None) -> None:
        super().__init__(capability_id="DRAW_BASIC_GEOMETRY")
        self._pointer = pointer

    def is_available(self) -> bool:
        return self._pointer is not None

    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        shape = parameters.get("shape", "cube")
        if not shape:
            return False, "Missing 'shape' parameter"
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

        shape = str(request.parameters.get("shape", "cube")).lower()
        logger.info("[GeometryDrawingExecutor] Rendering basic geometry shape '%s'", shape)

        # Base anchor coordinates in the active canvas (or default safe canvas center)
        canvas_rect = request.parameters.get("canvas_rect")
        if canvas_rect and isinstance(canvas_rect, (list, tuple)) and len(canvas_rect) == 4:
            x0, y0 = int(canvas_rect[0] + canvas_rect[2] * 0.3), int(canvas_rect[1] + canvas_rect[3] * 0.3)
        else:
            x0, y0 = 450, 350

        size = int(request.parameters.get("size", 120))
        strokes_dispatched = 0

        try:
            # Draw square 1
            await self._draw_rect(x0, y0, size, size)
            strokes_dispatched += 4

            if "cube" in shape:
                # Draw offset square 2
                offset = int(size * 0.35)
                await self._draw_rect(x0 + offset, y0 - offset, size, size)
                strokes_dispatched += 4
                # Connect 4 vertices
                await self._draw_line(x0, y0, x0 + offset, y0 - offset)
                await self._draw_line(x0 + size, y0, x0 + size + offset, y0 - offset)
                await self._draw_line(x0, y0 + size, x0 + offset, y0 + size - offset)
                await self._draw_line(x0 + size, y0 + size, x0 + size + offset, y0 + size - offset)
                strokes_dispatched += 4

            await asyncio.sleep(0.3)

            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=True,
                execution_success=True,
                stage_status=StageOutcomeStatus.DISPATCHED,
                output={
                    "shape": shape,
                    "strokes_dispatched": strokes_dispatched,
                    "anchor": [x0, y0],
                },
                evidence={
                    "shape": shape,
                    "strokes_count": strokes_dispatched,
                },
            )
        except Exception as ex:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="STROKE_DISPATCH_FAILED",
                failure_reason=str(ex),
            )

    async def _draw_rect(self, x: int, y: int, w: int, h: int) -> None:
        await self._draw_line(x, y, x + w, y)
        await self._draw_line(x + w, y, x + w, y + h)
        await self._draw_line(x + w, y + h, x, y + h)
        await self._draw_line(x, y + h, x, y)

    async def _draw_line(self, x1: int, y1: int, x2: int, y2: int) -> None:
        if self._pointer is None:
            return
        await self._pointer.move_to(x1, y1)
        await asyncio.sleep(0.02)
        if hasattr(self._pointer, "mouse_down"):
            await self._pointer.mouse_down()
        await self._pointer.move_to(x2, y2)
        await asyncio.sleep(0.02)
        if hasattr(self._pointer, "mouse_up"):
            await self._pointer.mouse_up()
        await asyncio.sleep(0.01)
