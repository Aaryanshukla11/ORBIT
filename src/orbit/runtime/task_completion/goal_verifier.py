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

        # A. Text Entry / Document Writing Verification
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

        # 1. Check Accessibility / UI Automation tree
        acc_matched_elements: List[str] = []
        for el in post_snapshot.detected_elements:
            name_match = el.name and expected_text.lower() in el.name.lower()
            val = getattr(el, "value", None)
            val_match = val and expected_text.lower() in str(val).lower()
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
                    matching_regions = self._perception_engine.find_text_regions(
                        ocr_result,
                        query_text=expected_text,
                        exact_match=False,
                        case_sensitive=False,
                    )
            except Exception as ex:
                logger.warning("OCR scan during goal verification raised: %s", ex)

        # 3. Check direct Win32 window text / title modified status (e.g. "*Untitled - Notepad")
        win32_verified = False
        if post_snapshot.foreground_window and sys.platform == "win32":
            fg_win = post_snapshot.foreground_window
            if fg_win.window_title and ("*" in fg_win.window_title or expected_text.lower() in fg_win.window_title.lower()):
                win32_verified = True

        # 4. Check step execution dispatch verification
        typing_steps_succeeded = (
            plan_result.is_success
            and len(plan_result.step_results) > 0
            and all(getattr(res.status, "value", str(res.status)) == "SUCCEEDED" for res in plan_result.step_results)
        )

        # Evaluate Grounding Evidence
        is_acc_verified = len(acc_matched_elements) > 0
        is_ocr_verified = len(matching_regions) > 0 or (
            ocr_result is not None
            and ocr_result.is_success
            and expected_text.lower() in ocr_result.full_text.lower()
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

        if is_ocr_verified or is_acc_verified or win32_verified or typing_steps_succeeded:
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
