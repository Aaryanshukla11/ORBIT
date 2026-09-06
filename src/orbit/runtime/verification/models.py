"""Domain models and contracts for post-action verification."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    """Canonical verification statuses required by M1.6 Step 2."""

    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"
    STALE = "STALE"
    CANCELLED = "CANCELLED"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


class VerificationOutcome(str, Enum):
    """Authoritative discrete outcome of post-action verification."""

    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"   # Strong evidence confirms the expected state transition occurred
    VERIFIED_FAILURE = "VERIFIED_FAILURE"   # Strong evidence demonstrates the expected outcome did not occur or failed
    INCONCLUSIVE = "INCONCLUSIVE"           # Insufficient or ambiguous evidence exists to verify outcome
    STALE_EVIDENCE = "STALE_EVIDENCE"       # Evidence cannot safely be compared (freshness or generation mismatch)
    UNSUPPORTED = "UNSUPPORTED"             # Requested verification strategy is not supported by available capabilities


class VerificationStrategy(str, Enum):
    """Strategy category for verifying an action outcome."""

    ACCESSIBILITY_STATE_CHANGE = "ACCESSIBILITY_STATE_CHANGE"  # Compare MSAA / UI Automation state delta
    WINDOW_STATE_CHANGE = "WINDOW_STATE_CHANGE"                # Compare top-level window / focus state delta
    TARGET_PRESENCE_CHANGE = "TARGET_PRESENCE_CHANGE"          # Verify target appearance, dismissal, or presence
    OBSERVATION_STATE_DELTA = "OBSERVATION_STATE_DELTA"        # General observation delta comparison
    VISUAL_SEMANTIC = "VISUAL_SEMANTIC"                        # Vision / OCR comparison (unsupported)


class ExpectedOutcomeType(str, Enum):
    """Declared expectation of what should happen after the action."""

    WINDOW_APPEARED = "WINDOW_APPEARED"            # New window matching title/process appeared
    WINDOW_CLOSED = "WINDOW_CLOSED"                # Window matching title/HWND closed
    WINDOW_FOCUSED = "WINDOW_FOCUSED"              # Target window gained foreground focus
    ELEMENT_STATE_CHANGED = "ELEMENT_STATE_CHANGED"# Specific accessible property changed
    TARGET_DISAPPEARED = "TARGET_DISAPPEARED"      # Target element disappeared (e.g. dialog dismissed)
    TARGET_APPEARED = "TARGET_APPEARED"            # Target element appeared
    ANY_OBSERVABLE_CHANGE = "ANY_OBSERVABLE_CHANGE"# Any legitimate UI change occurred


class ExpectedOutcome(BaseModel):
    """Specification of the intended outcome of an action for verification."""

    outcome_type: ExpectedOutcomeType = Field(..., description="Type of expected state transition")
    strategy: VerificationStrategy = Field(
        default=VerificationStrategy.ACCESSIBILITY_STATE_CHANGE,
        description="Verification strategy to use",
    )
    target_name: Optional[str] = Field(default=None, description="Expected target or window name")
    target_role: Optional[str] = Field(default=None, description="Expected target role")
    target_id: Optional[str] = Field(default=None, description="Expected target identifier")
    window_title: Optional[str] = Field(default=None, description="Expected window title")
    target_hwnd: Optional[int] = Field(default=None, description="Expected target window handle")
    expected_property: Optional[str] = Field(default=None, description="Property name e.g. is_focused, is_enabled")
    expected_value: Optional[Any] = Field(default=None, description="Expected property value after action")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary strategy-specific expectation hints")


class ObservationEvidenceSummary(BaseModel):
    """Structured immutable snapshot summary for pre/post action comparison."""

    snapshot_id: str
    desktop_generation_id: int
    timestamp_ns: int
    is_stale: bool
    foreground_hwnd: Optional[int] = None
    foreground_title: Optional[str] = None
    visible_window_count: int = 0
    element_count: int = 0
    element_ids: List[str] = Field(default_factory=list)
    window_hwnds: List[int] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ActionVerificationResult(BaseModel):
    """Authoritative result of post-action verification."""

    outcome: VerificationOutcome = Field(..., description="Discrete outcome of verification")
    strategy_used: VerificationStrategy = Field(..., description="Verification strategy applied")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Evidence-backed confidence score")
    pre_generation_id: int = Field(..., description="Desktop generation ID before action")
    post_generation_id: int = Field(..., description="Desktop generation ID after action")
    pre_evidence: ObservationEvidenceSummary = Field(..., description="Pre-action observation evidence summary")
    post_evidence: Optional[ObservationEvidenceSummary] = Field(default=None, description="Post-action observation evidence summary")
    detected_changes: List[str] = Field(default_factory=list, description="List of detected observable state changes")
    failure_reason: Optional[str] = Field(default=None, description="Diagnostic explanation if verification failed or inconclusive")
    evaluated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        return self.outcome == VerificationOutcome.VERIFIED_SUCCESS

    @property
    def status(self) -> VerificationStatus:
        """Map outcome to canonical VerificationStatus."""
        mapping = {
            VerificationOutcome.VERIFIED_SUCCESS: VerificationStatus.VERIFIED,
            VerificationOutcome.VERIFIED_FAILURE: VerificationStatus.NOT_VERIFIED,
            VerificationOutcome.INCONCLUSIVE: VerificationStatus.INCONCLUSIVE,
            VerificationOutcome.STALE_EVIDENCE: VerificationStatus.STALE,
            VerificationOutcome.UNSUPPORTED: VerificationStatus.UNSUPPORTED,
        }
        return mapping.get(self.outcome, VerificationStatus.ERROR)


# Domain aliases adhering to M1.6 Step 1 & Step 2 nomenclature
VerificationExpectation = ExpectedOutcome
VerificationEvidence = ObservationEvidenceSummary
VerificationResult = ActionVerificationResult
