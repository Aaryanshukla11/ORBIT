"""15-Class Failure Taxonomy and Diagnostic Classification for ORBIT Benchmark."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FailureTaxonomy(str, Enum):
    """15-class categorical failure taxonomy for desktop agent autonomy."""
    INTENT_ERROR = "INTENT_ERROR"                           # Model misunderstood user goal
    GOAL_DECOMPOSITION_ERROR = "GOAL_DECOMPOSITION_ERROR"   # Subgoals planned incorrectly
    PERCEPTION_ERROR = "PERCEPTION_ERROR"                   # Frame capture or UIA/OCR missed elements
    GROUNDING_ERROR = "GROUNDING_ERROR"                     # Coordinates failed to resolve from target
    STALE_OBSERVATION = "STALE_OBSERVATION"                 # Action targeted an outdated screen state
    ACTION_EXECUTION_ERROR = "ACTION_EXECUTION_ERROR"       # Win32/pointer/keyboard dispatch failure
    APPLICATION_STATE_ERROR = "APPLICATION_STATE_ERROR"     # App crashed or became unresponsive
    DIALOG_HANDLING_ERROR = "DIALOG_HANDLING_ERROR"         # Modal/file dialog blocked workflow
    SAVE_PERSISTENCE_ERROR = "SAVE_PERSISTENCE_ERROR"       # Save flow triggered but file not written
    ARTIFACT_INTEGRITY_ERROR = "ARTIFACT_INTEGRITY_ERROR"   # File created but corrupt or invalid format
    MODEL_ERROR = "MODEL_ERROR"                             # Model returned invalid JSON / schema error
    RECOVERY_ERROR = "RECOVERY_ERROR"                       # Recovery loop failed to heal state
    TIMEOUT = "TIMEOUT"                                     # Step or budget limit exceeded
    SAFETY_BLOCK = "SAFETY_BLOCK"                           # Policy blocked action
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"                 # External OS/driver anomaly


class FailureClassificationResult(BaseModel):
    """Structured diagnostic failure report."""
    primary_category: FailureTaxonomy
    secondary_category: Optional[FailureTaxonomy] = None
    diagnostic_details: str
    action_type: Optional[str] = None
    step_index: Optional[int] = None
    remediation_suggestion: Optional[str] = None


class FailureClassifier:
    """Automated classification engine mapping execution outcomes to failure taxonomy."""

    @classmethod
    def classify_execution_failure(
        cls,
        is_success: bool,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        verification_status: Optional[str] = None,
        verification_reason: Optional[str] = None,
        goal_verified: bool = False,
        artifact_verified: bool = False,
        has_deliverable_spec: bool = False,
        actions_attempted: int = 0,
        actions_completed: int = 0,
        recovery_attempts: int = 0,
        timeout_exceeded: bool = False,
        model_calls: int = 0,
    ) -> Optional[FailureClassificationResult]:
        """Classify a failed execution record into the 15-class taxonomy."""
        if is_success and goal_verified and (artifact_verified or not has_deliverable_spec):
            return None

        msg = (error_message or "").lower()
        reason = (verification_reason or "").lower()
        code = (error_code or "").upper()

        # 1. Timeout
        if timeout_exceeded or "timeout" in msg or "budget_exhausted" in code:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.TIMEOUT,
                diagnostic_details="Execution exceeded timeout or maximum step budget.",
                remediation_suggestion="Increase step budget or optimize plan decomposition.",
            )

        # 2. Safety block
        if "safety" in code or "safety" in msg or "blocked" in code:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.SAFETY_BLOCK,
                diagnostic_details=f"Safety gate blocked action: {error_message}",
                remediation_suggestion="Review safety rule or obtain operator authorization token.",
            )

        # 3. Model Error
        if "model_unavailable" in code or "json" in msg or "schema" in msg or model_calls == 0:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.MODEL_ERROR,
                diagnostic_details=f"Model failure or unavailable: {error_message}",
                remediation_suggestion="Verify model session health and JSON output schema.",
            )

        # 4. Grounding Error
        if "grounding" in code or "grounding" in msg or "target" in msg and "not found" in msg:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.GROUNDING_ERROR,
                diagnostic_details=f"Target grounding failed: {error_message or verification_reason}",
                remediation_suggestion="Enhance visual template or fuzzy OCR matching.",
            )

        # 5. Stale Observation
        if "stale" in code or "stale" in reason or "generation_mismatch" in reason:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.STALE_OBSERVATION,
                diagnostic_details=f"Stale observation detected: {verification_reason}",
                remediation_suggestion="Enforce perceptual settle before subsequent action.",
            )

        # 6. Artifact Integrity / Save Persistence
        if has_deliverable_spec and not artifact_verified:
            if "magic_bytes" in msg or "corrupt" in msg or "empty" in msg or "format" in msg:
                return FailureClassificationResult(
                    primary_category=FailureTaxonomy.ARTIFACT_INTEGRITY_ERROR,
                    diagnostic_details=f"Artifact format or checksum corrupted: {error_message or verification_reason}",
                    remediation_suggestion="Check file export writer and magic byte structure.",
                )
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.SAVE_PERSISTENCE_ERROR,
                diagnostic_details=f"Expected deliverable file was not written to disk: {error_message or verification_reason}",
                remediation_suggestion="Verify Save dialog automation and path confirmation.",
            )

        # 7. Dialog Handling Error
        if "dialog" in msg or "modal" in msg or "#32770" in msg or "overwrite" in msg:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.DIALOG_HANDLING_ERROR,
                diagnostic_details=f"Modal dialog blocked execution: {error_message or verification_reason}",
                remediation_suggestion="Handle Common Item Dialog or confirm overwrite prompt.",
            )

        # 8. Recovery Error
        if recovery_attempts > 0 and not is_success:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.RECOVERY_ERROR,
                diagnostic_details=f"Recovery failed after {recovery_attempts} remediation attempts.",
                remediation_suggestion="Expand recovery strategy registry with alternate inputs.",
            )

        # 9. Application State Error
        if "crash" in msg or "unresponsive" in msg or "not running" in msg:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.APPLICATION_STATE_ERROR,
                diagnostic_details=f"Target application crashed or failed to respond: {error_message}",
                remediation_suggestion="Restart application process and check Win32 handles.",
            )

        # 10. Action Execution Error
        if "sendinput" in msg or "dispatch" in msg or "pointer" in msg or "keyboard" in msg:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.ACTION_EXECUTION_ERROR,
                diagnostic_details=f"Physical input dispatch failed: {error_message}",
                remediation_suggestion="Check Win32 SendInput parameters and window foreground state.",
            )

        # 11. Perception Error
        if "perception" in msg or "screenshot" in msg or "uia" in msg:
            return FailureClassificationResult(
                primary_category=FailureTaxonomy.PERCEPTION_ERROR,
                diagnostic_details=f"Perception capture failed: {error_message}",
                remediation_suggestion="Verify GDI capture permissions and UIA COM apartment.",
            )

        # 12. Intent / Goal Error (Fallback)
        return FailureClassificationResult(
            primary_category=FailureTaxonomy.INTENT_ERROR,
            diagnostic_details=f"Goal not satisfied: {verification_reason or error_message or 'Unmet expectations'}",
            remediation_suggestion="Refine prompt decomposition and expected outcome contracts.",
        )
