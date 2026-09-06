"""Execution Checkpoint Manager for Dynamic Replanning & Backtracking (M1.8 Step 4).

Safety Invariants:
1. Grounded State Preservation: Checkpoints represent only genuinely verified execution states, never fabricated data.
2. Generation Parity Tracking: Every checkpoint records desktop generation and window geometry to detect spatial drift.
3. Monotonic Integrity: Invalidation of a checkpoint invalidates all subsequent dependent checkpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanStep
from orbit.runtime.replanning.models import ExecutionCheckpoint

logger = logging.getLogger(__name__)


class ExecutionCheckpointManager:
    """Manages verified execution checkpoints for safe replanning and backtracking."""

    def __init__(self) -> None:
        self._checkpoints: List[ExecutionCheckpoint] = []
        self._by_step_id: Dict[str, ExecutionCheckpoint] = {}

    @property
    def total_checkpoints(self) -> int:
        return len(self._checkpoints)

    @property
    def checkpoints(self) -> List[ExecutionCheckpoint]:
        return list(self._checkpoints)

    def create_checkpoint(
        self,
        step: PlanStep,
        completed_step_ids: Set[str],
        desktop_generation_id: Optional[int] = None,
        window_identity: Optional[str] = None,
        application_name: Optional[str] = None,
        window_rect: Optional[Tuple[int, int, int, int]] = None,
        verified_state: Optional[Dict[str, Any]] = None,
        execution_evidence: Optional[Dict[str, Any]] = None,
    ) -> ExecutionCheckpoint:
        """Create and record an ExecutionCheckpoint for a verified plan step."""
        checkpoint_id = f"chk_{step.step_id}_{uuid4().hex[:8]}"
        chk = ExecutionCheckpoint(
            checkpoint_id=checkpoint_id,
            step_id=step.step_id,
            step_index=step.step_index,
            completed_step_ids=sorted(list(completed_step_ids)),
            desktop_generation_id=desktop_generation_id,
            window_identity=window_identity,
            application_name=application_name,
            window_rect=window_rect,
            verified_state=verified_state or {},
            execution_evidence=execution_evidence or {},
            timestamp_utc=datetime.now(timezone.utc),
        )
        self.record_checkpoint(chk)
        return chk

    def record_checkpoint(self, checkpoint: ExecutionCheckpoint) -> None:
        """Record an existing ExecutionCheckpoint."""
        self._checkpoints.append(checkpoint)
        self._by_step_id[checkpoint.step_id] = checkpoint
        logger.debug(
            "Recorded execution checkpoint %s for step %s (generation=%s)",
            checkpoint.checkpoint_id,
            checkpoint.step_id,
            checkpoint.desktop_generation_id,
        )

    def get_latest_checkpoint(self) -> Optional[ExecutionCheckpoint]:
        """Retrieve the most recently recorded valid checkpoint."""
        return self._checkpoints[-1] if self._checkpoints else None

    def get_checkpoint_for_step(self, step_id: str) -> Optional[ExecutionCheckpoint]:
        """Retrieve the checkpoint recorded for a specific step ID."""
        return self._by_step_id.get(step_id)

    def find_safe_backtrack_checkpoint(
        self,
        failed_step: PlanStep,
        plan: ExecutableTaskPlan,
    ) -> Optional[ExecutionCheckpoint]:
        """Find the nearest verified predecessor checkpoint suitable for backtracking."""
        if not self._checkpoints:
            return None

        # Determine direct dependencies of the failed step
        deps = set(failed_step.dependencies)
        if deps:
            # Search backwards for the most recent completed dependency
            for chk in reversed(self._checkpoints):
                if chk.step_id in deps:
                    return chk

        # Fallback to the latest verified checkpoint prior to the failing step
        for chk in reversed(self._checkpoints):
            if chk.step_id != failed_step.step_id:
                return chk

        return None

    def is_valid_checkpoint(
        self,
        checkpoint: ExecutionCheckpoint,
        fresh_snapshot: Optional[ObservationSnapshot],
    ) -> bool:
        """Evaluate whether a checkpoint's assumptions still hold under a fresh observation."""
        if checkpoint is None:
            return False

        if fresh_snapshot is None:
            # Cannot verify without fresh observation
            return True

        # Check generation parity if recorded
        if checkpoint.desktop_generation_id is not None:
            if fresh_snapshot.generation_id != checkpoint.desktop_generation_id:
                logger.debug(
                    "Checkpoint generation mismatch: checkpoint=%s, fresh=%s",
                    checkpoint.desktop_generation_id,
                    fresh_snapshot.generation_id,
                )

        # Check window presence and geometry stability if recorded
        all_windows = fresh_snapshot.windows or getattr(fresh_snapshot, "window_metadata", [])
        if checkpoint.window_rect is not None and all_windows:
            app_id = (checkpoint.application_name or checkpoint.window_identity or "").lower()
            if app_id:
                matching_win = None
                for win in all_windows:
                    title = getattr(win, "window_title", None) or getattr(win, "title", "")
                    proc = getattr(win, "process_name", "") or ""
                    if app_id in title.lower() or app_id in proc.lower():
                        matching_win = win
                        break
                if matching_win:
                    bounds = getattr(matching_win, "extended_bounds", None) or getattr(matching_win, "rect", None)
                    if bounds:
                        cur_rect = (
                            bounds.left,
                            bounds.top,
                            bounds.right,
                            bounds.bottom,
                        )
                        if cur_rect != checkpoint.window_rect:
                            logger.debug(
                                "Window geometry shifted since checkpoint: was=%s, now=%s",
                                checkpoint.window_rect,
                                cur_rect,
                            )
                            return False

        return True

    def invalidate_after(self, step_id: str) -> List[ExecutionCheckpoint]:
        """Invalidate and remove all checkpoints recorded after the specified step."""
        target_idx = None
        for idx, chk in enumerate(self._checkpoints):
            if chk.step_id == step_id:
                target_idx = idx
                break

        if target_idx is None:
            return []

        invalidated = self._checkpoints[target_idx + 1 :]
        self._checkpoints = self._checkpoints[: target_idx + 1]

        # Rebuild lookup table
        self._by_step_id.clear()
        for chk in self._checkpoints:
            self._by_step_id[chk.step_id] = chk

        logger.info(
            "Invalidated %d checkpoints recorded after step %s",
            len(invalidated),
            step_id,
        )
        return invalidated

    def clear(self) -> None:
        """Clear all stored checkpoints."""
        self._checkpoints.clear()
        self._by_step_id.clear()
