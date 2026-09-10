"""Canvas Drawing Environment Provider (ASTRA-6 Canonical).

Executes DRAW_STROKES by transforming normalized canvas-local (u, v) geometry
into grounded canvas screen pixels and dispatching pointer drag strokes.
All physical execution remains under the authority of PrimitiveExecutionController.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional, Tuple

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.environment.registry import EnvironmentProvider, ProviderExecutionResult

logger = logging.getLogger(__name__)


class CanvasDrawingProvider(EnvironmentProvider):
    """Canonical ASTRA Environment Provider executing canvas vector drawing strokes."""

    def __init__(self, pointer: Optional[Any] = None) -> None:
        self._pointer = pointer

    def set_pointer(self, pointer: Any) -> None:
        """Attach or update the PointerCapability adapter."""
        self._pointer = pointer

    @property
    def pointer(self) -> Optional[Any]:
        return self._pointer

    @property
    def provider_id(self) -> str:
        return "canvas_drawing_provider"

    @property
    def supported_features(self) -> List[str]:
        return ["canvas_drawing", "normalized_strokes", "vector_rasterization", "drag_strokes"]

    async def is_available(self) -> bool:
        """Check if pointer capability adapter is attached."""
        return self._pointer is not None

    async def check_permissions(self, action: AbstractAction) -> bool:
        """Verify parameters contain valid strokes or shape vectors."""
        if action.action_type != AbstractActionType.DRAW_STROKES:
            return False
        params = action.parameters or {}
        strokes = params.get("strokes")
        shape = params.get("shape")
        return bool(strokes is not None or shape is not None)

    def validate_strokes(self, strokes: Any) -> Tuple[bool, Optional[str]]:
        """Strict fail-closed validation of normalized (u, v) stroke vectors."""
        if not isinstance(strokes, list):
            return False, "'strokes' must be a list of stroke point sequences"

        for s_idx, stroke in enumerate(strokes):
            if not isinstance(stroke, list):
                return False, f"Stroke {s_idx} must be a list of 2-numeric points (u, v)"
            if len(stroke) < 2:
                continue
            for p_idx, pt in enumerate(stroke):
                if isinstance(pt, dict):
                    return False, f"Stroke {s_idx} point {p_idx} cannot be a dictionary"
                if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                    return False, f"Stroke {s_idx} point {p_idx} must be a 2-tuple (u, v)"
                u, v = pt
                if not isinstance(u, (int, float)) or not isinstance(v, (int, float)):
                    return False, f"Stroke {s_idx} point {p_idx} coordinates must be numbers"
                if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
                    return False, f"Stroke {s_idx} point {p_idx} ({u}, {v}) violates normalized bounds [0.0, 1.0]"

        return True, None

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        """Execute DRAW_STROKES via pointer drag operations bounded by canvas geometry."""
        if self._pointer is None:
            logger.warning("[CanvasDrawingProvider] Execution rejected: PointerCapability missing (Fail-Closed)")
            return ProviderExecutionResult(
                success=False,
                error="REQUIRED_ADAPTER_MISSING: PointerCapability adapter is not provided",
                metadata={"provider": self.provider_id},
            )

        params = action.parameters or {}
        strokes = params.get("strokes")
        canvas_rect = params.get("canvas_rect")

        # Fallback to normalized shape vectors if strokes not explicit
        if not strokes and params.get("shape"):
            shape = str(params.get("shape", "rectangle")).lower()
            strokes = self._generate_normalized_shape_vectors(shape)

        if strokes is None:
            return ProviderExecutionResult(
                success=False,
                error="Missing required 'strokes' or 'shape' parameter in DRAW_STROKES action",
                metadata={"provider": self.provider_id},
            )

        # Validate strokes
        is_valid, val_err = self.validate_strokes(strokes)
        if not is_valid:
            return ProviderExecutionResult(
                success=False,
                error=f"STROKE_VALIDATION_FAILED: {val_err}",
                metadata={"provider": self.provider_id},
            )

        # Resolve grounded canvas bounding box [cx, cy, cw, ch]
        if canvas_rect and isinstance(canvas_rect, (list, tuple)) and len(canvas_rect) == 4:
            cx, cy, cw, ch = [int(v) for v in canvas_rect]
        else:
            # Safe default desktop center canvas
            cx, cy, cw, ch = 300, 200, 800, 600

        if cw <= 0 or ch <= 0:
            return ProviderExecutionResult(
                success=False,
                error=f"CANVAS_NOT_GROUNDED: Invalid canvas dimensions width={cw}, height={ch}",
                metadata={"provider": self.provider_id},
            )

        strokes_dispatched = 0

        try:
            for stroke in strokes:
                if not stroke or len(stroke) < 2:
                    continue

                # Transform normalized (u, v) points to physical pixels with strict boundary clamping
                transformed_points: List[Tuple[int, int]] = []
                for pt in stroke:
                    u, v = float(pt[0]), float(pt[1])
                    u_clamped = max(0.0, min(1.0, u))
                    v_clamped = max(0.0, min(1.0, v))

                    px = int(cx + u_clamped * cw)
                    py = int(cy + v_clamped * ch)

                    px = max(cx, min(cx + cw, px))
                    py = max(cy, min(cy + ch, py))
                    transformed_points.append((px, py))

                start_x, start_y = transformed_points[0]
                await self._pointer.move_to(start_x, start_y)
                await asyncio.sleep(0.02)

                # Mouse down
                btn_down = getattr(self._pointer, "button_down", None)
                press_down = getattr(self._pointer, "press_down", None)
                mouse_down = getattr(self._pointer, "mouse_down", None)

                if callable(btn_down) and hasattr(self._pointer, "button_down"):
                    res = btn_down()
                    if inspect.isawaitable(res):
                        await res
                elif callable(press_down) and hasattr(self._pointer, "press_down"):
                    res = press_down(button="left")
                    if inspect.isawaitable(res):
                        await res
                elif callable(mouse_down) and hasattr(self._pointer, "mouse_down"):
                    res = mouse_down(button="left")
                    if inspect.isawaitable(res):
                        await res

                await asyncio.sleep(0.02)

                # Drag stroke
                for next_x, next_y in transformed_points[1:]:
                    await self._pointer.move_to(next_x, next_y)
                    await asyncio.sleep(0.01)

                # Mouse up
                btn_up = getattr(self._pointer, "button_up", None)
                release_up = getattr(self._pointer, "release_up", None)
                mouse_up = getattr(self._pointer, "mouse_up", None)

                if callable(btn_up) and hasattr(self._pointer, "button_up"):
                    res = btn_up()
                    if inspect.isawaitable(res):
                        await res
                elif callable(release_up) and hasattr(self._pointer, "release_up"):
                    res = release_up(button="left")
                    if inspect.isawaitable(res):
                        await res
                elif callable(mouse_up) and hasattr(self._pointer, "mouse_up"):
                    res = mouse_up(button="left")
                    if inspect.isawaitable(res):
                        await res

                await asyncio.sleep(0.02)
                strokes_dispatched += 1

            return ProviderExecutionResult(
                success=True,
                output={
                    "strokes_dispatched": strokes_dispatched,
                    "canvas_rect": [cx, cy, cw, ch],
                },
                metadata={
                    "provider": self.provider_id,
                    "strokes_count": strokes_dispatched,
                },
            )

        except Exception as ex:
            logger.warning("[CanvasDrawingProvider] Stroke dispatch error: %s", ex, exc_info=True)
            return ProviderExecutionResult(
                success=False,
                error=f"STROKE_DISPATCH_FAILED: {ex}",
                metadata={"provider": self.provider_id},
            )

    @staticmethod
    def _generate_normalized_shape_vectors(shape: str) -> List[List[Tuple[float, float]]]:
        """Generate generic normalized vector strokes for basic fallback shapes."""
        if "rect" in shape or "square" in shape or "box" in shape:
            return [[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8), (0.2, 0.2)]]
        elif "triangle" in shape:
            return [[(0.5, 0.2), (0.8, 0.8), (0.2, 0.8), (0.5, 0.2)]]
        elif "line" in shape:
            return [[(0.2, 0.5), (0.8, 0.5)]]
        elif "circle" in shape or "oval" in shape:
            import math
            pts = []
            for i in range(17):
                angle = 2 * math.pi * (i / 16.0)
                pts.append((0.5 + 0.3 * math.cos(angle), 0.5 + 0.3 * math.sin(angle)))
            return [pts]
        else:
            return [[(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75), (0.25, 0.25)]]


__all__ = [
    "CanvasDrawingProvider",
]
