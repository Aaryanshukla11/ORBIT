"""Validation and epistemic status assignment for structured task understanding."""

from __future__ import annotations

from typing import List, Tuple
from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    StructuredTaskIntent,
    TaskGoal,
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)


class TaskUnderstandingValidator:
    """Validates extracted intent sequences and assigns truthful epistemic status."""

    def validate(
        self,
        raw_request: RawTaskRequest,
        intents: List[StructuredTaskIntent],
    ) -> TaskUnderstandingResult:
        """Validate intent sequence and construct final TaskUnderstandingResult."""
        raw_text = raw_request.raw_text.strip()
        diagnostics: List[str] = []
        unresolved: List[str] = []

        # 1. Check for empty or invalid input
        if not raw_text:
            return TaskUnderstandingResult(
                request_id=raw_request.task_id,
                raw_request=raw_request,
                status=TaskUnderstandingStatus.INVALID,
                intents=[],
                unresolved_constraints=["Task request prompt is empty or whitespace-only"],
                diagnostic_messages=["Rejected empty prompt during validation"],
            )

        if not intents:
            return TaskUnderstandingResult(
                request_id=raw_request.task_id,
                raw_request=raw_request,
                status=TaskUnderstandingStatus.FAILED,
                intents=[],
                unresolved_constraints=["No intents could be extracted from request"],
                diagnostic_messages=["Parser produced zero intents"],
            )

        # 2. Check each intent
        has_unknown = False
        has_ambiguous = False
        understood_count = 0

        for intent in intents:
            if intent.goal in {TaskGoal.UNKNOWN, TaskGoal.UNSUPPORTED}:
                has_unknown = True
                msg = f"Intent [{intent.sequence_index}] has unsupported or unknown goal '{intent.goal.value}'"
                unresolved.append(msg)
                diagnostics.append(msg)
            elif intent.is_ambiguous:
                has_ambiguous = True
                reason = intent.unresolved_reason or "Unresolved target or parameter ambiguity"
                msg = f"Intent [{intent.sequence_index}] is ambiguous: {reason}"
                unresolved.append(msg)
                diagnostics.append(msg)
            else:
                understood_count += 1

        # 3. Determine overall status
        if has_unknown and understood_count == 0:
            status = TaskUnderstandingStatus.UNSUPPORTED
        elif has_unknown and understood_count > 0:
            status = TaskUnderstandingStatus.PARTIALLY_UNDERSTOOD
        elif has_ambiguous and understood_count == 0:
            status = TaskUnderstandingStatus.AMBIGUOUS
        elif has_ambiguous and understood_count > 0:
            status = TaskUnderstandingStatus.PARTIALLY_UNDERSTOOD
        else:
            status = TaskUnderstandingStatus.UNDERSTOOD

        diagnostics.append(
            f"Validation complete: status={status.value}, total_intents={len(intents)}, understood={understood_count}"
        )

        return TaskUnderstandingResult(
            request_id=raw_request.task_id,
            raw_request=raw_request,
            status=status,
            intents=intents,
            unresolved_constraints=unresolved,
            diagnostic_messages=diagnostics,
        )
