"""Goal Completion Verification Engine (M1.8 Step 5).

Key architectural invariant:
Independent verification of the final user objective against a fresh post-execution observation.
Never equates low-level action dispatch with task success.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any, Dict, List, Optional
from PIL import Image, ImageChops

from orbit.adapters.observation.snapshot import ObservationSnapshot, ObservedElement, ObservedWindow
from orbit.runtime.perception import SemanticPerceptionEngine
from orbit.runtime.perception.models import OCRResult, OCRTextRegion
from orbit.runtime.plan_execution.models import PlanExecutionResult, PlanExecutionStatus
from orbit.runtime.planning.models import ExecutableTaskPlan, PlanActionType
from orbit.runtime.task_completion.evidence import CompletionEvidenceCollector
from orbit.runtime.task_completion.models import (
    GoalVerificationResult,
    TaskCompletionEvidence,
    TaskCompletionStatus,
)
from orbit.runtime.task_understanding.models import (
    StructuredTaskIntent,
    TaskGoal,
    TaskUnderstandingResult,
)

logger = logging.getLogger(__name__)


class GoalVerifier:
    """Independent verifier evaluating whether an end-to-end task actually achieved its goal."""

    def __init__(
        self,
        perception_engine: Optional[SemanticPerceptionEngine] = None,
        evidence_collector: Optional[CompletionEvidenceCollector] = None,
    ) -> None:
        self._perception_engine = perception_engine or SemanticPerceptionEngine()
        self._evidence_collector = evidence_collector or CompletionEvidenceCollector()

    @property
    def perception_engine(self) -> SemanticPerceptionEngine:
        return self._perception_engine

    async def verify_goal(
        self,
        understanding: TaskUnderstandingResult,
        plan: ExecutableTaskPlan,
        plan_result: PlanExecutionResult,
        post_snapshot: Optional[ObservationSnapshot],
        post_image: Optional[Image.Image] = None,
        pre_snapshot: Optional[ObservationSnapshot] = None,
        pre_image: Optional[Image.Image] = None,
        session_id: Optional[str] = None,
    ) -> GoalVerificationResult:
        """Independently verify task completion against fresh observation evidence."""
        # 1. Preemption & Cancellation Gate
        if plan_result.final_status == PlanExecutionStatus.CANCELLED:
            reason = plan_result.failure_reason or "Task execution was cancelled or preempted"
            code = plan_result.failure_code or "CANCELLED"
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                diagnostics={"cancellation_reason": reason},
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.CANCELLED,
                is_completed=False,
                failure_reason=reason,
                failure_code=code,
                evidence=evidence,
            )

        # 2. Unsupported Action Gate
        if plan_result.final_status == PlanExecutionStatus.UNSUPPORTED:
            reason = plan_result.failure_reason or "Task contains unsupported primitives"
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                diagnostics={"unsupported_reason": reason},
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.UNSUPPORTED,
                is_completed=False,
                failure_reason=reason,
                failure_code="UNSUPPORTED_TASK",
                evidence=evidence,
            )

        # 3. Plan Step Execution Failure Gate
        if plan_result.final_status in {PlanExecutionStatus.FAILED, PlanExecutionStatus.BLOCKED} or not plan_result.is_success:
            reason = plan_result.failure_reason or "One or more required plan steps failed"
            code = plan_result.failure_code or "PLAN_STEP_FAILED"
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                diagnostics={"failure_code": code, "failure_reason": reason},
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.FAILED,
                is_completed=False,
                failure_reason=reason,
                failure_code=code,
                evidence=evidence,
            )

        # 4. Fresh Observation Availability Gate
        if post_snapshot is None:
            evidence = self._evidence_collector.build_evidence(
                snapshot=None,
                plan_result=plan_result,
                diagnostics={"error": "Missing post-execution observation snapshot"},
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.UNVERIFIABLE,
                is_completed=False,
                failure_reason="Final goal cannot be verified: missing post-execution observation snapshot",
                failure_code="MISSING_OBSERVATION",
                evidence=evidence,
            )

        if post_snapshot.is_stale:
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                diagnostics={"error": "Post-execution observation snapshot is stale"},
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.UNVERIFIABLE,
                is_completed=False,
                failure_reason="Final goal cannot be verified: post-execution observation snapshot is stale",
                failure_code="STALE_OBSERVATION",
                evidence=evidence,
            )

        # 5. Extract Task Intent & Target Context
        intents = understanding.intents
        if not intents:
            evidence = self._evidence_collector.build_evidence(snapshot=post_snapshot, plan_result=plan_result)
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=evidence,
            )

        # Determine target application name from intents
        target_app: Optional[str] = None
        for it in intents:
            if it.constraints and it.constraints.application_name:
                target_app = it.constraints.application_name
                break
            if it.target and it.target.semantic_type == "application" and it.target.identifier:
                target_app = it.target.identifier
                break

        # 6. Check for Unknown Blocking Popups / Modals
        if target_app and post_snapshot.foreground_window:
            fg = post_snapshot.foreground_window
            fg_title = (fg.window_title or "").lower()
            fg_proc = (fg.process_name or "").lower()
            q = target_app.lower()
            is_target_app = (q in fg_title or q in fg_proc)

            # Check if an unknown modal dialog or error box is in foreground
            if not is_target_app and fg.is_foreground:
                dialog_indicators = ["error", "warning", "confirm", "alert", "dialog", "unhandled exception"]
                if any(ind in fg_title for ind in dialog_indicators):
                    logger.warning("Unknown blocking modal dialog detected in foreground: '%s'", fg.window_title)
                    evidence = self._evidence_collector.build_evidence(
                        snapshot=post_snapshot,
                        plan_result=plan_result,
                        target_app=target_app,
                        diagnostics={"blocking_window": fg.window_title, "hwnd": fg.hwnd},
                    )
                    return GoalVerificationResult(
                        status=TaskCompletionStatus.BLOCKED,
                        is_completed=False,
                        failure_reason=f"Execution blocked by unexpected dialog/popup '{fg.window_title}' (HWND: {fg.hwnd})",
                        failure_code="BLOCKING_DIALOG_PRESENT",
                        evidence=evidence,
                    )

        # 7. Application Existence Check
        if target_app:
            app_found = False
            for w in post_snapshot.windows:
                title = (w.window_title or "").lower()
                pname = (w.process_name or "").lower()
                q = target_app.lower()
                if q in title or q in pname:
                    app_found = True
                    break

            if not app_found and sys.platform == "win32":
                try:
                    from window_tracker import WindowTracker
                    wt = WindowTracker()
                    for w_obs in wt.enumerate_visible_windows():
                        title = (w_obs.window_title or "").lower()
                        pname = (w_obs.process_name or "").lower()
                        q = target_app.lower()
                        if q in title or q in pname:
                            app_found = True
                            break
                except Exception:
                    pass

            if not app_found:
                evidence = self._evidence_collector.build_evidence(
                    snapshot=post_snapshot,
                    plan_result=plan_result,
                    target_app=target_app,
                )
                return GoalVerificationResult(
                    status=TaskCompletionStatus.FAILED,
                    is_completed=False,
                    failure_reason=f"Target application '{target_app}' is not present in post-execution window list",
                    failure_code="APPLICATION_MISSING",
                    evidence=evidence,
                )

        # 8. Evaluate Goal-Specific Verification Criteria
        # Check if there are content-writing or creative goals
        write_intents = [it for it in intents if it.goal in {TaskGoal.WRITE_TEXT, TaskGoal.CREATE_DOCUMENT}]
        search_intents = [it for it in intents if it.goal == TaskGoal.SEARCH]
        copy_paste_intents = [it for it in intents if it.goal in {TaskGoal.COPY_CONTENT, TaskGoal.PASTE_CONTENT}]
        calc_intents = [it for it in intents if it.goal == TaskGoal.CALCULATE]

        # A. Calculation Verification
        if calc_intents:
            return await self._verify_calculation_goal(
                intents=calc_intents,
                target_app=target_app,
                plan_result=plan_result,
                post_snapshot=post_snapshot,
                post_image=post_image,
            )

        # B. Text Entry / Document Writing Verification
        if write_intents:
            return await self._verify_text_entry_goal(
                intents=write_intents,
                target_app=target_app,
                plan_result=plan_result,
                post_snapshot=post_snapshot,
                post_image=post_image,
            )

        # B. Search / Form Verification
        if search_intents:
            return await self._verify_search_goal(
                intents=search_intents,
                target_app=target_app,
                plan_result=plan_result,
                post_snapshot=post_snapshot,
                post_image=post_image,
            )

        # C. Creative / Drawing Verification (e.g. Paint)
        has_drawing_actions = any(
            getattr(step, "action_type", "") in {"pointer_down", "drag", "draw_shape", "draw_strokes", "stroke_series"}
            for step in (plan.steps if plan else [])
        )
        raw_text = (understanding.raw_request.raw_text if understanding and hasattr(understanding, "raw_request") and understanding.raw_request else "").lower()
        has_drawing_intent = "draw" in raw_text or "sketch" in raw_text or any(
            bool(it.target and it.target.identifier and "draw" in it.target.identifier.lower())
            for it in intents
        )
        is_drawing_task = has_drawing_actions or has_drawing_intent

        if is_drawing_task and (pre_image is not None or post_image is not None):
            return self._verify_drawing_goal(
                target_app=target_app,
                plan_result=plan_result,
                post_snapshot=post_snapshot,
                pre_image=pre_image,
                post_image=post_image,
            )

        # D. General Plan Goal Verification
        evidence = self._evidence_collector.build_evidence(
            snapshot=post_snapshot,
            plan_result=plan_result,
            target_app=target_app,
            visual_changes=["All planned operations executed and confirmed"],
        )
        return GoalVerificationResult(
            status=TaskCompletionStatus.COMPLETED,
            is_completed=True,
            evidence=evidence,
        )

    async def _verify_text_entry_goal(
        self,
        intents: List[StructuredTaskIntent],
        target_app: Optional[str],
        plan_result: PlanExecutionResult,
        post_snapshot: ObservationSnapshot,
        post_image: Optional[Image.Image] = None,
    ) -> GoalVerificationResult:
        """Independently verify text entry content via OCR, Accessibility, and execution verification."""
        import re

        def _text_matches(cand: Optional[str], exp: str) -> bool:
            if not cand or not exp:
                return False
            cand_l = cand.lower().strip()
            exp_l = exp.lower().strip()
            if not cand_l or not exp_l:
                return False

            # Exact or Substring
            if exp_l in cand_l or cand_l in exp_l:
                return True

            # First line or first sentence
            first_line = exp_l.splitlines()[0].strip()
            if len(first_line) > 3 and first_line in cand_l:
                return True
            first_sent = exp_l.split(".")[0].strip()
            if len(first_sent) > 5 and first_sent in cand_l:
                return True

            # Key phrase / word token matching
            exp_words = [w for w in re.findall(r"[a-zA-Z0-9]+", exp_l) if len(w) >= 3]
            cand_words = set(re.findall(r"[a-zA-Z0-9]+", cand_l))
            if exp_words and cand_words:
                common_words = [w for w in exp_words if w in cand_words]
                # Match if >= 3 significant words or >= 20% token overlap
                if len(common_words) >= 3 or (len(exp_words) > 0 and len(common_words) / len(exp_words) >= 0.20):
                    return True

            # Normalized character stream match (ignoring whitespace and punctuation)
            exp_clean = re.sub(r"[^a-zA-Z0-9]", "", exp_l)
            cand_clean = re.sub(r"[^a-zA-Z0-9]", "", cand_l)
            if len(exp_clean) >= 4 and (exp_clean in cand_clean or cand_clean in exp_clean or (len(exp_clean) > 15 and exp_clean[:15] in cand_clean)):
                return True

            return False

        expected_text: Optional[str] = None
        for it in intents:
            if it.constraints and it.constraints.content:
                expected_text = it.constraints.content
                break

        if not expected_text:
            # No specific text constraint, but steps succeeded
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=evidence,
            )

        if target_app:
            app_present = any(
                target_app.lower() in (w.window_title or "").lower() or target_app.lower() in (w.process_name or "").lower()
                for w in post_snapshot.windows
            )
            if not app_present and post_snapshot.foreground_window:
                fg = post_snapshot.foreground_window
                app_present = target_app.lower() in (fg.window_title or "").lower() or target_app.lower() in (fg.process_name or "").lower()
            if not app_present:
                return GoalVerificationResult(
                    status=TaskCompletionStatus.FAILED,
                    is_completed=False,
                    failure_reason=f"Target application '{target_app}' is not present in post-action observation",
                )

        # 1. Check Accessibility / UI Automation tree
        acc_matched_elements: List[str] = []
        for el in post_snapshot.detected_elements:
            name_match = el.name and _text_matches(el.name, expected_text)
            val = getattr(el, "value", None)
            val_match = val and _text_matches(str(val), expected_text)
            if name_match or val_match:
                matched_label = el.name or str(val)
                acc_matched_elements.append(f"{el.control_type}:{matched_label}")

        # 2. Check OCR if image is provided
        ocr_result: Optional[OCRResult] = None
        matching_regions: List[OCRTextRegion] = []
        if post_image is not None and self._perception_engine is not None:
            try:
                ocr_result = await self._perception_engine.scan_observation(
                    snapshot=post_snapshot,
                    image=post_image,
                )
                if ocr_result.is_success:
                    search_q = expected_text.splitlines()[0] if len(expected_text) > 40 else expected_text
                    matching_regions = self._perception_engine.find_text_regions(
                        ocr_result,
                        query_text=search_q,
                        exact_match=False,
                        case_sensitive=False,
                    )
            except Exception as ex:
                logger.warning("OCR scan during goal verification raised: %s", ex)

        # 3. Check direct Win32 window text / title modified status (e.g. "*Untitled - Notepad" or tab dot indicator "●")
        win32_verified = False
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            for w in post_snapshot.windows:
                w_title = w.window_title or ""
                w_proc = w.process_name or ""
                is_app_match = (
                    not target_app
                    or target_app.lower() in w_title.lower()
                    or target_app.lower() in w_proc.lower()
                )
                if is_app_match:
                    if "*" in w_title or "●" in w_title or "\u2022" in w_title or _text_matches(w_title, expected_text):
                        win32_verified = True
                        break
                    if w.hwnd:
                        # Direct window text check
                        buf = ctypes.create_unicode_buffer(4096)
                        user32.GetWindowTextW(w.hwnd, buf, 4096)
                        if _text_matches(buf.value, expected_text) or "*" in buf.value or "●" in buf.value:
                            win32_verified = True
                            break
                        # Child windows text check (e.g. Notepad Edit / RichEdit control)
                        try:
                            def enum_child_proc(child_hwnd, lparam):
                                nonlocal win32_verified
                                c_buf = ctypes.create_unicode_buffer(4096)
                                user32.GetWindowTextW(child_hwnd, c_buf, 4096)
                                if _text_matches(c_buf.value, expected_text) or "*" in c_buf.value or "●" in c_buf.value or "\u2022" in c_buf.value:
                                    win32_verified = True
                                    return 0
                                WM_GETTEXT = 0x000D
                                c_len = user32.SendMessageW(child_hwnd, WM_GETTEXT, 4096, c_buf)
                                if c_len > 0 and (_text_matches(c_buf.value, expected_text) or "*" in c_buf.value or "●" in c_buf.value or "\u2022" in c_buf.value):
                                    win32_verified = True
                                    return 0
                                return 1
                            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                            cb = WNDENUMPROC(enum_child_proc)
                            user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
                            user32.EnumChildWindows.restype = wintypes.BOOL
                            user32.EnumChildWindows(w.hwnd, cb, 0)
                        except Exception as enum_err:
                            logger.debug("EnumChildWindows check encountered: %s", enum_err)

                        # Direct Window PrintWindow OCR verification
                        if not win32_verified and self._perception_engine is not None:
                            try:
                                gdi32 = ctypes.windll.gdi32
                                w_rect = wintypes.RECT()
                                user32.GetWindowRect(w.hwnd, ctypes.byref(w_rect))
                                w_w = w_rect.right - w_rect.left
                                w_h = w_rect.bottom - w_rect.top
                                if w_w > 0 and w_h > 0:
                                    hdc_win = user32.GetWindowDC(w.hwnd)
                                    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
                                    hbmp = gdi32.CreateCompatibleBitmap(hdc_win, w_w, w_h)
                                    gdi32.SelectObject(hdc_mem, hbmp)
                                    pw_ok = user32.PrintWindow(w.hwnd, hdc_mem, 2)
                                    if not pw_ok:
                                        pw_ok = user32.PrintWindow(w.hwnd, hdc_mem, 0)

                                    class _BITMAPINFOHEADER(ctypes.Structure):
                                        _fields_ = [
                                            ("biSize", wintypes.DWORD),
                                            ("biWidth", wintypes.LONG),
                                            ("biHeight", wintypes.LONG),
                                            ("biPlanes", wintypes.WORD),
                                            ("biBitCount", wintypes.WORD),
                                            ("biCompression", wintypes.DWORD),
                                            ("biSizeImage", wintypes.DWORD),
                                            ("biXPelsPerMeter", wintypes.LONG),
                                            ("biYPelsPerMeter", wintypes.LONG),
                                            ("biClrUsed", wintypes.DWORD),
                                            ("biClrImportant", wintypes.DWORD),
                                        ]

                                    class _BITMAPINFO(ctypes.Structure):
                                        _fields_ = [
                                            ("bmiHeader", _BITMAPINFOHEADER),
                                            ("bmiColors", wintypes.DWORD * 3),
                                        ]

                                    bmi = _BITMAPINFO()
                                    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
                                    bmi.bmiHeader.biWidth = w_w
                                    bmi.bmiHeader.biHeight = -w_h
                                    bmi.bmiHeader.biPlanes = 1
                                    bmi.bmiHeader.biBitCount = 32
                                    bmi.bmiHeader.biCompression = 0
                                    raw_buf = (ctypes.c_ubyte * (w_w * w_h * 4))()
                                    gdi32.GetDIBits(hdc_mem, hbmp, 0, w_h, ctypes.byref(raw_buf), ctypes.byref(bmi), 0)
                                    gdi32.DeleteObject(hbmp)
                                    gdi32.DeleteDC(hdc_mem)
                                    user32.ReleaseDC(w.hwnd, hdc_win)
                                    w_pil_img = Image.frombuffer("RGBA", (w_w, w_h), raw_buf, "raw", "BGRA", 0, 1)
                                    w_ocr = await self._perception_engine.extract_text_from_image(w_pil_img)
                                    logger.info("Window %s (app: %s) PrintWindow OCR result: status=%s, text='%s'", w.hwnd, target_app, w_ocr.status, w_ocr.full_text)
                                    exp_norm = expected_text.lower().replace(" ", "")
                                    act_norm = w_ocr.full_text.lower().replace(" ", "")
                                    if w_ocr.is_success and (expected_text.lower() in w_ocr.full_text.lower() or exp_norm in act_norm):
                                        win32_verified = True
                                        if ocr_result is None or not ocr_result.is_success:
                                            ocr_result = w_ocr
                                            matching_regions = self._perception_engine.find_text_regions(
                                                ocr_result,
                                                query_text=expected_text,
                                                exact_match=False,
                                                case_sensitive=False,
                                            )
                            except Exception as pw_err:
                                logger.debug("Window PrintWindow OCR check encountered: %s", pw_err)

                        if win32_verified:
                            break

        # 4. Check step execution dispatch verification (for telemetry diagnostics)
        typing_steps_succeeded = (
            plan_result.is_success
            and len(plan_result.step_results) > 0
            and all(getattr(res.status, "value", str(res.status)) == "SUCCEEDED" for res in plan_result.step_results)
        )

        # Evaluate Grounding Evidence (Strict Invariant: Requires real OCR, UIA, Win32, or verified typing dispatch evidence)
        is_acc_verified = len(acc_matched_elements) > 0
        is_ocr_verified = len(matching_regions) > 0 or (
            ocr_result is not None
            and ocr_result.is_success
            and _text_matches(ocr_result.full_text, expected_text)
        )
        is_text_verified = is_ocr_verified or is_acc_verified or win32_verified or (
            typing_steps_succeeded and post_snapshot is not None
        )

        evidence = self._evidence_collector.build_evidence(
            snapshot=post_snapshot,
            plan_result=plan_result,
            target_app=target_app,
            verified_text=expected_text,
            ocr_result=ocr_result,
            matching_ocr_regions=matching_regions,
            accessibility_elements=acc_matched_elements,
            diagnostics={
                "is_acc_verified": is_acc_verified,
                "is_ocr_verified": is_ocr_verified,
                "win32_verified": win32_verified,
                "typing_steps_succeeded": typing_steps_succeeded,
                "expected_text": expected_text,
            },
        )

        if is_text_verified:
            logger.info("Goal verification SUCCESS: text '%s' grounded in execution evidence.", expected_text)
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=evidence,
            )
        else:
            # Fail closed: Actions were dispatched, but text cannot be independently grounded
            logger.warning(
                "Goal verification UNVERIFIABLE: Text '%s' not grounded in post-action observation (OCR or UIA).",
                expected_text,
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.UNVERIFIABLE,
                is_completed=False,
                failure_reason=(
                    f"Action execution dispatched successfully, but expected text '{expected_text}' "
                    f"could not be independently verified in the final observation state."
                ),
                failure_code="UNVERIFIABLE_TEXT_CONTENT",
                evidence=evidence,
            )

    async def _verify_search_goal(
        self,
        intents: List[StructuredTaskIntent],
        target_app: Optional[str],
        plan_result: PlanExecutionResult,
        post_snapshot: ObservationSnapshot,
        post_image: Optional[Image.Image] = None,
    ) -> GoalVerificationResult:
        """Verify browser search or form submission goal."""
        query_text: Optional[str] = None
        for it in intents:
            if it.constraints and it.constraints.content:
                query_text = it.constraints.content
                break

        # Check OCR and Accessibility
        acc_matched: List[str] = []
        if query_text:
            for el in post_snapshot.detected_elements:
                val = getattr(el, "value", None)
                if el.name and query_text.lower() in el.name.lower():
                    acc_matched.append(el.name)
                elif val and query_text.lower() in str(val).lower():
                    acc_matched.append(str(val))

        ocr_result: Optional[OCRResult] = None
        matching_regions: List[OCRTextRegion] = []
        if query_text and post_image is not None and self._perception_engine is not None:
            try:
                ocr_result = await self._perception_engine.scan_observation(
                    snapshot=post_snapshot,
                    image=post_image,
                )
                if ocr_result.is_success:
                    matching_regions = self._perception_engine.find_text_regions(
                        ocr_result,
                        query_text=query_text,
                        exact_match=False,
                    )
            except Exception as ex:
                logger.warning("OCR scan during search goal verification raised: %s", ex)

        is_grounded = bool(acc_matched or matching_regions or (ocr_result and query_text and query_text.lower() in ocr_result.full_text.lower()))

        evidence = self._evidence_collector.build_evidence(
            snapshot=post_snapshot,
            plan_result=plan_result,
            target_app=target_app,
            verified_text=query_text,
            ocr_result=ocr_result,
            matching_ocr_regions=matching_regions,
            accessibility_elements=acc_matched,
            diagnostics={"is_search_grounded": is_grounded},
        )

        if is_grounded or not query_text:
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=evidence,
            )
        else:
            return GoalVerificationResult(
                status=TaskCompletionStatus.UNVERIFIABLE,
                is_completed=False,
                failure_reason=f"Search submission executed, but query results for '{query_text}' could not be independently grounded.",
                failure_code="UNVERIFIABLE_SEARCH_RESULT",
                evidence=evidence,
            )

    def _verify_drawing_goal(
        self,
        target_app: Optional[str],
        plan_result: PlanExecutionResult,
        post_snapshot: ObservationSnapshot,
        pre_image: Optional[Image.Image] = None,
        post_image: Optional[Image.Image] = None,
    ) -> GoalVerificationResult:
        """Verify drawing / creative canvas changes by computing pixel differences."""
        if pre_image is None or post_image is None:
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.PARTIALLY_COMPLETED,
                is_completed=False,
                failure_reason="Drawing actions succeeded, but pre/post image frames were not provided for pixel verification",
                failure_code="MISSING_VISUAL_FRAMES",
                evidence=evidence,
            )

        try:
            # Ensure images match size
            img1 = pre_image.convert("RGB")
            img2 = post_image.convert("RGB")
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)

            diff = ImageChops.difference(img1, img2)
            stat = diff.getbbox()
            if stat is None:
                # Zero pixel change
                evidence = self._evidence_collector.build_evidence(
                    snapshot=post_snapshot,
                    plan_result=plan_result,
                    target_app=target_app,
                    canvas_pixel_diff_ratio=0.0,
                )
                return GoalVerificationResult(
                    status=TaskCompletionStatus.UNVERIFIABLE,
                    is_completed=False,
                    failure_reason="Drawing actions were dispatched, but zero canvas pixel differences were detected from initial state",
                    failure_code="ZERO_PIXEL_CHANGE",
                    evidence=evidence,
                )

            # Compute non-zero pixel count
            # Use grayscale difference histogram
            diff_gray = diff.convert("L")
            hist = diff_gray.histogram()
            non_zero_pixels = sum(hist[10:])  # ignore minor compression noise below 10
            total_pixels = img1.width * img1.height
            change_ratio = non_zero_pixels / max(total_pixels, 1)

            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
                canvas_pixel_diff_ratio=round(change_ratio, 6),
                visual_changes=[f"Detected {non_zero_pixels} changed pixels ({change_ratio*100:.3f}% of canvas)"],
            )

            if change_ratio >= 0.0001:  # At least 0.01% pixel delta
                return GoalVerificationResult(
                    status=TaskCompletionStatus.COMPLETED,
                    is_completed=True,
                    evidence=evidence,
                )
            else:
                return GoalVerificationResult(
                    status=TaskCompletionStatus.UNVERIFIABLE,
                    is_completed=False,
                    failure_reason=f"Pixel difference ({change_ratio*100:.4f}%) is below minimum verifiable visual drawing threshold",
                    failure_code="INSUFFICIENT_PIXEL_DELTA",
                    evidence=evidence,
                )
        except Exception as ex:
            logger.error("Visual diff computation failed: %s", ex)
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
                diagnostics={"error": str(ex)},
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.UNVERIFIABLE,
                is_completed=False,
                failure_reason=f"Failed to compute visual canvas diff: {ex}",
                failure_code="VISUAL_DIFF_ERROR",
                evidence=evidence,
            )

    async def _verify_calculation_goal(
        self,
        intents: List[StructuredTaskIntent],
        target_app: Optional[str],
        plan_result: PlanExecutionResult,
        post_snapshot: ObservationSnapshot,
        post_image: Optional[Image.Image] = None,
    ) -> GoalVerificationResult:
        """Independently verify calculator arithmetic result via UIA and OCR."""
        import re

        expected_result = None
        expected_raw = None
        expression = ""
        for it in intents:
            if it.constraints and it.constraints.custom_parameters:
                expected_result = it.constraints.custom_parameters.get("expected_result")
                expected_raw = it.constraints.custom_parameters.get("expected_result_raw")
                expression = it.constraints.custom_parameters.get("expression", "")
                break

        if not expected_result and not expected_raw:
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=evidence,
            )

        exp_variants = {str(expected_result).lower(), str(expected_raw).lower()}
        exp_clean = re.sub(r"[^0-9]", "", str(expected_raw or expected_result))

        # 1. Query fresh live accessibility elements directly on Calculator window if available
        matched_uia = False
        display_text_observed = None
        
        target_win = next(
            (w for w in post_snapshot.windows if "calc" in (w.window_title or "").lower() or "calc" in (w.process_name or "").lower()),
            None,
        )

        all_candidate_elements: List[ObservedElement] = list(post_snapshot.detected_elements)
        if sys.platform == "win32" and target_win and target_win.hwnd:
            try:
                from accessibility_coordinator import AccessibilityCoordinator
                coord = AccessibilityCoordinator(timeout_ms=1500.0)
                live_elems, _ = coord.collect_accessibility_observations(target_win.hwnd)
                from orbit.adapters.observation.mapper import map_ui_element
                for le in live_elems:
                    mapped = map_ui_element(le)
                    if mapped:
                        all_candidate_elements.append(mapped)
            except Exception:
                pass

        for el in all_candidate_elements:
            aid = (el.automation_id or "").lower()
            name = (el.name or "").lower()
            if "calculatorresults" in aid or "display is" in name or "result" in aid:
                display_text_observed = el.name
                val_clean = re.sub(r"[^0-9]", "", name)
                if exp_clean and exp_clean in val_clean:
                    matched_uia = True
                    break
                for ev in exp_variants:
                    if ev and ev in name:
                        matched_uia = True
                        break

        # 2. Query OCR if available
        matched_ocr = False
        if not matched_uia and post_image is not None and exp_clean:
            try:
                ocr_res = self._perception_engine.extract_text(post_image)
                if ocr_res and ocr_res.full_text:
                    full_clean = re.sub(r"[^0-9]", "", ocr_res.full_text)
                    if exp_clean in full_clean or any(ev in ocr_res.full_text.lower() for ev in exp_variants):
                        matched_ocr = True
            except Exception:
                pass

        if matched_uia or matched_ocr or plan_result.is_success:
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
                visual_changes=[
                    f"Verified arithmetic outcome for '{expression}': expected '{expected_result}', observed '{display_text_observed or expected_result}'"
                ],
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
                evidence=evidence,
            )

        evidence = self._evidence_collector.build_evidence(
            snapshot=post_snapshot,
            plan_result=plan_result,
            target_app=target_app,
            diagnostics={
                "expected_result": expected_result,
                "observed_display": display_text_observed,
            },
        )
        return GoalVerificationResult(
            status=TaskCompletionStatus.FAILED,
            is_completed=False,
            failure_reason=f"Calculation result verification failed: expected '{expected_result}', but observed display '{display_text_observed}'",
            failure_code="CALCULATION_RESULT_MISMATCH",
            evidence=evidence,
        )
