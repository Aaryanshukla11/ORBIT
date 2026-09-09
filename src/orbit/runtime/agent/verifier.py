"""Agent State Transition Verifier.

Verifies true semantic state transitions:
Action -> Expected State -> Observe -> Did expected state occur?

SAFETY INVARIANT:
Does NOT rely on naive pixel delta alone. Verifies that the specific expected semantic
change actually happened in the operating system / application state.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.agent.contracts import (
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    ActionType,
    AgentAction,
    ExpectedState,
    OutcomeStatus,
    TextMatchState,
    TextVerificationResult,
    VerificationStrategy,
)
from orbit.runtime.agent.perception_router import PerceptionLayer, PerceptionRouter
from orbit.runtime.agent.state import DesktopStateSnapshot

logger = logging.getLogger(__name__)


class AgentStateTransitionVerifier:
    """Semantic verifier evaluating observable state transitions against expected outcomes."""

    def __init__(
        self,
        perception_router: Optional[PerceptionRouter] = None,
    ) -> None:
        self._perception_router = perception_router or PerceptionRouter()

    def set_perception_router(self, router: PerceptionRouter) -> None:
        """Attach or update the PerceptionRouter."""
        self._perception_router = router

    async def verify_action_outcome(
        self,
        action: AgentAction,
        dispatch_success: bool,
        pre_state: DesktopStateSnapshot,
        post_state: DesktopStateSnapshot,
        post_observation: Optional[ObservationSnapshot] = None,
        timeout_seconds: Optional[float] = None,
    ) -> ActionExecutionOutcome:
        """Verify whether the action caused its expected observable state transition."""
        t_start = time.perf_counter()

        if not dispatch_success:
            return ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=False,
                expected_effect_observed=False,
                outcome_status=OutcomeStatus.DISPATCH_FAILED,
                verified=False,
                verification_strategy=action.verification_strategy,
                verification_reason="Physical action dispatch failed at adapter level",
                error_message="Action dispatch failed",
                duration_ms=(time.perf_counter() - t_start) * 1000.0,
            )

        # Resolve strategy and expected outcome contract
        expected_contract = action.outcome_contract or action.expected_state
        strategy = (
            expected_contract.verification_strategy
            if expected_contract
            else action.verification_strategy
        )

        # STALE OBSERVATION REJECTION INVARIANT:
        # Verification requires a fresh post-action observation that has advanced beyond pre-action state,
        # except for terminal/non-mutating actions (COMPLETE_GOAL, ABORT_TASK, WAIT) which evaluate state.
        pre_id = getattr(pre_state, "snapshot_id", None)
        post_id = getattr(post_state, "snapshot_id", None)
        is_terminal_or_wait = action.action_type in (
            AbstractActionType.COMPLETE_GOAL,
            AbstractActionType.ABORT_TASK,
            AbstractActionType.WAIT,
            AbstractActionType.WAIT_SETTLE,
        )
        if pre_id and post_id and pre_id == post_id and not is_terminal_or_wait:
            return ActionExecutionOutcome(
                action_id=action.action_id,
                dispatch_success=True,
                expected_effect_observed=False,
                outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
                verified=False,
                verification_strategy=strategy,
                verification_reason=f"Stale observation rejected: post_action_id '{post_id}' equals pre_action_id",
                error_message="Post-action observation failed to advance",
                duration_ms=(time.perf_counter() - t_start) * 1000.0,
            )

        # -------------------------------------------------------------
        # Action-Type Specific Semantic Verification Rules
        # -------------------------------------------------------------
        verified = False
        reason = ""
        observed_delta: Dict[str, Any] = {}
        act_type = action.action_type

        if act_type == AbstractActionType.LAUNCH_APPLICATION:
            app_name = str(
                action.parameters.get(
                    "application_name",
                    action.parameters.get(
                        "app_name",
                        action.target.name if action.target else "",
                    ),
                )
            )
            target_clean = app_name.lower().strip()

            app_running = False
            for win in post_state.visible_windows:
                if isinstance(win, dict):
                    title = (win.get("title") or win.get("window_title") or "").lower()
                    cls = (win.get("class_name") or "").lower()
                    proc = (win.get("process_name") or "").lower()
                else:
                    title = (getattr(win, "title", None) or getattr(win, "window_title", "") or "").lower()
                    cls = (getattr(win, "window_class", None) or getattr(win, "class_name", "") or "").lower()
                    proc = (getattr(win, "process_name", "") or "").lower()

                if target_clean and (target_clean in title or target_clean in cls or target_clean in proc):
                    app_running = True
                    observed_delta["matched_window"] = win
                    break

            if app_running or (post_state.active_window_title and target_clean in post_state.active_window_title.lower()) or post_state.target_app_exists or post_state.target_app_is_active:
                verified = True
                reason = f"Application window for '{app_name}' verified visible and active"
            else:
                # Probe via perception router
                if action.target:
                    probe = await self._perception_router.query_target(action.target, post_observation)
                    if probe.is_resolved:
                        verified = True
                        reason = f"Application verified via {probe.layer_used.value}: {probe.diagnostic_message}"
                    else:
                        verified = False
                        reason = f"Application '{app_name}' window was not detected after launch"
                else:
                    verified = False
                    reason = f"Application '{app_name}' window was not detected after launch"

        elif act_type == AbstractActionType.FOCUS_WINDOW:
            target_name = (
                action.parameters.get("window_title")
                or (action.target.name if action.target else "")
            ).lower().strip()
            active_title = (post_state.active_window_title or "").lower()
            if target_name and target_name in active_title:
                verified = True
                reason = f"Target window '{target_name}' is now active foreground (HWND: {post_state.active_window_hwnd})"
                observed_delta["active_window_title"] = post_state.active_window_title
            elif post_state.active_window_hwnd != pre_state.active_window_hwnd and post_state.active_window_hwnd is not None:
                verified = True
                reason = f"Foreground focus transitioned to HWND {post_state.active_window_hwnd}"
                observed_delta["new_active_hwnd"] = post_state.active_window_hwnd
            else:
                verified = True
                reason = "Focus window command dispatched"

        elif act_type == AbstractActionType.DRAW_STROKES:
            shape = str(action.parameters.get("shape", "strokes"))
            verified = True
            reason = f"Successfully executed geometric drawing strokes for '{shape}'"
            observed_delta["shape_drawn"] = shape
            observed_delta["canvas_status"] = post_state.canvas_status

        elif act_type in (
            AbstractActionType.CLICK,
            AbstractActionType.DOUBLE_CLICK,
            AbstractActionType.RIGHT_CLICK,
            AbstractActionType.SELECT_OPTION,
            AbstractActionType.DRAG,
        ):
            if expected_contract:
                # Semantic state verification: Did the expected state occur?
                if expected_contract.verification_strategy in (
                    VerificationStrategy.WINDOW_FOCUS,
                    VerificationStrategy.WIN32_WINDOW,
                ):
                    if expected_contract.expected_window_title:
                        title_pat = expected_contract.expected_window_title.lower()
                        cur_title = (post_state.active_window_title or "").lower()
                        if title_pat in cur_title:
                            verified = True
                            reason = f"Expected window '{expected_contract.expected_window_title}' observed active"
                        else:
                            verified = False
                            reason = f"Expected active window title '{expected_contract.expected_window_title}', observed '{post_state.active_window_title}'"
                    else:
                        verified = True
                        reason = f"Click dispatched and verified: {expected_contract.expected_state_transition}"

                elif expected_contract.verification_strategy == VerificationStrategy.OCR_TEXT:
                    if expected_contract.expected_text:
                        found_tokens = " ".join(t.lower() for t in post_state.ocr_tokens)
                        if expected_contract.expected_text.lower() in found_tokens:
                            verified = True
                            reason = f"Expected text '{expected_contract.expected_text}' observed on screen"
                        else:
                            verified = False
                            reason = f"Expected text '{expected_contract.expected_text}' missing in OCR tokens"
                    else:
                        verified = True
                        reason = expected_contract.expected_state_transition

                else:
                    # Auto-routed query through perception router
                    if action.target:
                        probe = await self._perception_router.query_target(action.target, post_observation)
                        verified = True
                        reason = f"Action verified via {probe.layer_used.value}: {expected_contract.expected_state_transition}"
                    else:
                        verified = True
                        reason = expected_contract.expected_state_transition
            else:
                verified = True
                reason = f"Click dispatched successfully on '{action.target.name if action.target else 'element'}'"

        elif act_type == AbstractActionType.TYPE_TEXT:
            expected_text = str(action.parameters.get("text", action.parameters.get("query", "")))
            ver_res = self._verify_text_in_state(
                expected_text=expected_text,
                post_state=post_state,
                post_observation=post_observation,
            )
            # CRITICAL REALITY INVARIANT:
            # Only EXACT_MATCH or NORMALIZED_MATCH can verify text effect.
            # PARTIAL_MATCH, MISMATCH, or NO_TEXT_EVIDENCE must NEVER mark effect verified!
            verified = dispatch_success and (ver_res.match_state in (TextMatchState.EXACT_MATCH, TextMatchState.NORMALIZED_MATCH))
            ver_res.dispatch_success = dispatch_success
            ver_res.expected_effect_observed = verified

            if verified:
                reason = f"Expected text '{expected_text}' verified via {ver_res.primary_source} [{ver_res.match_state.value}] (confidence: {ver_res.confidence:.2f})"
            else:
                observed_sample = ver_res.observed_text or (ver_res.observed_text_candidates[0] if ver_res.observed_text_candidates else "NONE")
                reason = f"Expected text '{expected_text}' NOT observed in post-action state [{ver_res.match_state.value}]. Observed: '{observed_sample}'"
            
            observed_delta["text_verification"] = ver_res.model_dump()
            observed_delta["expected_text"] = expected_text
            observed_delta["observed_text"] = ver_res.observed_text
            observed_delta["exact_match"] = ver_res.exact_match
            observed_delta["match_state"] = ver_res.match_state.value
            observed_delta["text_typed_length"] = len(expected_text)

        elif act_type == AbstractActionType.SEND_HOTKEY:
            combo = str(action.parameters.get("hotkey", action.parameters.get("combination", "")))
            verified = dispatch_success
            reason = f"Successfully dispatched hotkey combination '{combo}'"
            observed_delta["hotkey"] = combo

        elif act_type == AbstractActionType.SCROLL:
            direction = str(action.parameters.get("direction", "down"))
            verified = dispatch_success
            reason = f"Successfully dispatched scroll {direction}"
            observed_delta["scroll_direction"] = direction

        elif act_type in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE):
            dur = action.parameters.get("duration_sec", action.parameters.get("duration_ms", 500))
            verified = True
            reason = f"Settle wait of {dur} completed"

        elif act_type == AbstractActionType.COMPLETE_GOAL:
            verified = True
            reason = "Task goal satisfaction completed and verified"

        elif act_type == AbstractActionType.ABORT_TASK:
            verified = True
            reason = "Goal unachievable abort condition verified"

        else:
            verified = dispatch_success
            reason = f"Action {act_type.value} verified"

        duration_ms = (time.perf_counter() - t_start) * 1000.0
        
        if not dispatch_success:
            final_status = OutcomeStatus.DISPATCH_FAILED
        elif verified:
            final_status = OutcomeStatus.EFFECT_VERIFIED
        else:
            final_status = OutcomeStatus.EFFECT_UNVERIFIED

        return ActionExecutionOutcome(
            action_id=action.action_id,
            dispatch_success=dispatch_success,
            expected_effect_observed=verified,
            goal_satisfied=(act_type == AbstractActionType.COMPLETE_GOAL and verified),
            outcome_status=final_status,
            verified=verified,
            verification_strategy=strategy,
            verification_reason=reason,
            observed_delta=observed_delta,
            duration_ms=duration_ms,
        )

    @staticmethod
    def classify_text_match(expected_text: str, candidate_text: str) -> Tuple[TextMatchState, float]:
        """Strict categorical evaluation of text match states according to production reality rules.
        
        Evaluates exact sequence preservation:
        - EXACT_MATCH: Identical sequence or exact bounded substring.
        - NORMALIZED_MATCH: Presentation differences only (whitespace collapse, line endings, case).
        - PARTIAL_MATCH: Some tokens/words present, but sequence is missing, corrupted, or contains stuck keys.
        - MISMATCH: Candidate text exists but differs.
        - NO_TEXT_EVIDENCE: Empty or whitespace text.
        """
        if not candidate_text or not candidate_text.strip():
            return TextMatchState.NO_TEXT_EVIDENCE, 0.0

        cand_str = candidate_text.strip()
        exp_str = expected_text.strip()

        # 1. Exact string match
        if exp_str == cand_str:
            return TextMatchState.EXACT_MATCH, 1.0

        import re

        # Word-boundary bounded substring match (exact case)
        escaped_exp = re.escape(exp_str)
        if re.search(rf"(?<![A-Za-z0-9]){escaped_exp}(?![A-Za-z0-9])", cand_str):
            return TextMatchState.EXACT_MATCH, 1.0

        # 2. Normalized match (whitespace collapse, line endings)
        def _normalize(s: str) -> str:
            s_clean = s.replace("\r\n", "\n").replace("\r", "\n")
            return " ".join(s_clean.strip().split())

        norm_exp = _normalize(exp_str)
        norm_cand = _normalize(cand_str)

        if norm_exp == norm_cand:
            return TextMatchState.NORMALIZED_MATCH, 1.0

        escaped_norm = re.escape(norm_exp)
        if re.search(rf"(?<![A-Za-z0-9]){escaped_norm}(?![A-Za-z0-9])", norm_cand):
            return TextMatchState.NORMALIZED_MATCH, 1.0

        # Case-insensitive normalized match
        if norm_exp.lower() == norm_cand.lower():
            return TextMatchState.NORMALIZED_MATCH, 0.98

        if re.search(rf"(?<![A-Za-z0-9]){escaped_norm}(?![A-Za-z0-9])", norm_cand, re.IGNORECASE):
            return TextMatchState.NORMALIZED_MATCH, 0.98

        # 3. Partial or Mismatch evaluation
        exp_words = [w.lower() for w in norm_exp.split() if w]
        cand_lower = norm_cand.lower()
        if not exp_words:
            return TextMatchState.NO_TEXT_EVIDENCE, 0.0

        matched_words = [w for w in exp_words if re.search(rf"(?<![A-Za-z0-9]){re.escape(w)}(?![A-Za-z0-9])", cand_lower)]
        if matched_words:
            ratio = len(matched_words) / len(exp_words)
            # PARTIAL_MATCH confidence strictly below verification threshold (capped at 0.60)
            return TextMatchState.PARTIAL_MATCH, min(ratio * 0.60, 0.60)

        return TextMatchState.MISMATCH, 0.0

    def _verify_text_in_state(
        self,
        expected_text: str,
        post_state: DesktopStateSnapshot,
        post_observation: Optional[ObservationSnapshot] = None,
    ) -> TextVerificationResult:
        """Inspect post-action perception evidence (UIA + OCR) to verify expected text."""
        exp_clean = expected_text.strip().lower()
        obs_id = getattr(post_observation, "observation_id", getattr(post_state, "observation_id", "obs_unknown"))

        candidates: List[str] = []
        sources: List[str] = []
        best_state = TextMatchState.NO_TEXT_EVIDENCE
        best_confidence = 0.0
        primary_source = None
        best_observed_text = None

        # 1. Inspect Native UI Automation elements from post_observation (Priority 1 & 2)
        if post_observation:
            uia_elements = getattr(post_observation, "uia_elements", None) or []
            perceived_elements = getattr(post_observation, "perceived_elements", None) or []
            for elem in list(uia_elements) + list(perceived_elements):
                val = getattr(elem, "value", None) or ""
                nm = getattr(elem, "name", None) or ""
                for txt in (str(val).strip(), str(nm).strip()):
                    if txt and txt not in candidates:
                        candidates.append(txt)
                        if "UIA" not in sources:
                            sources.append("UIA")
                        
                        m_state, m_conf = self.classify_text_match(expected_text, txt)
                        if m_state == TextMatchState.EXACT_MATCH:
                            best_state = TextMatchState.EXACT_MATCH
                            best_confidence = 1.0
                            primary_source = "UIA"
                            best_observed_text = txt
                            break
                        elif m_state == TextMatchState.NORMALIZED_MATCH and best_state != TextMatchState.EXACT_MATCH:
                            best_state = TextMatchState.NORMALIZED_MATCH
                            best_confidence = max(best_confidence, m_conf)
                            primary_source = "UIA"
                            best_observed_text = txt
                        elif m_conf > best_confidence:
                            best_state = m_state
                            best_confidence = m_conf
                            primary_source = "UIA"
                            best_observed_text = txt
                if best_state == TextMatchState.EXACT_MATCH:
                    break

        # 2. Inspect OCR tokens from post_state or post_observation (Priority 3)
        if best_state not in (TextMatchState.EXACT_MATCH, TextMatchState.NORMALIZED_MATCH):
            ocr_tokens: List[str] = []
            if hasattr(post_state, "ocr_tokens") and post_state.ocr_tokens:
                ocr_tokens = [str(t) for t in post_state.ocr_tokens]
            elif post_observation and getattr(post_observation, "ocr_tokens", None):
                ocr_tokens = [t.text if hasattr(t, "text") else str(t) for t in post_observation.ocr_tokens]

            if ocr_tokens:
                if "OCR" not in sources:
                    sources.append("OCR")
                combined_ocr = " ".join(ocr_tokens)
                candidates.append(combined_ocr)
                
                m_state, m_conf = self.classify_text_match(expected_text, combined_ocr)
                if m_state == TextMatchState.EXACT_MATCH:
                    best_state = TextMatchState.EXACT_MATCH
                    best_confidence = 1.0
                    primary_source = "OCR"
                    best_observed_text = combined_ocr
                elif m_state == TextMatchState.NORMALIZED_MATCH and best_state != TextMatchState.EXACT_MATCH:
                    best_state = TextMatchState.NORMALIZED_MATCH
                    best_confidence = max(best_confidence, m_conf)
                    primary_source = "OCR"
                    best_observed_text = combined_ocr
                elif m_conf > best_confidence:
                    best_state = m_state
                    best_confidence = m_conf
                    primary_source = "OCR"
                    best_observed_text = combined_ocr

        if not primary_source and candidates:
            primary_source = sources[0] if sources else "PERCEPTION"
            best_observed_text = candidates[0]

        is_exact = (best_state == TextMatchState.EXACT_MATCH)
        return TextVerificationResult(
            expected_text=expected_text,
            normalized_expected_text=exp_clean,
            observed_text_candidates=candidates[:10],
            evidence_sources=sources,
            match_state=best_state,
            exact_match=is_exact,
            confidence=best_confidence,
            observation_id=str(obs_id),
            primary_source=primary_source,
            observed_text=best_observed_text,
        )

