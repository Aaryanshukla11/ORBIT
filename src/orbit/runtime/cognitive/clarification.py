"""Epistemic Ambiguity Resolution and User Clarification subsystem.

INVARIANT (ASTRA Dimension 4): Ambiguous or underspecified goals must halt physical execution
immediately. Speculative physical dispatch under ambiguity is strictly forbidden.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.task_understanding.models import (
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)


class ClarificationRequest(BaseModel):
    """Structured request for user disambiguation before any physical execution occurs."""

    request_id: str = Field(default_factory=lambda: f"clar_{uuid4().hex[:8]}")
    task_id: str
    original_prompt: str
    status: TaskUnderstandingStatus
    unresolved_constraints: List[str] = Field(default_factory=list)
    diagnostic_messages: List[str] = Field(default_factory=list)
    clarification_questions: List[str] = Field(default_factory=list)
    candidate_interpretations: List[str] = Field(default_factory=list)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClarificationResponse(BaseModel):
    """Disambiguation input provided by user or interactive supervisor."""

    request_id: str
    user_response: str
    selected_interpretation: Optional[str] = None
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClarificationManager:
    """Detects ambiguity, blocks physical execution, and generates structured clarification requests."""

    def is_clarification_needed(self, understanding: Optional[TaskUnderstandingResult]) -> bool:
        """Evaluate if task understanding exhibits unresolved ambiguity or unsupported goals."""
        if understanding is None:
            return True

        if understanding.status in (
            TaskUnderstandingStatus.AMBIGUOUS,
            TaskUnderstandingStatus.UNSUPPORTED,
            TaskUnderstandingStatus.INVALID,
            TaskUnderstandingStatus.FAILED,
        ):
            return True

        # Check for any individual intent that remains ambiguous
        if any(intent.is_ambiguous for intent in understanding.intents):
            return True

        return False

    def generate_clarification_request(
        self,
        task_id: str,
        prompt: str,
        understanding: TaskUnderstandingResult,
    ) -> ClarificationRequest:
        """Construct a structured clarification request detailing exactly what is ambiguous."""
        questions: List[str] = []
        candidates: List[str] = []

        for c in understanding.unresolved_constraints:
            questions.append(f"Please clarify: {c}")

        for intent in understanding.intents:
            if intent.is_ambiguous:
                reason = intent.unresolved_reason or f"Goal {intent.goal.value} is ambiguous"
                questions.append(f"For step '{intent.goal.value}': {reason}")
                if intent.constraints.application_name:
                    candidates.append(f"Perform action inside {intent.constraints.application_name}")

        if not questions and understanding.diagnostic_messages:
            for diag in understanding.diagnostic_messages:
                questions.append(f"Requirement unclear: {diag}")

        if not questions:
            questions.append(f"Could not determine concrete execution path for: '{prompt}'. Please provide specific application or target details.")

        return ClarificationRequest(
            task_id=task_id,
            original_prompt=prompt,
            status=understanding.status,
            unresolved_constraints=list(understanding.unresolved_constraints),
            diagnostic_messages=list(understanding.diagnostic_messages),
            clarification_questions=questions,
            candidate_interpretations=candidates,
        )

    def apply_clarification(self, original_prompt: str, clarification: ClarificationResponse) -> str:
        """Compose an unambiguous revised prompt incorporating the user's clarification."""
        addon = clarification.user_response.strip()
        if clarification.selected_interpretation:
            addon = f"{clarification.selected_interpretation}. {addon}".strip()
        return f"{original_prompt} (Clarification: {addon})"


__all__ = [
    "ClarificationManager",
    "ClarificationRequest",
    "ClarificationResponse",
]
