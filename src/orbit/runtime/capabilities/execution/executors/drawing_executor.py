"""Canvas-Relative Drawing Capability Executor (M1.9).

Executes DRAW_STROKES by transforming normalized canvas-local (u, v) geometry
into grounded canvas screen pixels and dispatching pointer drag strokes.
"""

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


class DrawingExecutor(BaseCapabilityExecutor):
    """Executes DRAW_STROKES by transforming normalized canvas geometry into screen pixels."""

    def __init__(self, pointer: Optional[Any] = None) -> None:
        super().__init__(capability_id="DRAW_STROKES")
        self._pointer = pointer

    def is_available(self) -> bool:
        return self._pointer is not None

    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        strokes = parameters.get("strokes")
        if strokes is None:
            # Check legacy shape fallback
            if not parameters.get("shape"):
                return False, "Missing 'strokes' parameter (or legacy 'shape')"
            return True, None

        if not isinstance(strokes, list):
            return False, "'strokes' must be a list of stroke point sequences"

        for s_idx, stroke in enumerate(strokes):
            if not isinstance(stroke, list):
                return False, f"Stroke {s_idx} must be a list of 2-numeric points (u, v)"
            for p_idx, pt in enumerate(stroke):
                if isinstance(pt, dict):
                    return False, f"Stroke {s_idx} point {p_idx} cannot be a dictionary (raw coordinate dictionaries prohibited)"
                if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                    return False, f"Stroke {s_idx} point {p_idx} must be a 2-tuple of numeric coordinates (u, v)"
                u, v = pt
                if not isinstance(u, (int, float)) or not isinstance(v, (int, float)):
                    return False, f"Stroke {s_idx} point {p_idx} coordinates must be numbers"
                if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
                    return False, f"Stroke {s_idx} point {p_idx} ({u}, {v}) violates normalized canvas bounds [0.0, 1.0]"

        return True, None

    async def _execute_internal(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        if self._pointer is None:
            logger.warning("[DrawingExecutor] Execution rejected: PointerCapability adapter is missing (Fail-Closed)")
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="REQUIRED_ADAPTER_MISSING",
                failure_reason="PointerCapability adapter is not provided",
            )

        strokes = request.parameters.get("strokes")
        canvas_rect = request.parameters.get("canvas_rect")

        # Resolve canvas bounding box [x, y, width, height]
        if canvas_rect and isinstance(canvas_rect, (list, tuple)) and len(canvas_rect) == 4:
            cx, cy, cw, ch = [int(v) for v in canvas_rect]
        else:
            # Default safe center canvas if not explicitly bound
            cx, cy, cw, ch = 300, 200, 800, 600

        if cw <= 0 or ch <= 0:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="CANVAS_NOT_GROUNDED",
                failure_reason=f"Invalid grounded canvas dimensions: width={cw}, height={ch}",
            )

        # If strokes are not explicitly provided, generate basic normalized vectors for legacy shape
        if not strokes:
            shape = str(request.parameters.get("shape", "rectangle")).lower()
            strokes = self._generate_normalized_shape_vectors(shape)

        strokes_dispatched = 0

        try:
            for stroke in strokes:
                if not stroke or len(stroke) < 2:
                    continue

                # Pre-transformation and transformation
                transformed_points: List[Tuple[int, int]] = []
                for pt in stroke:
                    u, v = float(pt[0]), float(pt[1])
                    # Pre-transformation boundary check
                    u_clamped = max(0.0, min(1.0, u))
                    v_clamped = max(0.0, min(1.0, v))

                    px = int(cx + u_clamped * cw)
                    py = int(cy + v_clamped * ch)

                    # Post-transformation boundary assertion
                    px = max(cx, min(cx + cw, px))
                    py = max(cy, min(cy + ch, py))
                    transformed_points.append((px, py))

                start_x, start_y = transformed_points[0]
                await self._pointer.move_to(start_x, start_y)
                await asyncio.sleep(0.02)

                if hasattr(self._pointer, "mouse_down"):
                    await self._pointer.mouse_down(button="left")
                elif hasattr(self._pointer, "press_down"):
                    await self._pointer.press_down(button="left")
                elif hasattr(self._pointer, "button_down"):
                    await self._pointer.button_down()

                await asyncio.sleep(0.02)

                for next_x, next_y in transformed_points[1:]:
                    await self._pointer.move_to(next_x, next_y)
                    await asyncio.sleep(0.01)

                if hasattr(self._pointer, "mouse_up"):
                    await self._pointer.mouse_up(button="left")
                elif hasattr(self._pointer, "release_up"):
                    await self._pointer.release_up(button="left")
                elif hasattr(self._pointer, "button_up"):
                    await self._pointer.button_up()

                await asyncio.sleep(0.02)
                strokes_dispatched += 1

            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=True,
                execution_success=True,
                stage_status=StageOutcomeStatus.DISPATCHED,
                output={
                    "strokes_dispatched": strokes_dispatched,
                    "canvas_rect": [cx, cy, cw, ch],
                },
                evidence={
                    "strokes_count": strokes_dispatched,
                },
            )
        except Exception as ex:
            logger.warning("[DrawingExecutor] Stroke dispatch failed: %s", ex, exc_info=True)
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="STROKE_DISPATCH_FAILED",
                failure_reason=str(ex),
            )

    @staticmethod
    def _generate_normalized_shape_vectors(shape: str) -> List[List[Tuple[float, float]]]:
        """Generate generic normalized vectors in [0.0, 1.0] for fallback shapes."""
        if "rect" in shape or "square" in shape or "box" in shape:
            return [[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8), (0.2, 0.2)]]
        elif "triangle" in shape:
            return [[(0.5, 0.2), (0.8, 0.8), (0.2, 0.8), (0.5, 0.2)]]
        elif "line" in shape:
            return [[(0.2, 0.5), (0.8, 0.5)]]
        else:
            # Default normalized rectangle
            return [[(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75), (0.25, 0.25)]]
