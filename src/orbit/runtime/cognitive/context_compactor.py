"""Context Compaction and Memory Compression Engine (Phase 2G.1).

Transforms long-horizon action histories into structured, token-bounded factual representations.
Preserves critical semantic intent, milestone progression, and recent state deltas.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.cognitive.models import CognitiveStepResult

logger = logging.getLogger(__name__)


class CompactedContext(BaseModel):
    """Result of context compaction with bounded size metrics."""

    summary_text: str = Field(..., description="Formatted string for reasoning context injection")
    total_steps: int = Field(..., description="Total steps in raw history")
    compacted_steps_count: int = Field(..., description="Number of steps compacted into summaries")
    detailed_steps_count: int = Field(..., description="Number of steps kept in raw detail")
    char_count: int = Field(..., description="Character length of summary text")


class ContextCompactor:
    """Intelligently summarizes historical steps to maintain sub-linear context growth."""

    def __init__(
        self,
        max_detailed_steps: int = 4,
        max_characters: int = 3500,
    ) -> None:
        self.max_detailed_steps = max(2, max_detailed_steps)
        self.max_characters = max(100, max_characters)

    def compact_history(
        self,
        step_history: List[CognitiveStepResult],
        current_step: int,
        active_subgoals_summary: Optional[str] = None,
        key_facts: Optional[Dict[str, Any]] = None,
    ) -> CompactedContext:
        """Compress execution history into bounded markdown summary."""
        total_steps = len(step_history)
        if not step_history:
            text = "  Initial step: No actions dispatched yet."
            return CompactedContext(
                summary_text=text,
                total_steps=0,
                compacted_steps_count=0,
                detailed_steps_count=0,
                char_count=len(text),
            )

        if total_steps <= self.max_detailed_steps:
            # Short history: format all steps directly
            lines: List[str] = []
            for s in step_history:
                lines.append(self._format_detailed_step(s))
            summary_str = "\n".join(lines)
            return CompactedContext(
                summary_text=summary_str,
                total_steps=total_steps,
                compacted_steps_count=0,
                detailed_steps_count=total_steps,
                char_count=len(summary_str),
            )

        # Long history: split into older (compacted) and recent (detailed)
        older_steps = step_history[:-self.max_detailed_steps]
        recent_steps = step_history[-self.max_detailed_steps:]

        lines: List[str] = []

        # 1. High-level Milestone / Subgoal Progress if provided
        if active_subgoals_summary:
            lines.append(f"=== MILESTONE PROGRESS ===\n{active_subgoals_summary}")

        # 2. Key Learned Facts
        if key_facts:
            facts_str = ", ".join(f"{k}='{v}'" for k, v in key_facts.items())
            lines.append(f"=== ESTABLISHED FACTS ===\n  {facts_str}")

        # 3. Compacted Older Steps Summary
        compacted_summary = self._summarize_step_slice(older_steps)
        lines.append(f"=== PRIOR EXECUTION PHASES (Steps 0 to {older_steps[-1].step_index}) ===\n{compacted_summary}")

        # 4. Detailed Recent Steps
        lines.append(f"=== RECENT ACTIONS (Steps {recent_steps[0].step_index} to {recent_steps[-1].step_index}) ===")
        for s in recent_steps:
            lines.append(self._format_detailed_step(s))

        raw_output = "\n".join(lines)

        # Enforce hard character limit
        if len(raw_output) > self.max_characters:
            trunc_msg = "\n  [... older context truncated ...]"
            keep_len = max(0, self.max_characters - len(trunc_msg))
            raw_output = raw_output[:keep_len] + trunc_msg

        return CompactedContext(
            summary_text=raw_output,
            total_steps=total_steps,
            compacted_steps_count=len(older_steps),
            detailed_steps_count=len(recent_steps),
            char_count=len(raw_output),
        )

    def _summarize_step_slice(self, steps: List[CognitiveStepResult]) -> str:
        """Aggregate multiple steps into concise categorical statements."""
        if not steps:
            return "  None"

        # Categorize action types and verification status
        action_counts: Dict[str, int] = {}
        verified_count = 0
        failed_count = 0
        targets_seen: List[str] = []

        for s in steps:
            act = s.action_dispatched
            act_name = act.action_type.value if act and hasattr(act.action_type, "value") else "UNKNOWN"
            action_counts[act_name] = action_counts.get(act_name, 0) + 1

            if s.outcome_verified:
                verified_count += 1
            else:
                failed_count += 1

            if act and act.target and act.target.name and act.target.name not in targets_seen:
                targets_seen.append(act.target.name)

        summary_parts: List[str] = []
        for act_name, count in sorted(action_counts.items()):
            summary_parts.append(f"{count}x {act_name}")

        target_str = f" targeting [{', '.join(targets_seen[:5])}]" if targets_seen else ""
        return (
            f"  - Completed {len(steps)} steps ({', '.join(summary_parts)}){target_str}\n"
            f"  - Outcomes: {verified_count} verified transitions, {failed_count} unverified/retried"
        )

    def _format_detailed_step(self, step: CognitiveStepResult) -> str:
        """Format a single recent step with complete operational context."""
        act = step.action_dispatched
        if not act:
            return f"  Step {step.step_index}: NO_ACTION"

        target_name = act.target.name if act.target else ""
        target_role = f" [{act.target.role}]" if (act.target and act.target.role) else ""
        params_str = f", params={act.parameters}" if act.parameters else ""
        v_str = "EFFECT_VERIFIED" if step.outcome_verified else "UNVERIFIED"
        err_str = f" [Error: {step.execution_result.error_message}]" if (step.execution_result and step.execution_result.error_message) else ""

        return f"  Step {step.step_index}: {act.action_type.value}('{target_name}'{target_role}{params_str}) -> {v_str}{err_str}"
