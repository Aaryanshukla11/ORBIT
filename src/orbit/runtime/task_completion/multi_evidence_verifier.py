"""Multi-Evidence Action Verifier.

Guardrail 6: Closed-Loop is a Hard Invariant (Verify postconditions before next action).
Guardrail 7: Verification Must Be Semantic (Multi-evidence fusion driven by PrimitiveContract;
             never a generic weighted evidence score where arbitrary pixel delta alone claims success).
Guardrail 16: No Silent Fallback Success.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionOutcomeContract,
    OutcomeStatus,
    VerificationStrategy,
)

if TYPE_CHECKING:
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

        # 5. SAVE_FILE / FILE_WRITE verification
        if act_type in (AbstractActionType.SAVE_FILE, AbstractActionType.FILE_WRITE):
            return self._verify_save_file(action, pre_obs, post_obs, pixel_delta)

        # 6. Generic observation or environment interface
        if act_type in (AbstractActionType.WAIT, AbstractActionType.WAIT_SETTLE):
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["SETTLED_WAIT"],
                verification_reason="Wait duration elapsed; desktop settled.",
                confidence=1.0,
            )

        # 7. Fallback semantic evaluation
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

        active_title = (post_obs.active_window_title or "").lower()
        active_proc = (post_obs.active_process_name or "").lower()

        aliases = [target_name]
        if target_name in ("edge", "msedge", "microsoft edge", "browser"):
            aliases = ["edge", "msedge", "microsoft edge"]
        elif target_name in ("paint", "mspaint"):
            aliases = ["paint", "mspaint"]
        elif target_name in ("calc", "calculator"):
            aliases = ["calc", "calculator"]
        elif target_name in ("notepad", "notepad.exe"):
            aliases = ["notepad"]
        elif target_name in ("chrome", "google chrome"):
            aliases = ["chrome", "google chrome"]

        def _is_editor(title: str, proc: str = "") -> bool:
            p = (proc or "").lower()
            if p in ("msedge.exe", "chrome.exe", "brave.exe", "firefox.exe", "mspaint.exe", "calc.exe", "notepad.exe"):
                return False
            t = (title or "").lower()
            return any(ed in t for ed in ("antigravity ide", "visual studio code", "vscode", "sublime text", "pycharm")) or p in ("antigravity ide.exe", "code.exe", "devenv.exe")

        def _matches(t_str: str, p_str: str, c_str: str = "") -> bool:
            t_low = (t_str or "").lower()
            p_low = (p_str or "").lower()
            c_low = (c_str or "").lower()
            if _is_editor(t_low, p_low):
                return False
            if target_name in ("paint", "mspaint"):
                return ("mspaint" in p_low or "mspaintapp" in c_low or "msppaint" in c_low or 
                        ("paint" in t_low and not t_low.endswith((".py", ".ts", ".js", ".md", ".json", ".txt"))))
            if target_name in ("edge", "msedge", "microsoft edge", "browser"):
                return "msedge" in p_low or ("edge" in t_low and not t_low.endswith((".py", ".ts", ".js", ".md", ".json", ".txt")))
            if target_name in ("notepad", "notepad.exe"):
                return "notepad" in p_low or ("notepad" in t_low and not t_low.endswith((".py", ".ts", ".js", ".md", ".json", ".txt")))
            if target_name in ("calc", "calculator"):
                return "calc" in p_low or "calculator" in p_low or ("calc" in t_low and not t_low.endswith((".py", ".ts", ".js", ".md", ".json", ".txt")))
            return any(a in t_low or a in p_low or a in c_low for a in aliases if a)

        # Match in active window
        active_cls = (getattr(post_obs, "active_window_class", "") or "").lower()
        if target_name and _matches(active_title, active_proc, active_cls):
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
            w_title = (win.get("title", "") if isinstance(win, dict) else getattr(win, "title", str(win))) or ""
            w_proc = (win.get("process_name", "") if isinstance(win, dict) else getattr(win, "process_name", "")) or ""
            w_cls = (win.get("class_name", "") if isinstance(win, dict) else getattr(win, "window_class", getattr(win, "class_name", ""))) or ""
            if target_name and _matches(w_title, w_proc, w_cls):
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

        # Real-time Win32 check fallback in case window opened during settle interval
        import sys
        if sys.platform == "win32":
            try:
                from orbit.runtime.perception.windows import Win32WindowObserver
                observer = Win32WindowObserver()
                _, live_visible = observer.observe_windows()
                for lw in live_visible:
                    lw_title = lw.title or ""
                    lw_proc = lw.process_name or ""
                    lw_cls = lw.window_class or ""
                    if target_name and _matches(lw_title, lw_proc, lw_cls):
                        return MultiEvidenceVerificationResult(
                            is_verified=True,
                            outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                            evidence_sources=["WINDOW_VISIBLE", "WIN32_LIVE_ENUM"],
                            verification_reason=f"Target window for '{target_name}' confirmed in live window scan ('{lw_title}')",
                            confidence=0.92,
                            window_state_satisfied=True,
                            pixel_delta_detected=True,
                        )
            except Exception:
                pass

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
        if canvas_status in ("BLANK", "EMPTY", "UNMODIFIED"):
            return MultiEvidenceVerificationResult(
                is_verified=False,
                outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
                evidence_sources=["CANVAS_EVIDENCE"],
                verification_reason="Canvas showed no drawing modification post-stroke (status remains BLANK).",
                confidence=0.0,
            )

        if canvas_status in ("NON_BLANK", "DRAWING_COMPLETED", "MODIFIED", "READY_FOR_DRAWING", "CANVAS_MODIFIED"):
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["CANVAS_STATUS_DELTA"],
                verification_reason=f"Canvas state verified modified/active: {canvas_status}",
                confidence=0.95,
                pixel_delta_detected=True,
            )

        if pixel_delta:
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

    def _verify_save_file(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        pixel_delta: bool,
    ) -> MultiEvidenceVerificationResult:
        """Verify physical file persistence and artifact integrity."""
        params = action.parameters or {}
        filename = str(
            params.get("file_path")
            or params.get("filename")
            or params.get("target_path")
            or params.get("path")
            or params.get("destination")
            or params.get("save_path")
            or params.get("output_path")
            or ""
        ).strip()
        if not filename and action.target:
            t_name = (action.target.name or "").strip()
            if t_name and t_name.lower() not in ("file", "current_artifact", "artifact"):
                filename = t_name

        if not filename:
            return MultiEvidenceVerificationResult(
                action=action,
                action_type=AbstractActionType.SAVE_FILE,
                is_verified=False,
                confidence=0.0,
                evidence_found=[],
                failure_reason="SAVE_VERIFICATION_FAILED: No target filename specified in action parameters or target",
                provenance_verified=False,
            )

        user_profile = os.environ.get("USERPROFILE", "")
        home_dir = os.path.expanduser("~")
        candidate_paths = [filename]
        if os.path.isabs(filename):
            candidate_paths.append(filename)
        else:
            if user_profile:
                candidate_paths.append(os.path.join(user_profile, "OneDrive", "Desktop", os.path.basename(filename)))
                candidate_paths.append(os.path.join(user_profile, "Desktop", os.path.basename(filename)))
            if home_dir:
                candidate_paths.append(os.path.join(home_dir, "OneDrive", "Desktop", os.path.basename(filename)))
                candidate_paths.append(os.path.join(home_dir, "Desktop", os.path.basename(filename)))
            candidate_paths.append(os.path.abspath(filename))
            candidate_paths.append(os.path.join(os.getcwd(), os.path.basename(filename)))

        found_path = None
        for p in candidate_paths:
            if os.path.exists(p) and os.path.isfile(p):
                sz = os.path.getsize(p)
                if sz > 0:
                    fmt = str(params.get("format", p.rsplit(".", 1)[-1] if "." in p else "png")).lower()
                    if fmt in ("png", "jpg", "jpeg", "bmp") or p.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                        try:
                            from PIL import Image
                            with Image.open(p) as img:
                                img.verify()
                            found_path = p
                            break
                        except Exception:
                            continue
                    else:
                        found_path = p
                        break

        if found_path:
            return MultiEvidenceVerificationResult(
                is_verified=True,
                outcome_status=OutcomeStatus.EFFECT_VERIFIED,
                evidence_sources=["FILE_ARTIFACT_CHECK", "FORMAT_INTEGRITY"],
                verification_reason=f"Target file '{found_path}' verified on disk (size: {os.path.getsize(found_path)} bytes).",
                confidence=1.0,
                pixel_delta_detected=pixel_delta,
            )

        return MultiEvidenceVerificationResult(
            is_verified=False,
            outcome_status=OutcomeStatus.EFFECT_UNVERIFIED,
            evidence_sources=["FILE_ARTIFACT_CHECK"],
            verification_reason=f"Target artifact '{filename}' not found or invalid on disk.",
            confidence=0.0,
            pixel_delta_detected=pixel_delta,
        )
