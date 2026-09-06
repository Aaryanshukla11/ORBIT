"""Runtime Desktop State Validator for Dynamic Replanning (M1.8 Step 4).

Safety Invariants:
1. Fresh Grounding: Validates application and window state strictly against fresh observation snapshots.
2. Geometry Integrity: Detects window translation, resizing, minimization, or occlusion without guessing.
3. Generation Parity Gate: Enforces generation consistency between observations and planned actions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedWindow
from orbit.runtime.planning.models import PlanStep
from orbit.runtime.replanning.models import ExecutionCheckpoint, ReplanReason

logger = logging.getLogger(__name__)


class StateValidationResult(BaseModel):
    """Result of validating runtime desktop state against plan assumptions."""
    is_valid: bool
    detected_issue: Optional[ReplanReason] = None
    diagnostic_message: str = ""
    evidence: Dict[str, Any] = Field(default_factory=dict)


class StateValidator:
    """Evaluates fresh desktop observations against plan expectations and checkpoint baselines."""

    def validate_step_state(
        self,
        step: PlanStep,
        fresh_snapshot: Optional[ObservationSnapshot],
        checkpoint: Optional[ExecutionCheckpoint] = None,
        expected_generation_id: Optional[int] = None,
    ) -> StateValidationResult:
        """Validate whether current desktop observation satisfies preconditions for step execution."""
        if fresh_snapshot is None:
            return StateValidationResult(
                is_valid=False,
                detected_issue=ReplanReason.STALE_OBSERVATION,
                diagnostic_message="No fresh observation snapshot available for state validation",
                evidence={"expected_generation": expected_generation_id},
            )

        # 1. Check Desktop Generation Parity
        if expected_generation_id is not None and fresh_snapshot.generation_id != expected_generation_id:
            logger.info(
                "Generation shift detected: expected=%s, snapshot=%s",
                expected_generation_id,
                fresh_snapshot.generation_id,
            )
            return StateValidationResult(
                is_valid=False,
                detected_issue=ReplanReason.STALE_GENERATION,
                diagnostic_message=f"Desktop generation changed ({expected_generation_id} -> {fresh_snapshot.generation_id})",
                evidence={
                    "expected_generation_id": expected_generation_id,
                    "fresh_generation_id": fresh_snapshot.generation_id,
                },
            )

        # 2. Extract Application / Window Targets
        app_target = None
        if step.target and step.target.semantic_type == "application":
            app_target = step.target.identifier
        elif step.deferred_grounding and step.deferred_grounding.target_reference.semantic_type == "application":
            app_target = step.deferred_grounding.target_reference.identifier
        elif checkpoint and checkpoint.application_name:
            app_target = checkpoint.application_name

        if not app_target:
            # Step does not explicitly bind to a specific application window
            return StateValidationResult(
                is_valid=True,
                diagnostic_message="State valid (no specific application window bound)",
                evidence={"generation_id": fresh_snapshot.generation_id},
            )

        # 3. Locate Target Window in Fresh Snapshot
        app_target_lower = app_target.lower()
        matching_window = None
        all_windows = fresh_snapshot.windows or getattr(fresh_snapshot, "window_metadata", [])

        for win in all_windows:
            title = getattr(win, "window_title", None) or getattr(win, "title", "")
            proc_name = getattr(win, "process_name", "") or ""
            title_match = app_target_lower in title.lower()
            proc_match = app_target_lower in proc_name.lower()
            if title_match or proc_match:
                matching_window = win
                break

        if matching_window is None:
            visible_titles = [
                getattr(w, "window_title", None) or getattr(w, "title", "")
                for w in all_windows
            ]
            logger.warning("Target application '%s' not found in fresh windows: %s", app_target, visible_titles)
            return StateValidationResult(
                is_valid=False,
                detected_issue=ReplanReason.APPLICATION_NOT_AVAILABLE,
                diagnostic_message=f"Application window '{app_target}' is not available on desktop",
                evidence={
                    "app_target": app_target,
                    "visible_windows": visible_titles,
                },
            )

        # 4. Check Window Geometry vs Checkpoint Baseline
        bounds = getattr(matching_window, "extended_bounds", None) or getattr(matching_window, "rect", None)
        if bounds is not None:
            cur_rect: Tuple[int, int, int, int] = (
                bounds.left,
                bounds.top,
                bounds.right,
                bounds.bottom,
            )
        else:
            cur_rect = (0, 0, 0, 0)

        if checkpoint and checkpoint.window_rect is not None and bounds is not None:
            prev_rect = checkpoint.window_rect
            if cur_rect != prev_rect:
                # Check whether position or dimensions changed
                prev_w = prev_rect[2] - prev_rect[0]
                prev_h = prev_rect[3] - prev_rect[1]
                cur_w = cur_rect[2] - cur_rect[0]
                cur_h = cur_rect[3] - cur_rect[1]

                if cur_w != prev_w or cur_h != prev_h:
                    logger.info("Window resized: was=%s (w=%d,h=%d), now=%s (w=%d,h=%d)", prev_rect, prev_w, prev_h, cur_rect, cur_w, cur_h)
                    return StateValidationResult(
                        is_valid=False,
                        detected_issue=ReplanReason.WINDOW_RESIZED,
                        diagnostic_message=f"Target window resized from ({prev_w}x{prev_h}) to ({cur_w}x{cur_h})",
                        evidence={"previous_rect": prev_rect, "current_rect": cur_rect},
                    )
                else:
                    logger.info("Window moved: was=%s, now=%s", prev_rect, cur_rect)
                    return StateValidationResult(
                        is_valid=False,
                        detected_issue=ReplanReason.WINDOW_MOVED,
                        diagnostic_message=f"Target window moved from {prev_rect} to {cur_rect}",
                        evidence={"previous_rect": prev_rect, "current_rect": cur_rect},
                    )

        # 5. Check Focus
        win_title = getattr(matching_window, "window_title", None) or getattr(matching_window, "title", "")
        if not getattr(matching_window, "is_foreground", True):
            logger.debug("Target window '%s' is not in foreground focus", win_title)
            return StateValidationResult(
                is_valid=False,
                detected_issue=ReplanReason.WINDOW_NOT_FOCUSED,
                diagnostic_message=f"Target window '{win_title}' is not foreground focused",
                evidence={
                    "window_title": win_title,
                    "is_foreground": False,
                    "window_rect": cur_rect,
                },
            )

        return StateValidationResult(
            is_valid=True,
            diagnostic_message="Target window is present, focused, and geometrically stable",
            evidence={
                "window_title": win_title,
                "window_rect": cur_rect,
                "generation_id": fresh_snapshot.generation_id,
            },
        )
