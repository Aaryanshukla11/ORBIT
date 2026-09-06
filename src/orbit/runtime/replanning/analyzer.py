"""Compatibility module for Failure Classifier (M1.8 Step 4)."""

from orbit.runtime.replanning.failure_classifier import (
    ExecutionFailureAnalyzer,
    FailureClassifier,
)

__all__ = ["ExecutionFailureAnalyzer", "FailureClassifier"]
