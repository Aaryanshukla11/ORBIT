"""Cognitive Decision Engine evaluating State / Goal Delta and Layered Decision Hierarchy."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from orbit.runtime.agent.contracts import VerificationStrategy
from orbit.runtime.cognitive.models import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    SemanticTarget,
    StructuredObjective,
)
from orbit.runtime.models.models import ModelGenerateRequest

logger = logging.getLogger(__name__)

DECISION_SYSTEM_PROMPT = """You are the ORBIT Cognitive Decision Engine.
Given the User Goal, the Structured Objective, the Current Screen/Window State, and the Action History, determine what should happen NEXT.

SAFETY INVARIANT:
Do NOT produce physical screen coordinates (x, y). Use logical target names, roles, and contexts only.

Output ONLY a single valid JSON object with the following schema:
{
  "is_goal_satisfied": <true/false>,
  "decision_summary": "<concise state assessment vs objective>",
  "decision_confidence": <float between 0.0 and 1.0>,
  "evidence_used": ["<concrete observations referenced>"],
  "expected_state_transition": "<what state delta should happen after action>",
  "reason_summary": "<why this action is selected>",
  "next_action": {
     "action_type": "<LAUNCH_APPLICATION | FOCUS_WINDOW | CLICK | TYPE_TEXT | DRAW_STROKES | SEND_HOTKEY | WAIT_SETTLE | COMPLETE_GOAL | ABORT_TASK>",
     "target": {
        "name": "<logical label, text, or title>",
        "role": "<edit | button | canvas | window | etc>",
        "context": "<app or window name>"
     },
     "parameters": { ... },
     "expected_effect": "<what state transition is expected>"
  }
}
If the goal is already fully satisfied according to the observation, set "is_goal_satisfied": true and "action_type": "COMPLETE_GOAL".
Do not include markdown code blocks. Output plain JSON.
"""


class StateGoalDelta:
    """Computed semantic difference between StructuredObjective and CurrentStateObservation."""

    def __init__(
        self,
        app_running: bool,
        app_focused: bool,
        content_present: bool,
        goal_satisfied: bool,
        target_app: str,
        missing_aspects: List[str],
    ) -> None:
        self.app_running = app_running
        self.app_focused = app_focused
        self.content_present = content_present
        self.goal_satisfied = goal_satisfied
        self.target_app = target_app
        self.missing_aspects = missing_aspects


class CognitiveDecisionEngine:
    """Computes state/goal delta and applies layered decision hierarchy (Fast Rules -> Recovery -> LLM Escalation)."""

    def __init__(
        self,
        model_session_manager: Optional[Any] = None,
    ) -> None:
        self._model_session_manager = model_session_manager

    def set_model_session_manager(self, msm: Any) -> None:
        self._model_session_manager = msm

    @property
    def model_session_manager(self) -> Optional[Any]:
        return self._model_session_manager

    async def decide_next_step(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        step_history: Optional[List[CognitiveStepResult]] = None,
        step_index: int = 0,
    ) -> CognitiveDecision:
        """Determine what should happen next using Layered Decision Hierarchy."""
        history = step_history or []
        delta = self._compute_delta(objective, observation, history)

        # -------------------------------------------------------------
        # Level 1 & 2: Deterministic Fast-Path & Recovery (0ms LLM Latency)
        # -------------------------------------------------------------
        deterministic_decision = self._decide_deterministic(objective, observation, delta, history, step_index)
        if deterministic_decision is not None:
            return deterministic_decision

        # -------------------------------------------------------------
        # Level 3: Cognitive LLM Escalation (Only when state unexpected / ambiguous)
        # -------------------------------------------------------------
        if self._model_session_manager is not None:
            try:
                active_ctx = (
                    self._model_session_manager.get_active_context()
                    if hasattr(self._model_session_manager, "get_active_context")
                    else None
                )
                if active_ctx:
                    logger.info("Escalating decision to active LLM model (%s)", active_ctx.model_id)
                    from orbit.runtime.cognitive.output_parser import StructuredDecisionParser
                    from orbit.runtime.cognitive.context_builder import AgentReasoningContextBuilder, DECISION_SYSTEM_PROMPT

                    prompt_text = AgentReasoningContextBuilder.build_prompt_text(
                        objective=objective,
                        observation=observation,
                        step_history=history,
                        step_index=step_index,
                    )
                    gen_req = ModelGenerateRequest(
                        prompt=prompt_text,
                        system_prompt=DECISION_SYSTEM_PROMPT,
                        temperature=0.0,
                    )
                    resp = await self._model_session_manager.generate(gen_req)
                    content = resp.content.strip()
                    return StructuredDecisionParser.parse_decision(
                        raw_text=content,
                        step_index=step_index,
                        model_id=active_ctx.model_id,
                        latency_ms=resp.total_duration_ms,
                    )
            except Exception as ex:
                logger.warning("LLM Cognitive Decision escalation error: %s", ex)

        # Fallback to conservative default decision
        return CognitiveDecision(
            step_index=step_index,
            decision_summary="Fallback: settling desktop state",
            decision_confidence=0.5,
            evidence_used=[observation.screen_summary],
            expected_state_transition="desktop_settled",
            reason_summary="Ensuring desktop has settled before further action.",
            is_goal_satisfied=False,
            escalated_to_llm=False,
            next_action=AbstractAction(
                action_type=AbstractActionType.WAIT_SETTLE,
                parameters={"duration_ms": 500},
                outcome_contract=ActionOutcomeContract(expected_state_transition="desktop_settled"),
                expected_effect="Desktop settled",
                rationale="Settling desktop before retry.",
            ),
        )

    def _compute_delta(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        history: List[CognitiveStepResult],
    ) -> StateGoalDelta:
        """Compute the semantic delta between current state and end condition."""
        target_app = str(objective.parameters.get("app_name", "")).strip()
        if not target_app and objective.target_entities:
            target_app = objective.target_entities[0].strip()

        app_running = observation.target_app_exists
        app_focused = observation.target_app_is_active
        missing: List[str] = []

        if target_app and not app_running:
            missing.append(f"app_not_running:{target_app}")
        elif target_app and not app_focused:
            missing.append(f"app_not_focused:{target_app}")

        # Check content presence
        action_type = str(objective.parameters.get("action_type", "")).lower()
        content_present = False

        if action_type == "draw":
            # Check if drawing strokes succeeded and canvas was modified
            has_drawn = any(
                step.action_dispatched
                and step.action_dispatched.action_type == AbstractActionType.DRAW_STROKES
                and step.outcome_verified
                for step in history
            )
            content_present = has_drawn
            if not content_present and app_focused:
                missing.append("strokes_not_drawn")

        elif action_type == "type":
            text_payload = str(objective.parameters.get("text", "")).lower()
            # Check if text was typed in history
            has_typed = any(
                step.action_dispatched
                and step.action_dispatched.action_type == AbstractActionType.TYPE_TEXT
                and step.outcome_verified
                for step in history
            )
            content_present = has_typed
            if not content_present and app_focused:
                missing.append("text_not_entered")

        elif action_type == "save":
            has_saved = any(
                step.action_dispatched
                and step.action_dispatched.action_type == AbstractActionType.SAVE_FILE
                and step.outcome_verified
                for step in history
            )
            content_present = has_saved
            if not content_present:
                missing.append("file_not_saved")

        # Check downstream save requirement if composite goal
        requires_save = bool(objective.parameters.get("requires_save")) or bool(objective.parameters.get("filename")) or ("save" in objective.raw_prompt.lower() and not action_type in ("open", "launch"))
        if requires_save and action_type != "save":
            has_saved = any(
                step.action_dispatched
                and step.action_dispatched.action_type == AbstractActionType.SAVE_FILE
                and step.outcome_verified
                for step in history
            )
            if not has_saved:
                missing.append("file_not_saved")

        goal_satisfied = (len(missing) == 0 and (content_present or action_type in ("open", "launch", "")))

        return StateGoalDelta(
            app_running=app_running,
            app_focused=app_focused,
            content_present=content_present,
            goal_satisfied=goal_satisfied,
            target_app=target_app,
            missing_aspects=missing,
        )

    def _decide_deterministic(
        self,
        objective: StructuredObjective,
        observation: CurrentStateObservation,
        delta: StateGoalDelta,
        history: List[CognitiveStepResult],
        step_index: int,
    ) -> Optional[CognitiveDecision]:
        """Level 1 & 2 Deterministic Decision Logic."""
        target_app = delta.target_app or "application"
        action_type = str(objective.parameters.get("action_type", "")).lower()

        # Check for recovery scenario: Was previous action unverified?
        if history:
            last_step = history[-1]
            if last_step.action_dispatched and not last_step.outcome_verified:
                # Level 2 Deterministic Recovery
                last_act = last_step.action_dispatched.action_type
                if last_act == AbstractActionType.FOCUS_WINDOW:
                    # Focus failed -> Retry with window title or list_windows
                    return CognitiveDecision(
                        step_index=step_index,
                        decision_summary=f"Focus verification failed for '{target_app}'. Retrying window focus recovery.",
                        decision_confidence=0.85,
                        evidence_used=[f"previous_unverified:{last_act.value}"],
                        expected_state_transition=f"{target_app}_window_focused",
                        reason_summary=f"Recovering focus for {target_app}.",
                        is_goal_satisfied=False,
                        escalated_to_llm=False,
                        next_action=AbstractAction(
                            action_type=AbstractActionType.FOCUS_WINDOW,
                            target=SemanticTarget(name=target_app, role="window", context=target_app),
                            parameters={"app_name": target_app, "recovery": True},
                            outcome_contract=ActionOutcomeContract(
                                expected_state_transition=f"{target_app}_focused",
                                verification_strategy="WINDOW_FOCUS_OR_STATE",
                                target_name=target_app,
                            ),
                            expected_effect=f"{target_app} focused in foreground",
                            rationale="Recovery attempt to restore application focus.",
                        ),
                    )

        # Rule 1: Goal Already Satisfied
        if delta.goal_satisfied:
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"Objective '{objective.user_goal}' is fully satisfied and verified.",
                decision_confidence=1.0,
                evidence_used=[f"active_window:{observation.active_window_title}", f"canvas_status:{observation.canvas_status}"],
                expected_state_transition="task_completed",
                reason_summary="All required state criteria and outcome contracts satisfied.",
                is_goal_satisfied=True,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.COMPLETE_GOAL,
                    outcome_contract=ActionOutcomeContract(expected_state_transition="task_completed"),
                    expected_effect="Goal marked complete",
                    rationale="End condition fulfilled.",
                ),
            )

        # Rule 2: App Not Running -> Launch Application
        if not delta.app_running:
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"Target application '{target_app}' is not running on desktop. Must launch it first.",
                decision_confidence=0.95,
                evidence_used=["target_app_exists:false"],
                expected_state_transition=f"{target_app}_process_running",
                reason_summary=f"Application {target_app} must be open to perform operations.",
                is_goal_satisfied=False,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.LAUNCH_APPLICATION,
                    target=SemanticTarget(name=target_app, role="application", context="desktop"),
                    parameters={"app_name": target_app},
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition=f"{target_app}_running",
                        verification_strategy="WINDOW_FOCUS_OR_STATE",
                        target_name=target_app,
                    ),
                    expected_effect=f"{target_app} launched and visible on desktop",
                    rationale="Starting target application process.",
                ),
            )

        # Rule 3: App Running but Not Focused -> Focus Window
        if not delta.app_focused:
            target_hwnd = None
            t_low = target_app.lower()
            # Generic window matching against title, process name, and class name
            for win in observation.visible_windows:
                w_title = (win.get("title") or "").lower()
                w_cls = (win.get("class_name") or "").lower()
                w_proc = (win.get("process_name") or "").lower()
                if t_low in w_title or t_low in w_cls or t_low in w_proc:
                    target_hwnd = win.get("hwnd")
                    break

            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"'{target_app}' is running but active foreground is '{observation.active_window_title}'. Must focus {target_app}.",
                decision_confidence=0.95,
                evidence_used=[f"active_window:{observation.active_window_title}", "target_app_is_active:false"],
                expected_state_transition=f"{target_app}_window_focused",
                reason_summary=f"Focus {target_app} to accept user input.",
                is_goal_satisfied=False,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.FOCUS_WINDOW,
                    target=SemanticTarget(name=target_app, role="window", context=target_app),
                    parameters={"app_name": target_app, "hwnd": target_hwnd or observation.active_window_hwnd},
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition=f"{target_app}_focused",
                        verification_strategy="WINDOW_FOCUS_OR_STATE",
                        target_name=target_app,
                    ),
                    expected_effect=f"{target_app} focused as active foreground window",
                    rationale="Bringing application to front.",
                ),
            )

        # Rule 4: App Active & Drawing Intent -> Check Capability Feasibility
        if action_type == "draw" and not delta.content_present:
            shape_param = str(objective.parameters.get("shape", "")).lower()
            raw_prompt_lower = objective.raw_prompt.lower()
            is_unsupported_complex_drawing = any(
                term in shape_param or term in raw_prompt_lower
                for term in ("portrait", "boy", "face", "landscape", "complex", "photorealistic")
            )
            if is_unsupported_complex_drawing:
                explanation = f"Goal '{objective.user_goal}' requires complex drawing capabilities not supported by primitive stroke engine"
                return CognitiveDecision(
                    step_index=step_index,
                    decision_summary=f"Drawing goal unachievable: {explanation}",
                    decision_confidence=1.0,
                    evidence_used=["triggered_limitations:1"],
                    expected_state_transition="task_aborted_unsupported",
                    reason_summary=explanation,
                    is_goal_satisfied=False,
                    escalated_to_llm=False,
                    next_action=AbstractAction(
                        action_type=AbstractActionType.ABORT_TASK,
                        outcome_contract=ActionOutcomeContract(expected_state_transition="task_aborted"),
                        expected_effect="Halt execution: goal not feasibly executable with available capabilities",
                        rationale=explanation,
                    ),
                )

            shape = str(objective.parameters.get("shape", "geometric_shape"))
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"'{target_app}' is active and ready. Executing physical drawing strokes for shape '{shape}'.",
                decision_confidence=0.95,
                evidence_used=["target_app_is_active:true", f"canvas_status:{observation.canvas_status}"],
                expected_state_transition=f"canvas_modified_with_{shape}",
                reason_summary=f"Drawing {shape} on active canvas.",
                is_goal_satisfied=False,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.DRAW_STROKES,
                    target=SemanticTarget(name="canvas", role="canvas", context=target_app),
                    parameters={"shape": shape, "app_name": target_app},
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition=f"canvas_has_{shape}_drawing",
                        verification_strategy="PIXEL_DIFF",
                        target_role="canvas",
                    ),
                    expected_effect=f"Physical strokes for {shape} drawn on canvas",
                    rationale=f"Executing geometric trajectory for {shape} on canvas.",
                ),
            )

        # Rule 5: App Active & Typing Intent -> Type Text
        if action_type == "type" and not delta.content_present:
            text_payload = str(objective.parameters.get("text", "Hello World"))
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"'{target_app}' is active in foreground. Typing text: '{text_payload}'.",
                decision_confidence=0.95,
                evidence_used=["target_app_is_active:true"],
                expected_state_transition=f"text_buffer_contains_{text_payload[:10]}",
                reason_summary=f"Typing text into {target_app}.",
                is_goal_satisfied=False,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.TYPE_TEXT,
                    target=SemanticTarget(name="editor", role="edit", context=target_app),
                    parameters={"text": text_payload, "app_name": target_app},
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition=f"editor_contains_{text_payload[:10]}",
                        verification_strategy="UIA_STATE",
                        target_role="edit",
                    ),
                    expected_effect=f"Text '{text_payload}' typed into editor",
                    rationale="Inputting string into document buffer.",
                ),
            )

        # Rule 5b: App Active & Save Intent Pending -> Save File
        requires_save = bool(objective.parameters.get("requires_save")) or bool(objective.parameters.get("filename")) or (action_type == "save") or ("save" in objective.raw_prompt.lower() and not action_type in ("open", "launch"))
        has_saved = any(
            step.action_dispatched
            and step.action_dispatched.action_type == AbstractActionType.SAVE_FILE
            and step.outcome_verified
            for step in history
        )
        if requires_save and not has_saved and (delta.content_present or action_type in ("save", "")):
            filename = str(objective.parameters.get("filename", "")).strip()
            if not filename and objective.parameters.get("file_path"):
                import os
                filename = os.path.basename(str(objective.parameters["file_path"]))
            target_dir = str(objective.parameters.get("target_dir", "desktop"))
            fmt = str(objective.parameters.get("format", filename.rsplit(".", 1)[-1] if "." in filename else ""))
            target_label = filename or "current_artifact"
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"'{target_app}' is active and content prepared. Executing file save as '{target_label}' on {target_dir}.",
                decision_confidence=0.95,
                evidence_used=["target_app_is_active:true", f"content_present:{delta.content_present}"],
                expected_state_transition=f"file_{target_label}_saved",
                reason_summary=f"Saving artifact {target_label} to {target_dir}.",
                is_goal_satisfied=False,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.SAVE_FILE,
                    target=SemanticTarget(name=target_label, role="file", context=target_dir),
                    parameters={
                        "filename": filename,
                        "target_dir": target_dir,
                        "format": fmt,
                        "app_name": target_app,
                    },
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition=f"File {target_label} saved on {target_dir}",
                        verification_strategy=VerificationStrategy.ARTIFACT_CREATED,
                        target_name=target_label,
                    ),
                    expected_effect=f"File {target_label} saved to {target_dir}",
                    rationale=f"Persisting artifact {target_label} to disk.",
                ),
            )

        # Rule 6: Launch-Only Goal Complete
        if action_type in ("open", "launch", "") and delta.app_focused and not requires_save:
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"Application '{target_app}' is running and focused in foreground.",
                decision_confidence=1.0,
                evidence_used=["target_app_is_active:true"],
                expected_state_transition="task_completed",
                reason_summary=f"{target_app} successfully launched and focused.",
                is_goal_satisfied=True,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.COMPLETE_GOAL,
                    outcome_contract=ActionOutcomeContract(expected_state_transition="task_completed"),
                    expected_effect="Goal complete",
                    rationale="Requested application is open and active.",
                ),
            )

        # If none of the deterministic fast rules apply, escalate to Level 3 LLM
        return None


class OrbitDecisionEngine:
    """Canonical Authoritative Model-First Decision Engine (Phase 2E).

    Guarantees:
    1. Single Authoritative Decision Path: Multimodal model decides WHAT next action to take.
    2. Zero Hidden Heuristic Authority: Never silently falls back to deterministic rule engines.
    3. Fail-Closed on Model Absence: Returns explicit MODEL_UNAVAILABLE diagnostics if no model is present.
    4. Deterministic Gating: ModelActionProposal passes strict 4-stage validation (Schema, Capability, Safety, Grounding).
    5. Integrated 4-Pass Grounding: Binds targets to GroundingCandidate with observation freshness validation.
    """

    def __init__(
        self,
        model_session_manager: Optional[Any] = None,
        model_client: Optional[Any] = None,
        proposal_validator: Optional[Any] = None,
        grounder: Optional[Any] = None,
        prompt_builder: Optional[Any] = None,
    ) -> None:
        self._model_session_manager = model_session_manager
        self._model_client = model_client

        from orbit.runtime.cognitive.primitive_validator import ModelProposalValidator
        from orbit.runtime.cognitive.prompt_builder import MultimodalPromptBuilder
        from orbit.runtime.targeting.grounding import MultiPassGrounder

        self._proposal_validator = proposal_validator or ModelProposalValidator()
        self._grounder = grounder or MultiPassGrounder()
        self._prompt_builder = prompt_builder or MultimodalPromptBuilder()

    def set_model_session_manager(self, msm: Any) -> None:
        self._model_session_manager = msm

    @property
    def model_session_manager(self) -> Optional[Any]:
        return self._model_session_manager

    @property
    def proposal_validator(self) -> Any:
        return self._proposal_validator

    @property
    def grounder(self) -> Any:
        return self._grounder

    async def decide_next_step(
        self,
        objective: Any,
        observation: CurrentStateObservation,
        step_history: Optional[List[Any]] = None,
        step_index: int = 0,
        task_requirements: Optional[List[str]] = None,
        failure_feedback: Optional[str] = None,
        user_goal: Optional[str] = None,
    ) -> CognitiveDecision:
        """Evaluate current observation through the authoritative multimodal model and deterministic validation."""
        history = step_history or []
        obs_id = getattr(observation, "observation_id", f"obs_{step_index}")

        # 1. Resolve Goal Text
        goal_text = user_goal or (getattr(objective, "user_goal", str(objective)) if objective else "Execute user task")

        # 2. Extract active model context / client
        active_ctx = None
        if self._model_session_manager is not None:
            if hasattr(self._model_session_manager, "get_active_context"):
                active_ctx = self._model_session_manager.get_active_context()

        if active_ctx is None and self._model_client is None:
            # FAIL-CLOSED: No silent heuristic fallback is permitted
            logger.warning("[OrbitDecisionEngine] Model unavailable and no active session configured.")
            return CognitiveDecision(
                step_index=step_index,
                decision_summary="MODEL_UNAVAILABLE: No authoritative multimodal model session or client available.",
                decision_confidence=0.0,
                evidence_used=["model_session_manager:none"],
                expected_state_transition="none",
                reason_summary="Authoritative model is unavailable and silent heuristic fallback is prohibited.",
                is_goal_satisfied=False,
                escalated_to_llm=False,
                next_action=AbstractAction(
                    action_type=AbstractActionType.ABORT_TASK,
                    parameters={
                        "error_code": "MODEL_UNAVAILABLE",
                        "diagnostic": "No active multimodal decision model configured.",
                    },
                    expected_effect="Abort task due to missing decision model",
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition="task_aborted",
                        verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    ),
                ),
            )

        # 3. Build Token-Efficient Multimodal Prompt
        action_history_summary = []
        for h in history[-5:]:
            act_d = getattr(h, "action_dispatched", None)
            verif = getattr(h, "outcome_verified", False)
            diag = getattr(h, "failure_diagnosis", "")
            action_history_summary.append({
                "action": {
                    "action_type": getattr(act_d, "action_type", AbstractActionType.WAIT_SETTLE).value if act_d else "UNKNOWN",
                    "parameters": getattr(act_d, "parameters", {}) if act_d else {},
                },
                "verified": verif,
                "reason": diag,
            })

        prompt_payload = self._prompt_builder.build_prompt(
            user_goal=goal_text,
            current_observation=observation,
            task_requirements=task_requirements,
            action_history=action_history_summary,
            failure_feedback=failure_feedback,
        )

        # 4. Invoke Authoritative Model
        raw_response_text = ""
        try:
            if self._model_client is not None:
                if callable(self._model_client):
                    res = self._model_client(prompt_payload)
                    raw_response_text = await res if hasattr(res, "__await__") else res
                elif hasattr(self._model_client, "generate_response"):
                    res = self._model_client.generate_response(prompt_payload)
                    raw_response_text = await res if hasattr(res, "__await__") else res
            elif self._model_session_manager is not None:
                gen_req = ModelGenerateRequest(
                    prompt=prompt_payload.get("user_prompt", ""),
                    system_prompt=prompt_payload.get("system_prompt", ""),
                    temperature=0.1,
                    max_tokens=1024,
                )
                resp_obj = await self._model_session_manager.generate(gen_req)
                raw_response_text = getattr(resp_obj, "content", getattr(resp_obj, "text", str(resp_obj)))
        except Exception as model_err:
            logger.error("[OrbitDecisionEngine] Model generation call failed: %s", model_err)
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"MODEL_CALL_FAILED: {model_err}",
                decision_confidence=0.0,
                evidence_used=[f"exception:{model_err}"],
                expected_state_transition="none",
                reason_summary=f"Model call exception: {model_err}",
                is_goal_satisfied=False,
                escalated_to_llm=True,
                next_action=AbstractAction(
                    action_type=AbstractActionType.ABORT_TASK,
                    parameters={"error": str(model_err)},
                    expected_effect="Abort due to model call exception",
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition="task_aborted",
                        verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    ),
                ),
            )

        # 5. Parse Declarative ModelActionProposal
        proposal = self._parse_model_proposal(raw_response_text)
        if proposal is None:
            logger.warning("[OrbitDecisionEngine] Failed to parse ModelActionProposal from model response: %s", raw_response_text)
            return CognitiveDecision(
                step_index=step_index,
                decision_summary="INVALID_PROPOSAL_SCHEMA: Failed to parse JSON ModelActionProposal from model output.",
                decision_confidence=0.0,
                evidence_used=[f"raw_output:{raw_response_text[:100]}"],
                expected_state_transition="none",
                reason_summary="Model produced unparsable or malformed output.",
                is_goal_satisfied=False,
                escalated_to_llm=True,
                next_action=AbstractAction(
                    action_type=AbstractActionType.WAIT_SETTLE,
                    parameters={"reason": "replan_after_schema_error", "raw_output": raw_response_text[:200]},
                    expected_effect="Retry planning with diagnostic feedback",
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition="replan_retry",
                        verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    ),
                ),
            )

        # 6. Stage 1-4 Deterministic Validation Gate
        val_result = self._proposal_validator.validate_proposal(
            proposal=proposal,
            current_observation_id=obs_id,
        )

        if not val_result.is_valid:
            logger.warning(
                "[OrbitDecisionEngine] Proposal REJECTED at [%s]: %s",
                val_result.failed_stage.value if val_result.failed_stage else "UNKNOWN",
                val_result.failure_reason,
            )
            # Return non-physical diagnostic action for model retry
            return CognitiveDecision(
                step_index=step_index,
                decision_summary=f"PROPOSAL_REJECTED: [{val_result.failed_stage.value if val_result.failed_stage else 'UNKNOWN'}] {val_result.failure_reason}",
                decision_confidence=0.0,
                evidence_used=[f"validation_failure:{val_result.failure_reason}"],
                expected_state_transition="none",
                reason_summary=val_result.diagnostic_feedback or val_result.failure_reason or "Proposal validation failed.",
                is_goal_satisfied=False,
                escalated_to_llm=True,
                next_action=AbstractAction(
                    action_type=AbstractActionType.WAIT_SETTLE,
                    parameters={
                        "reason": "validation_failure_retry",
                        "diagnostic_feedback": val_result.diagnostic_feedback,
                        "failed_stage": val_result.failed_stage.value if val_result.failed_stage else "UNKNOWN",
                    },
                    expected_effect="Retry proposal with validation diagnostic",
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition="validation_retry",
                        verification_strategy=VerificationStrategy.AUTO_ROUTED,
                    ),
                ),
            )

        # 7. Grounding Resolution & Observation Freshness Check
        grounded_candidate = None
        if proposal.target_selector:
            tgt_name = proposal.target_selector.name or ""
            tgt_role = proposal.target_selector.role or None
            ws = getattr(observation, "world_state", None)
            if ws is not None:
                ground_res = self._grounder.ground_target(
                    target_name=tgt_name,
                    target_role=tgt_role,
                    world_state=ws,
                    candidate_bounds=proposal.target_selector.bounds,
                )
                if ground_res.is_grounded:
                    grounded_candidate = ground_res.candidate
                    logger.debug("[OrbitDecisionEngine] Grounded target '%s' via %s", tgt_name, ground_res.candidate.source.value)

        # 8. Assemble Canonical AbstractAction
        canonical_action = self._translate_proposal_to_abstract_action(
            proposal=proposal,
            grounded_candidate=grounded_candidate,
            goal_text=goal_text,
        )

        is_complete = (proposal.action_type.value == "COMPLETE")
        is_fail = (proposal.action_type.value == "FAIL")

        return CognitiveDecision(
            step_index=step_index,
            decision_summary=proposal.diagnostic_reasoning or f"Model selected {proposal.action_type.value} -> {canonical_action.expected_effect}",
            decision_confidence=float(proposal.confidence or 1.0),
            evidence_used=[f"observation_id:{obs_id}", f"action_type:{proposal.action_type.value}"],
            expected_state_transition=proposal.expected_outcome,
            reason_summary=proposal.diagnostic_reasoning or f"Model-driven {proposal.action_type.value}",
            is_goal_satisfied=is_complete,
            escalated_to_llm=True,
            next_action=canonical_action,
        )

    decide_next_action = decide_next_step

    def _parse_model_proposal(self, text: str) -> Optional[Any]:
        """Extract and parse ModelActionProposal JSON from model response text."""
        from orbit.runtime.cognitive.model_proposal import ModelActionProposal

        if not text or not text.strip():
            return None

        # Clean markdown code fences if present
        clean_text = text.strip()
        if "```json" in clean_text:
            match = re.search(r"```json\s*(.*?)\s*```", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1).strip()
        elif "```" in clean_text:
            match = re.search(r"```\s*(.*?)\s*```", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1).strip()

        try:
            data = json.loads(clean_text)
            if isinstance(data, dict):
                return ModelActionProposal.model_validate(data)
        except Exception as e:
            # Fallback: scan for first JSON object
            try:
                brace_match = re.search(r"\{.*\}", clean_text, re.DOTALL)
                if brace_match:
                    data = json.loads(brace_match.group(0))
                    return ModelActionProposal.model_validate(data)
            except Exception:
                pass
            logger.debug("[OrbitDecisionEngine] JSON parse error: %s", e)

        return None

    def _translate_proposal_to_abstract_action(
        self,
        proposal: Any,
        grounded_candidate: Optional[Any],
        goal_text: str,
    ) -> AbstractAction:
        """Convert validated ModelActionProposal into canonical AbstractAction for execution controller."""
        from orbit.runtime.cognitive.model_proposal import ModelActionType

        act_type_map = {
            ModelActionType.CLICK: AbstractActionType.CLICK,
            ModelActionType.DOUBLE_CLICK: AbstractActionType.DOUBLE_CLICK,
            ModelActionType.RIGHT_CLICK: AbstractActionType.RIGHT_CLICK,
            ModelActionType.TYPE: AbstractActionType.TYPE_TEXT,
            ModelActionType.HOTKEY: AbstractActionType.SEND_HOTKEY,
            ModelActionType.LAUNCH: AbstractActionType.LAUNCH_APPLICATION,
            ModelActionType.SAVE_FILE: AbstractActionType.SAVE_FILE,
            ModelActionType.WAIT: AbstractActionType.WAIT_SETTLE,
            ModelActionType.SCROLL: AbstractActionType.SCROLL,
            ModelActionType.DRAG: AbstractActionType.DRAG,
            ModelActionType.DRAW: AbstractActionType.DRAW_STROKES,
            ModelActionType.COMPLETE: AbstractActionType.COMPLETE_GOAL,
            ModelActionType.FAIL: AbstractActionType.ABORT_TASK,
        }

        canonical_type = act_type_map.get(proposal.action_type, AbstractActionType.WAIT_SETTLE)

        # Semantic target
        target = None
        if proposal.target_selector:
            ts = proposal.target_selector
            target = SemanticTarget(
                name=ts.name or "",
                role=ts.role or "control",
                context=ts.selector or "",
            )
        elif proposal.parameters.get("application_name"):
            app_name = proposal.parameters.get("application_name")
            target = SemanticTarget(name=app_name, role="application", context="desktop")

        # Outcome contract
        strategy = VerificationStrategy.ELEMENT_VISIBLE
        if canonical_type == AbstractActionType.SAVE_FILE:
            strategy = VerificationStrategy.ARTIFACT_CREATED
        elif canonical_type in (AbstractActionType.LAUNCH_APPLICATION, AbstractActionType.FOCUS_WINDOW):
            strategy = VerificationStrategy.WINDOW_FOCUS
        else:
            strategy = VerificationStrategy.AUTO_ROUTED

        outcome_contract = ActionOutcomeContract(
            expected_state_transition=proposal.expected_outcome,
            verification_strategy=strategy,
            target_name=target.name if target else None,
        )

        params = dict(proposal.parameters)
        if grounded_candidate and grounded_candidate.bounds:
            params["target_bounds"] = grounded_candidate.bounds
            if canonical_type == AbstractActionType.DRAW_STROKES and "canvas_rect" not in params:
                params["canvas_rect"] = grounded_candidate.bounds

        return AbstractAction(
            action_type=canonical_type,
            target=target,
            parameters=params,
            outcome_contract=outcome_contract,
            expected_effect=proposal.expected_outcome,
            rationale=proposal.diagnostic_reasoning or f"Model proposed {canonical_type.value}",
        )

