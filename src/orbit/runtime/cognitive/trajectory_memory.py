"""Trajectory Memory and Anti-Looping Heuristic Engine (Phase 2G.1).

Stores executed action trajectories, maps successful patterns, records dead-ends,
and enforces loop-detection thresholds to prevent oscillating or trapped agent states.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.cognitive.models import CognitiveStepResult

logger = logging.getLogger(__name__)


class FailedPattern(BaseModel):
    """A recorded action sequence or discrete action that failed verification."""

    pattern_id: str = Field(default_factory=lambda: f"fail_{uuid4().hex[:8]}")
    action_type: str
    target_signature: str
    parameters_summary: str
    failure_reason: str
    failure_count: int = 1
    first_seen_step: int
    last_seen_step: int


class SuccessfulPattern(BaseModel):
    """A verified action sequence or discrete action that produced intended state transition."""

    pattern_id: str = Field(default_factory=lambda: f"succ_{uuid4().hex[:8]}")
    action_type: str
    target_signature: str
    parameters_summary: str
    expected_effect: str
    step_index: int


class TrajectoryMemory:
    """Maintains task-scoped trajectory history, detecting loops and dead-ends."""

    def __init__(
        self,
        loop_threshold: int = 3,
        oscillation_threshold: int = 4,
    ) -> None:
        self.loop_threshold = max(2, loop_threshold)
        self.oscillation_threshold = max(3, oscillation_threshold)

        self._action_signatures: List[str] = []
        self._action_history_records: List[CognitiveStepResult] = []
        self._failed_patterns: Dict[str, FailedPattern] = {}
        self._successful_patterns: List[SuccessfulPattern] = []
        self._visited_window_signatures: Set[str] = set()
        self._consecutive_failure_count: int = 0

    @property
    def total_steps_recorded(self) -> int:
        return len(self._action_history_records)

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failure_count

    def compute_action_signature(self, action: AbstractAction) -> str:
        """Create canonical deterministic hash/string signature for an abstract action."""
        act_type = action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type)
        t_name = action.target.name if action.target else ""
        t_role = action.target.role if action.target else ""
        t_ctx = action.target.context if action.target else ""
        
        # Canonicalize parameters
        params_json = json.dumps(action.parameters or {}, sort_keys=True)
        return f"{act_type}|{t_name}|{t_role}|{t_ctx}|{params_json}"

    def record_step(
        self,
        step: CognitiveStepResult,
        active_window_title: Optional[str] = None,
    ) -> None:
        """Record an executed step and update loop/failure indices."""
        self._action_history_records.append(step)

        if active_window_title:
            self._visited_window_signatures.add(active_window_title.strip().lower())

        act = step.action_dispatched
        if not act:
            return

        sig = self.compute_action_signature(act)
        self._action_signatures.append(sig)

        if step.outcome_verified:
            self._consecutive_failure_count = 0
            self._successful_patterns.append(
                SuccessfulPattern(
                    action_type=act.action_type.value if hasattr(act.action_type, "value") else str(act.action_type),
                    target_signature=f"{act.target.name if act.target else ''} ({act.target.role if act.target else ''})",
                    parameters_summary=str(act.parameters),
                    expected_effect=act.expected_effect,
                    step_index=step.step_index,
                )
            )
        else:
            self._consecutive_failure_count += 1
            reason = (step.execution_result.error_message if step.execution_result else "") or "Verification failed"
            if sig in self._failed_patterns:
                fp = self._failed_patterns[sig]
                fp.failure_count += 1
                fp.last_seen_step = step.step_index
                fp.failure_reason = reason
            else:
                self._failed_patterns[sig] = FailedPattern(
                    action_type=act.action_type.value if hasattr(act.action_type, "value") else str(act.action_type),
                    target_signature=f"{act.target.name if act.target else ''} ({act.target.role if act.target else ''})",
                    parameters_summary=str(act.parameters),
                    failure_reason=reason,
                    first_seen_step=step.step_index,
                    last_seen_step=step.step_index,
                )

    def is_looping_detected(self) -> Tuple[bool, Optional[str]]:
        """Check if recent actions constitute an infinite loop or unproductive oscillation."""
        if len(self._action_signatures) < self.loop_threshold:
            return False, None

        # 1. Exact immediate repetition check (e.g. A -> A -> A)
        recent_window = self._action_signatures[-self.loop_threshold :]
        if len(set(recent_window)) == 1:
            sig = recent_window[0]
            return True, f"Repetitive action loop detected: identical action attempted {self.loop_threshold} consecutive times ({sig[:40]})."

        # 2. Alternating oscillation check (e.g. A -> B -> A -> B)
        if len(self._action_signatures) >= self.oscillation_threshold:
            osc_window = self._action_signatures[-self.oscillation_threshold :]
            if len(set(osc_window)) == 2 and osc_window[0] == osc_window[2] and osc_window[1] == osc_window[3]:
                return True, f"Oscillation loop detected: alternating between two actions 4 times."

        return False, None

    def is_known_dead_end(self, action: AbstractAction) -> Tuple[bool, Optional[str]]:
        """Check if proposed action is a known failing dead-end."""
        sig = self.compute_action_signature(action)
        if sig in self._failed_patterns:
            fp = self._failed_patterns[sig]
            if fp.failure_count >= 2:
                return True, f"Action is a known dead-end: failed {fp.failure_count} times previously ({fp.failure_reason})."
        return False, None

    def get_recovery_guidance(self) -> Optional[str]:
        """Generate targeted contextual guidance for the decision engine if trapped or failing."""
        is_loop, loop_msg = self.is_looping_detected()
        if is_loop and loop_msg:
            return f"LOOP WARNING: {loop_msg}. Switch strategy immediately (e.g. focus window, use hotkey, or verify text)."

        if self._consecutive_failure_count >= 2:
            return (
                f"FAILURE WARNING: Last {self._consecutive_failure_count} actions failed verification. "
                "Re-examine current window title and visible UI elements before retrying."
            )

        return None

    def clear(self) -> None:
        """Reset trajectory memory."""
        self._action_signatures.clear()
        self._action_history_records.clear()
        self._failed_patterns.clear()
        self._successful_patterns.clear()
        self._visited_window_signatures.clear()
        self._consecutive_failure_count = 0
