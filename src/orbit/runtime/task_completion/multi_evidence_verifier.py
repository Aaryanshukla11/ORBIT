"""Multi-Evidence Action Verifier.

Guardrail 6: Closed-Loop is a Hard Invariant (Verify postconditions before next action).
Guardrail 7: Verification Must Be Semantic (Multi-evidence fusion driven by PrimitiveContract;
             never a generic weighted evidence score where arbitrary pixel delta alone claims success).
Guardrail 16: No Silent Fallback Success.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    OutcomeStatus,
    VerificationStrategy,
)
from orbit.runtime.cognitive.models import CurrentStateObservation

logger = logging.getLogger(__name__)


class MultiEvidenceVerificationResult(BaseModel):
    """Structured result of semantic multi-evidence verification."""

    is_verified: bool = Field(..., description="Whether expected semantic effect is confirmed")
    outcome_status: OutcomeStatus = Field(default=OutcomeStatus.EFFECT_UNVERIFIED)
    evidence_sources: List[str] = Field(default_factory=list, description="Modality evidence sources evaluated")
    verification_reason: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    pixel_delta_detected: bool = Field(default=False, description="Whether pixel visual delta occurred (supporting only)")
    uia_delta_detected: bool = Field(default=False, description="Whether accessibility state changed")
    ocr_match_detected: bool = Field(default=False, description="Whether required text appeared in OCR")
    window_state_satisfied: bool = Field(default=False, description="Whether foreground window state matched contract")


class MultiEvidenceActionVerifier:
    """Verifies that an action's postcondition contract was physically satisfied on screen.

    Strict semantic verification invariant:
    Verification is driven by the specific PrimitiveContract.
    - Window lifecycle actions verify foreground HWND, title, process, and visibility.
    - Typing actions verify text presence in UIA buffer or OCR text tokens.
    - Click actions verify UI control state changes or target disappearance/appearance.
    - Pixel delta alone is NEVER sufficient to declare success on interactive or text actions.
    """

    async def verify_action_effect(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
    ) -> MultiEvidenceVerificationResult:
        """Evaluate semantic evidence against action outcome contract."""
        contract: Optional[ActionOutcomeContract] = action.outcome_contract
        act_type = action.action_type

        # Stale Observation Check (Part 6):
        # Verification requires a fresh post-action observation that has advanced beyond pre-action state.
        if pre_obs.observation_id and post_obs.observation_id and pre_obs.observation_id == post_obs.observation_id:
            if act_type not in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE):
                return MultiEvidenceVerificationResult(
                    is_verified=False,
                    outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
                    evidence_sources=["STALE_OBSERVATION_CHECK"],
                    verification_reason="Post-action observation ID is identical to pre-action; observation is stale.",
                    confidence=0.0,
                    pixel_delta_detected=False,
                )

        # Observation delta check (supporting evidence)
        pixel_delta = False
        if pre_obs.observation_id != post_obs.observation_id:
            # Different observation ID indicates live recapture
            pixel_delta = True

        # 1. LAUNCH_APPLICATION / FOCUS_WINDOW verification
        if act_type in (AbstractActionType.LAUNCH_APPLICATION, AbstractActionType.FOCUS_WINDOW):
            return self._verify_window_action(action, pre_obs, post_obs, pixel_delta)

        # 2. TYPE_TEXT verification
        if act_type == AbstractActionType.TYPE_TEXT:
            return self._verify_type_text(action, pre_obs, post_obs, pixel_delta)

        # 3. DRAW_STROKES verification
        if act_type == AbstractActionType.DRAW_STROKES:
            return self._verify_drawing(action, pre_obs, post_obs, pixel_delta)

        # 4. CLICK / DOUBLE_CLICK / RIGHT_CLICK verification
        if act_type in (AbstractActionType.CLICK, AbstractActionType.DOUBLE_CLICK, AbstractActionType.RIGHT_CLICK):
            return self._verify_pointer_click(action, pre_obs, post_obs, pixel_delta)

        # 5. Generic observation or environment interface
        if act_type in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE):
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["SETTLED_WAIT"],
                verification_reason="Wait duration elapsed; desktop settled.",
                confidence=1.0,
            )

        # 6. Fallback semantic evaluation
        if contract:
            exp = (contract.expected_state_transition or "").lower()
            # If foreground window title changed as expected
            if exp and post_obs.active_window_title and exp in post_obs.active_window_title.lower():
                return MultiEvidenceVerificationResult(
                    is_verified=True,
                    outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                    evidence_sources=["WINDOW_TITLE"],
                    verification_reason=f"Foreground window '{post_obs.active_window_title}' satisfied '{exp}'",
                    confidence=0.9,
                    window_state_satisfied=True,
                )

        # Guardrail 16: No Silent Fallback Success
        logger.warning("Action %s effect could not be verified by multi-evidence verifier", action.action_id)
        return MultiEvidenceVerificationResult(
            is_verified=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            evidence_sources=["MULTI_EVIDENCE_EVAL"],
            verification_reason=f"Expected state transition '{contract.expected_state_transition if contract else 'unspecified'}' was not observed.",
            confidence=0.0,
            pixel_delta_detected=pixel_delta,
        )

    def _verify_window_action(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        pixel_delta: bool,
    ) -> MultiEvidenceVerificationResult:
        """Verify window launch or focus actions."""
        target_name = str(
            action.parameters.get("application_name", action.parameters.get("app_name", action.target.name if action.target else ""))
        ).strip().lower()

        # Check post-observation active window title and visible windows
        active_title = (post_obs.active_window_title or "").lower()
        active_proc = (post_obs.active_process_name or "").lower()

        # Match in active window
        if target_name and (target_name in active_title or target_name in active_proc):
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["WINDOW_ACTIVE", "WIN32_FOREGROUND"],
                verification_reason=f"Target application '{target_name}' is active foreground window ('{post_obs.active_window_title}')",
                confidence=0.98,
                window_state_satisfied=True,
                pixel_delta_detected=pixel_delta,
            )

        # Match in visible windows list
        for win in post_obs.visible_windows:
            w_title = (win.get("title") or "").lower()
            w_proc = (win.get("process_name") or "").lower()
            if target_name and (target_name in w_title or target_name in w_proc):
                return MultiEvidenceVerificationResult(
                    is_verified=True,
                    outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                    evidence_sources=["WINDOW_VISIBLE", "WIN32_ENUM"],
                    verification_reason=f"Target window for '{target_name}' found in visible top-level windows",
                    confidence=0.90,
                    window_state_satisfied=True,
                    pixel_delta_detected=pixel_delta,
                )

        if post_obs.target_app_exists or post_obs.target_app_is_active:
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["OBSERVER_APP_STATUS"],
                verification_reason="Target application detected running by live observer.",
                confidence=0.85,
                window_state_satisfied=True,
            )

        return MultiEvidenceVerificationResult(
            is_verified=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            evidence_sources=["WIN32_OBSERVATION"],
            verification_reason=f"Application '{target_name}' not found in active or visible windows.",
            confidence=0.0,
            pixel_delta_detected=pixel_delta,
        )

    def _verify_type_text(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        pixel_delta: bool,
    ) -> MultiEvidenceVerificationResult:
        """Verify typed text via OCR or UIA."""
        expected_text = str(action.parameters.get("text", action.parameters.get("query", ""))).strip().lower()

        # Check OCR tokens in post observation
        ocr_match = False
        matching_token = ""
        for token in post_obs.ocr_tokens:
            if expected_text and (expected_text in token.lower() or token.lower() in expected_text):
                ocr_match = True
                matching_token = token
                break

        if ocr_match:
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["OCR_TOKEN_MATCH"],
                verification_reason=f"Typed text '{expected_text}' verified via OCR token '{matching_token}'",
                confidence=0.95,
                ocr_match_detected=True,
                pixel_delta_detected=pixel_delta,
            )

        # Check raw evidence / UIA text buffers if present
        uia_val = post_obs.raw_evidence.get("focused_element_text", "")
        if expected_text and expected_text in str(uia_val).lower():
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["UIA_VALUE_BUFFER"],
                verification_reason=f"Typed text '{expected_text}' verified in UIA control buffer",
                confidence=0.98,
                uia_delta_detected=True,
                pixel_delta_detected=pixel_delta,
            )

        # Guardrail 7: Pixel delta ALONE cannot verify text entry
        return MultiEvidenceVerificationResult(
            is_verified=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            evidence_sources=["OCR", "UIA"],
            verification_reason=f"Typed text '{expected_text}' was not found in post-action OCR or UIA buffers.",
            confidence=0.0,
            pixel_delta_detected=pixel_delta,
        )

    def _verify_drawing(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        pixel_delta: bool,
    ) -> MultiEvidenceVerificationResult:
        """Verify geometric canvas drawing."""
        canvas_status = (post_obs.canvas_status or "").upper()
        if canvas_status in ("NON_BLANK", "DRAWING_COMPLETED", "MODIFIED"):
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["CANVAS_STATUS_DELTA"],
                verification_reason=f"Canvas state verified modified: {canvas_status}",
                confidence=0.95,
                pixel_delta_detected=True,
            )

        if pixel_delta and pre_obs.canvas_status == "BLANK" and post_obs.canvas_status != "BLANK":
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["CANVAS_PIXEL_DELTA"],
                verification_reason="Canvas pixel delta detected post-stroke dispatch",
                confidence=0.88,
                pixel_delta_detected=True,
            )

        return MultiEvidenceVerificationResult(
            is_verified=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            evidence_sources=["CANVAS_EVIDENCE"],
            verification_reason="Canvas showed no drawing modification post-stroke.",
            confidence=0.0,
        )

    def _verify_pointer_click(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        pixel_delta: bool,
    ) -> MultiEvidenceVerificationResult:
        """Verify pointer click actions."""
        # 1. Did active window change?
        if pre_obs.active_window_hwnd != post_obs.active_window_hwnd and post_obs.active_window_hwnd is not None:
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["ACTIVE_WINDOW_CHANGED"],
                verification_reason=f"Click caused active window transition from '{pre_obs.active_window_title}' to '{post_obs.active_window_title}'",
                confidence=0.95,
                window_state_satisfied=True,
                pixel_delta_detected=pixel_delta,
            )

        # 2. Did target disappear or new elements appear?
        if pre_obs.perceived_elements_count != post_obs.perceived_elements_count:
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["UIA_ELEMENT_COUNT_DELTA"],
                verification_reason=f"UI element tree modified: {pre_obs.perceived_elements_count} -> {post_obs.perceived_elements_count}",
                confidence=0.90,
                uia_delta_detected=True,
                pixel_delta_detected=pixel_delta,
            )

        # 3. Contract-specific postcondition check
        if action.outcome_contract and action.outcome_contract.expected_state_transition:
            exp = action.outcome_contract.expected_state_transition.lower()
            if any(exp in t.lower() for t in post_obs.ocr_tokens):
                return MultiEvidenceVerificationResult(
                    is_verified=True,
                    outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                    evidence_sources=["OCR_CONTRACT_MATCH"],
                    verification_reason=f"Expected transition text '{exp}' verified in OCR tokens",
                    confidence=0.92,
                    ocr_match_detected=True,
                    pixel_delta_detected=pixel_delta,
                )

        # 4. Subtle click check: UIA focus or selection state changed without global pixel delta
        pre_focused = pre_obs.raw_evidence.get("focused_element_id") or pre_obs.raw_evidence.get("focused_element_name")
        post_focused = post_obs.raw_evidence.get("focused_element_id") or post_obs.raw_evidence.get("focused_element_name")
        if pre_focused and post_focused and pre_focused != post_focused:
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["UIA_FOCUSED_ELEMENT_DELTA"],
                verification_reason=f"Subtle click verified: focused element changed from '{pre_focused}' to '{post_focused}'",
                confidence=0.92,
                uia_delta_detected=True,
            )

        # 5. Semantic visual verification: Visual delta is ONLY accepted when specifically
        # contracted via VerificationStrategy.PIXEL_DELTA / PIXEL_DIFF and local delta confirmed
        contract = action.outcome_contract
        if contract and contract.verification_strategy in (VerificationStrategy.PIXEL_DELTA, VerificationStrategy.PIXEL_DIFF):
            if post_obs.raw_evidence.get("target_pixel_delta_verified", False):
                return MultiEvidenceVerificationResult(
                    is_verified=True,
                    outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                    evidence_sources=["TARGET_BOUNDING_BOX_PIXEL_DELTA"],
                    verification_reason="Target bounding box confirmed visual change per PIXEL_DELTA contract.",
                    confidence=0.85,
                    pixel_delta_detected=True,
                )

        return MultiEvidenceVerificationResult(
            is_verified=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            evidence_sources=["CLICK_VERIFICATION"],
            verification_reason="No observable window, UI element, or contracted visual delta detected after click.",
            confidence=0.0,
            pixel_delta_detected=pixel_delta,
        )
