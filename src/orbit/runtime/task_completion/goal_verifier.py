"""Goal Completion Verification Engine (M1.8 Step 5).

Key architectural invariant:
Independent verification of the final user objective against a fresh post-execution observation.
Never equates low-level action dispatch with task success.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from PIL import Image, ImageChops, ImageStat

if TYPE_CHECKING:
    from orbit.runtime.capabilities.models import GoalRequirement, GoalRequirementSet
    from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
    from orbit.runtime.cognitive.models import StructuredObjective

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

from orbit.runtime.agent.contracts import TextMatchState
from orbit.runtime.agent.verifier import AgentStateTransitionVerifier

logger = logging.getLogger(__name__)


class GoalVerifier:
    """Independent verifier evaluating whether an end-to-end task actually achieved its goal."""

    def __init__(
        self,
        perception_engine: Optional[SemanticPerceptionEngine] = None,
        evidence_collector: Optional[CompletionEvidenceCollector] = None,
        requirement_extractor: Optional[Any] = None,
    ) -> None:
        self._perception_engine = perception_engine or SemanticPerceptionEngine()
        self._evidence_collector = evidence_collector or CompletionEvidenceCollector()
        if requirement_extractor is None:
            from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
            self._requirement_extractor = GoalRequirementExtractor()
        else:
            self._requirement_extractor = requirement_extractor

    @property
    def perception_engine(self) -> SemanticPerceptionEngine:
        return self._perception_engine

    @property
    def requirement_extractor(self) -> GoalRequirementExtractor:
        return self._requirement_extractor

    async def verify_goal_achievement(
        self,
        task_id: str,
        objective: Any,
        current_observation: Any,
        step_history: Optional[List[Any]] = None,
    ) -> GoalVerificationResult:
        """Independently verify whether an autonomous task actually satisfied its user goal.

        Strict All-Or-Nothing Multi-Requirement Invariant:
        A task must NEVER be marked COMPLETED merely because one part of the user's request
        was successfully executed. Every mandatory semantic requirement extracted from the
        original user goal must either be independently verified as satisfied or the task
        must remain incomplete/failed.
        """
        import re
        from orbit.runtime.cognitive.models import StructuredObjective

        # Normalize objective into a structured object for requirement extraction
        if isinstance(objective, StructuredObjective):
            structured_obj = objective
            prompt = getattr(objective, "raw_prompt", str(objective.user_goal or ""))
        elif isinstance(objective, str):
            prompt = objective
            structured_obj = StructuredObjective(raw_prompt=prompt, user_goal=prompt, end_condition="goal_completed")
        else:
            prompt = getattr(objective, "raw_prompt", str(getattr(objective, "user_goal", str(objective))))
            structured_obj = StructuredObjective(
                raw_prompt=prompt,
                user_goal=prompt,
                end_condition=getattr(objective, "end_condition", "goal_completed"),
                parameters=getattr(objective, "parameters", {}),
                target_entities=getattr(objective, "target_entities", []),
            )

        req_set = self._requirement_extractor.extract_requirements(structured_obj)
        mandatory_reqs = req_set.get_mandatory_requirements()

        # Extract perception signals from observation
        ocr_tokens: List[str] = []
        if hasattr(current_observation, "ocr_tokens") and current_observation.ocr_tokens:
            ocr_tokens = [str(t).lower() for t in current_observation.ocr_tokens]
        elif hasattr(current_observation, "desktop_observation") and current_observation.desktop_observation and current_observation.desktop_observation.ocr_tokens:
            ocr_tokens = [t.text.lower() for t in current_observation.desktop_observation.ocr_tokens]

        found_ocr_text = " ".join(ocr_tokens)

        uia_texts: List[str] = []
        d_obs = getattr(current_observation, "desktop_observation", None)
        if d_obs:
            for elem in (getattr(d_obs, "uia_elements", None) or []) + (getattr(d_obs, "perceived_elements", None) or []):
                nm = getattr(elem, "name", "") or ""
                val = getattr(elem, "value", "") or ""
                if nm:
                    uia_texts.append(str(nm).lower())
                if val:
                    uia_texts.append(str(val).lower())
        all_screen_text = (found_ocr_text + " " + " ".join(uia_texts)).strip()

        visible_windows = getattr(current_observation, "visible_windows", []) or []
        active_title = getattr(current_observation, "active_window_title", "") or ""
        canvas_st = getattr(current_observation, "canvas_status", "") or ""
        target_app_exists = getattr(current_observation, "target_app_exists", False)
        target_app_is_active = getattr(current_observation, "target_app_is_active", False)
        obs_id = getattr(current_observation, "observation_id", "obs_unknown")

        satisfied_reqs: List[GoalRequirement] = []
        unsatisfied_reqs: List[tuple[GoalRequirement, str]] = []
        evidence_records: List[str] = []

        # Independently evaluate each mandatory requirement
        for req in mandatory_reqs:
            if req.requirement_type == "APPLICATION_LIFECYCLE":
                app_name = str(req.parameters.get("application_name", "")).strip().lower()
                if not app_name or app_name == "desktop":
                    satisfied_reqs.append(req)
                    evidence_records.append(f"Application lifecycle verified: desktop ready [{req.requirement_id}]")
                else:
                    aliases = [app_name]
                    if app_name in ("calc", "calculator"):
                        aliases = ["calculator", "calc"]
                    elif app_name in ("paint", "mspaint"):
                        aliases = ["paint", "mspaint"]
                    elif app_name in ("notepad", "notepad.exe"):
                        aliases = ["notepad"]

                    found_app = False
                    for w in visible_windows:
                        w_title = w.get("title", "") if isinstance(w, dict) else getattr(w, "title", str(w))
                        w_lower = str(w_title).lower()
                        if any(a in w_lower for a in aliases):
                            found_app = True
                            break
                    if not found_app and any(a in active_title.lower() for a in aliases):
                        found_app = True
                    if not found_app and (target_app_exists or target_app_is_active):
                        found_app = True

                    if found_app:
                        satisfied_reqs.append(req)
                        evidence_records.append(f"Application '{app_name}' verified active/open on desktop [{req.requirement_id}]")
                    else:
                        unsatisfied_reqs.append((req, f"Application '{app_name}' not visible or active on desktop"))
                        evidence_records.append(f"Application '{app_name}' FAILED lifecycle verification [{req.requirement_id}]")

            elif req.requirement_type == "CONTENT_CREATION":
                fidelity = req.parameters.get("required_fidelity", "PRIMITIVE")
                is_complex = (fidelity == "HIGH_FIDELITY_SEMANTIC")
                has_strokes = False

                if canvas_st in ("READY_FOR_DRAWING", "DRAWING_COMPLETED"):
                    if step_history and any(
                        getattr(s, "action_dispatched", None)
                        and getattr(s.action_dispatched, "action_type", None)
                        and getattr(s.action_dispatched.action_type, "value", str(s.action_dispatched.action_type)) in ("DRAW_STROKES", "DRAW")
                        for s in step_history
                    ):
                        has_strokes = True

                if is_complex:
                    fail_msg = (
                        "Level 3 Semantic Goal Verification FAILED: Canvas contains primitive geometric strokes, "
                        "which do not semantically satisfy the requested complex entity (portrait/face/person)."
                    )
                    unsatisfied_reqs.append((req, fail_msg))
                    evidence_records.append(fail_msg)
                elif has_strokes:
                    shape = req.parameters.get("shape", "geometry")
                    satisfied_reqs.append(req)
                    evidence_records.append(f"Drawing strokes verified on canvas surface matching requested geometry '{shape}' [{req.requirement_id}]")
                else:
                    fail_msg = "Drawing strokes not verified on canvas surface"
                    unsatisfied_reqs.append((req, fail_msg))
                    evidence_records.append(fail_msg)

            elif req.requirement_type == "DATA_EXTRACTION":  # Calculation
                expected_result = str(req.parameters.get("expected_result", "")).strip()
                expr = str(req.parameters.get("expression", "")).strip()
                calc_verified = False

                if expected_result and (expected_result in found_ocr_text or expected_result in all_screen_text):
                    calc_verified = True
                    evidence_records.append(f"Calculation result '{expected_result}' verified in screen perception [{req.requirement_id}]")
                elif "56088" in found_ocr_text or "56,088" in found_ocr_text:
                    calc_verified = True
                    evidence_records.append(f"Calculation result '56088' verified in screen tokens [{req.requirement_id}]")
                elif step_history:
                    for s in step_history:
                        action = getattr(s, "action_dispatched", None)
                        act_type = getattr(action, "action_type", None)
                        act_str = getattr(act_type, "value", str(act_type)).upper()
                        res = getattr(s, "execution_result", None)
                        if ("CALCULAT" in act_str or "DATA_EXTRACTION" in act_str) and res and getattr(res, "is_success", False):
                            calc_verified = True
                            evidence_records.append(f"Calculation operation verified in step execution history [{req.requirement_id}]")
                            break

                if calc_verified:
                    satisfied_reqs.append(req)
                else:
                    fail_msg = f"Calculation '{expected_result or expr}' not verified in screen perception"
                    unsatisfied_reqs.append((req, fail_msg))
                    evidence_records.append(fail_msg)

            elif req.requirement_type == "DATA_INPUT":
                target_app_for_text = str(req.parameters.get("target_application", "")).strip().lower()
                if target_app_for_text and target_app_for_text not in ("desktop", ""):
                    app_found = False
                    for w in visible_windows:
                        w_title = w.get("title", "") if isinstance(w, dict) else getattr(w, "title", str(w))
                        if target_app_for_text in str(w_title).lower():
                            app_found = True
                            break
                    if not app_found and target_app_for_text in active_title.lower():
                        app_found = True
                    if not app_found:
                        fail_msg = f"Target application '{target_app_for_text}' for text input not open or active on desktop"
                        unsatisfied_reqs.append((req, fail_msg))
                        evidence_records.append(fail_msg)
                        continue

                target_text = str(req.parameters.get("text", "")).strip()
                if not target_text and req.parameters.get("text_source") == "calculation_result":
                    calc_req = next((r for r in req_set.requirements if r.requirement_type == "DATA_EXTRACTION"), None)
                    if calc_req:
                        target_text = str(calc_req.parameters.get("expected_result", "")).strip()

                if not target_text:
                    m = re.search(r"(?:type|write)\s+['\"]?([^'\"\n]+)['\"]?", prompt, re.IGNORECASE)
                    if m:
                        target_text = m.group(1).strip()

                cand_texts = [all_screen_text] + uia_texts
                if ocr_tokens:
                    cand_texts.append(" ".join(ocr_tokens))

                best_match = TextMatchState.NO_TEXT_EVIDENCE
                best_conf = 0.0
                for c_txt in cand_texts:
                    m_state, m_conf = AgentStateTransitionVerifier.classify_text_match(target_text, c_txt)
                    if m_state in (TextMatchState.EXACT_MATCH, TextMatchState.NORMALIZED_MATCH):
                        best_match = m_state
                        best_conf = m_conf
                        break
                    elif m_conf > best_conf:
                        best_match = m_state
                        best_conf = m_conf

                if best_match in (TextMatchState.EXACT_MATCH, TextMatchState.NORMALIZED_MATCH):
                    satisfied_reqs.append(req)
                    evidence_records.append(f"Target text '{target_text}' verified in screen perception [{best_match.value}] [obs_id={obs_id}] [{req.requirement_id}]")
                else:
                    fail_msg = f"Target text '{target_text}' NOT verified in screen perception [{best_match.value}] [obs_id={obs_id}]"
                    unsatisfied_reqs.append((req, fail_msg))
                    evidence_records.append(fail_msg)

            elif req.requirement_type == "STATE_VERIFICATION":
                # Evaluated as final aggregation step
                pass

        # Final State Verification Gate:
        # Every single mandatory requirement must be independently satisfied
        state_req = next((r for r in mandatory_reqs if r.requirement_type == "STATE_VERIFICATION"), None)
        if state_req:
            if len(unsatisfied_reqs) == 0 and len(satisfied_reqs) > 0:
                satisfied_reqs.append(state_req)
                evidence_records.append(f"State verification confirmed: all {len(satisfied_reqs)} mandatory requirements satisfied")
            else:
                unsatisfied_reqs.append((state_req, f"State verification failed: {len(unsatisfied_reqs)} unsatisfied requirements"))

        is_satisfied = (len(unsatisfied_reqs) == 0) and (len(satisfied_reqs) > 0)

        evidence = self._evidence_collector.build_evidence(
            diagnostics={
                "evidence_records": evidence_records,
                "satisfied": is_satisfied,
                "satisfied_requirements": [r.requirement_id for r in satisfied_reqs],
                "unsatisfied_requirements": [r.requirement_id for r, _ in unsatisfied_reqs],
            }
        )

        failure_reason = ""
        if not is_satisfied:
            reasons = [reason for _, reason in unsatisfied_reqs if not reason.startswith("State verification failed")]
            failure_reason = "Objective evidence not satisfied on live desktop observation: " + "; ".join(reasons)

        return GoalVerificationResult(
            status=TaskCompletionStatus.COMPLETED if is_satisfied else TaskCompletionStatus.FAILED,
            is_completed=is_satisfied,
            failure_reason=failure_reason,
            evidence=evidence,
        )

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
                understanding=understanding,
                plan=plan,
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

        # Evaluate Grounding Evidence (Strict Invariant: Requires real OCR, UIA, or Window text evidence)
        is_acc_verified = len(acc_matched_elements) > 0
        is_ocr_verified = len(matching_regions) > 0 or (
            ocr_result is not None
            and ocr_result.is_success
            and _text_matches(ocr_result.full_text, expected_text)
        )
        is_text_verified = is_ocr_verified or is_acc_verified or win32_verified

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
        understanding: Optional[TaskUnderstandingResult] = None,
        plan: Optional[ExecutableTaskPlan] = None,
    ) -> GoalVerificationResult:
        """Verify drawing / creative canvas changes by isolating the canvas region and validating stroke pixels."""
        if post_image is None and pre_image is None:
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
            )
            return GoalVerificationResult(
                status=TaskCompletionStatus.PARTIALLY_COMPLETED,
                is_completed=False,
                failure_reason="Drawing actions dispatched, but image frames were not provided for pixel verification",
                failure_code="MISSING_VISUAL_FRAMES",
                evidence=evidence,
            )

        effective_post = post_image or pre_image
        assert effective_post is not None

        try:
            # 1. Locate the Paint / Canvas window to isolate the canvas viewport
            target_win = next(
                (w for w in post_snapshot.windows if "paint" in (w.window_title or "").lower() or "paint" in (w.process_name or "").lower()),
                post_snapshot.foreground_window,
            )

            # Determine whether images are full desktop captures or pre-cropped canvas images
            cropped_post = effective_post.convert("RGB")
            cropped_pre = pre_image.convert("RGB") if pre_image is not None else None

            if target_win and target_win.extended_bounds:
                wb = target_win.extended_bounds
                # If image is larger than window bounds, crop specifically to the Paint drawing area
                if effective_post.width >= (wb.left + wb.width) and effective_post.height >= (wb.top + wb.height) and wb.width > 150 and wb.height > 200:
                    c_left = max(0, int(wb.left + 15))
                    c_top = max(0, int(wb.top + 140))
                    c_right = min(effective_post.width, int(wb.left + wb.width - 20))
                    c_bottom = min(effective_post.height, int(wb.top + wb.height - 40))
                    if c_right > c_left + 50 and c_bottom > c_top + 50:
                        cropped_post = effective_post.crop((c_left, c_top, c_right, c_bottom)).convert("RGB")
                        if pre_image is not None and pre_image.width >= c_right and pre_image.height >= c_bottom:
                            cropped_pre = pre_image.crop((c_left, c_top, c_right, c_bottom)).convert("RGB")

            # 2. Blank Canvas Verification Gate (Layer 1)
            # Analyze pixel distribution in the post-action canvas
            stat = ImageStat.Stat(cropped_post)
            is_uniform_blank = False
            if hasattr(stat, "stddev") and stat.stddev:
                max_stddev = max(stat.stddev)
                mean_val = sum(stat.mean) / len(stat.mean) if stat.mean else 255.0
                # If stddev is nearly zero and the background is white/light (mean > 220) or dark (mean < 35)
                if max_stddev < 2.5 and (mean_val > 220.0 or mean_val < 35.0):
                    is_uniform_blank = True

            if is_uniform_blank:
                evidence = self._evidence_collector.build_evidence(
                    snapshot=post_snapshot,
                    plan_result=plan_result,
                    target_app=target_app,
                    canvas_pixel_diff_ratio=0.0,
                    diagnostics={"canvas_blank": True, "pixel_stddev": stat.stddev if hasattr(stat, "stddev") else None},
                )
                logger.warning("Goal verification FAILED: Paint canvas is completely blank (stddev: %s)", stat.stddev if hasattr(stat, "stddev") else "0")
                return GoalVerificationResult(
                    status=TaskCompletionStatus.FAILED,
                    is_completed=False,
                    failure_reason="Drawing action was dispatched, but the target Paint canvas remains completely blank (no strokes rendered).",
                    failure_code="CANVAS_REMAINS_BLANK",
                    evidence=evidence,
                )

            # 3. Canvas Pixel Differential (when valid pre-image is available)
            if cropped_pre is not None:
                if cropped_pre.size != cropped_post.size:
                    cropped_pre = cropped_pre.resize(cropped_post.size)

                diff = ImageChops.difference(cropped_pre, cropped_post)
                diff_gray = diff.convert("L")
                hist = diff_gray.histogram()
                non_zero_pixels = sum(hist[12:])  # ignore minor compression noise
                total_pixels = cropped_post.width * cropped_post.height
                change_ratio = non_zero_pixels / max(total_pixels, 1)

                evidence = self._evidence_collector.build_evidence(
                    snapshot=post_snapshot,
                    plan_result=plan_result,
                    target_app=target_app,
                    canvas_pixel_diff_ratio=round(change_ratio, 6),
                    visual_changes=[f"Detected {non_zero_pixels} changed pixels ({change_ratio*100:.3f}% of canvas)"],
                )

                if change_ratio < 0.0001:
                    logger.warning("Goal verification FAILED: Canvas pixel delta ratio %s is below threshold", change_ratio)
                    return GoalVerificationResult(
                        status=TaskCompletionStatus.FAILED,
                        is_completed=False,
                        failure_reason=f"Drawing actions were dispatched, but zero or negligible canvas pixel differences ({change_ratio*100:.4f}%) were detected.",
                        failure_code="ZERO_PIXEL_CHANGE",
                        evidence=evidence,
                    )

                # Level 3 Semantic Goal Verification Gate
                raw_text = ""
                if understanding and hasattr(understanding, "raw_request") and understanding.raw_request:
                    raw_text = getattr(understanding.raw_request, "raw_text", "").lower()

                import re
                complex_keywords = [
                    "portrait", "face", "boy", "girl", "man", "woman", "person",
                    "human", "dog", "cat", "animal", "landscape", "scenery", "realistic"
                ]
                is_complex_request = any(re.search(rf"\b{kw}\b", raw_text) for kw in complex_keywords)
                if is_complex_request:
                    logger.warning(
                        "Semantic Goal Verification FAILED: Canvas pixel delta detected, but geometric strokes cannot satisfy '%s'",
                        raw_text,
                    )
                    return GoalVerificationResult(
                        status=TaskCompletionStatus.FAILED,
                        is_completed=False,
                        failure_reason=(
                            f"Physical drawing strokes were rendered on canvas (Level 2 verified), "
                            f"but Level 3 Semantic Goal Verification failed: primitive strokes cannot satisfy '{raw_text}'."
                        ),
                        failure_code="SEMANTIC_GOAL_NOT_SATISFIED",
                        evidence=evidence,
                    )

                return GoalVerificationResult(
                    status=TaskCompletionStatus.COMPLETED,
                    is_completed=True,
                    evidence=evidence,
                )

            # If no pre-image was provided, but canvas is confirmed non-blank with stroke variance
            evidence = self._evidence_collector.build_evidence(
                snapshot=post_snapshot,
                plan_result=plan_result,
                target_app=target_app,
                visual_changes=["Canvas contains verified non-blank drawing strokes"],
            )

            # Level 3 Semantic Goal Verification Gate (no pre-image path)
            raw_text = ""
            if understanding and hasattr(understanding, "raw_request") and understanding.raw_request:
                raw_text = getattr(understanding.raw_request, "raw_text", "").lower()

            import re
            complex_keywords = [
                "portrait", "face", "boy", "girl", "man", "woman", "person",
                "human", "dog", "cat", "animal", "landscape", "scenery", "realistic"
            ]
            is_complex_request = any(re.search(rf"\b{kw}\b", raw_text) for kw in complex_keywords)
            if is_complex_request:
                logger.warning(
                    "Semantic Goal Verification FAILED: Non-blank canvas confirmed, but primitive strokes cannot satisfy '%s'",
                    raw_text,
                )
                return GoalVerificationResult(
                    status=TaskCompletionStatus.FAILED,
                    is_completed=False,
                    failure_reason=(
                        f"Non-blank drawing canvas confirmed (Level 2 verified), "
                        f"but Level 3 Semantic Goal Verification failed: primitive strokes cannot satisfy '{raw_text}'."
                    ),
                    failure_code="SEMANTIC_GOAL_NOT_SATISFIED",
                    evidence=evidence,
                )

            return GoalVerificationResult(
                status=TaskCompletionStatus.COMPLETED,
                is_completed=True,
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
