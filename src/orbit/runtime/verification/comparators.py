"""Verification comparators and strategy evaluators.

Re-exports comparator functions and evidence summarization for M1.6 Step 2.
"""

from orbit.runtime.verification.evidence import summarize_observation_evidence
from orbit.runtime.verification.strategies import (
    evaluate_accessibility_state_change,
    evaluate_observation_state_delta,
    evaluate_window_state_change,
)

__all__ = [
    "evaluate_accessibility_state_change",
    "evaluate_observation_state_delta",
    "evaluate_window_state_change",
    "summarize_observation_evidence",
]
