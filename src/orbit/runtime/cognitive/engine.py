"""Cognitive Decision Engine evaluating State / Goal Delta and Layered Decision Hierarchy."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

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
     "action_type": "<LAUNCH_APPLICATION | FOCUS_WINDOW | CLICK_ELEMENT | TYPE_TEXT | DRAW_STROKES | SEND_HOTKEY | WAIT_SETTLE | COMPLETE_GOAL | ABORT_UNACHIEVABLE>",
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

    def __init__(self, model_session_manager: Optional[Any] = None) -> None:
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
                    prompt_payload = {
                        "objective": objective.model_dump(mode="json"),
                        "observation": {
                            "active_window_title": observation.active_window_title,
                            "active_window_class": observation.active_window_class,
                            "target_app_exists": observation.target_app_exists,
                            "target_app_is_active": observation.target_app_is_active,
                            "canvas_status": observation.canvas_status,
                            "screen_summary": observation.screen_summary,
                            "ocr_tokens": observation.ocr_tokens[:20],
                        },
                        "missing_aspects": delta.missing_aspects,
                        "step_index": step_index,
                        "history_count": len(history),
                    }
                    gen_req = ModelGenerateRequest(
                        prompt=f"Cognitive State:\n{json.dumps(prompt_payload, indent=2)}",
                        system_prompt=DECISION_SYSTEM_PROMPT,
                        temperature=0.0,
                    )
                    resp = await self._model_session_manager.generate(gen_req)
                    content = resp.content.strip()
                    if content.startswith("```"):
                        content = re.sub(r"^```(?:json)?\s*", "", content)
                        content = re.sub(r"\s*```$", "", content)
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "decision_summary" in parsed:
                        is_sat = bool(parsed.get("is_goal_satisfied", False))
                        act_data = parsed.get("next_action")
                        action_obj = None
                        if act_data and isinstance(act_data, dict):
                            act_type_str = act_data.get("action_type", "COMPLETE_GOAL")
                            try:
                                act_type = AbstractActionType(act_type_str)
                            except Exception:
                                act_type = AbstractActionType.COMPLETE_GOAL

                            target_data = act_data.get("target") or {}
                            sem_target = None
                            if target_data and isinstance(target_data, dict):
                                sem_target = SemanticTarget(
                                    name=target_data.get("name"),
                                    role=target_data.get("role"),
                                    context=target_data.get("context"),
                                )

                            # Clean parameters: ensure no physical coordinates leaked
                            raw_params = act_data.get("parameters", {})
                            clean_params = {k: v for k, v in raw_params.items() if k.lower() not in {"x", "y", "screen_x", "screen_y"}}

                            exp_trans = str(parsed.get("expected_state_transition", act_data.get("expected_effect", "")))

                            action_obj = AbstractAction(
                                action_type=act_type,
                                target=sem_target,
                                parameters=clean_params,
                                outcome_contract=ActionOutcomeContract(
                                    expected_state_transition=exp_trans or "state_progress",
                                    target_role=sem_target.role if sem_target else None,
                                    target_name=sem_target.name if sem_target else None,
                                ),
                                expected_effect=exp_trans,
                                rationale=str(parsed.get("reason_summary", "")),
                            )
                        return CognitiveDecision(
                            step_index=step_index,
                            decision_summary=str(parsed.get("decision_summary", "LLM decision")),
                            decision_confidence=float(parsed.get("decision_confidence", 0.9)),
                            evidence_used=list(parsed.get("evidence_used", [observation.screen_summary])),
                            expected_state_transition=str(parsed.get("expected_state_transition", "")),
                            reason_summary=str(parsed.get("reason_summary", "")),
                            is_goal_satisfied=is_sat,
                            escalated_to_llm=True,
                            next_action=action_obj,
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
                    parameters={"app_name": target_app, "hwnd": observation.active_window_hwnd},
                    outcome_contract=ActionOutcomeContract(
                        expected_state_transition=f"{target_app}_focused",
                        verification_strategy="WINDOW_FOCUS_OR_STATE",
                        target_name=target_app,
                    ),
                    expected_effect=f"{target_app} focused as active foreground window",
                    rationale="Bringing application to front.",
                ),
            )

        # Rule 4: App Active & Drawing Intent -> Draw Strokes
        if action_type == "draw" and not delta.content_present:
            shape = str(objective.parameters.get("shape", "cube"))
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

        # Rule 6: Launch-Only Goal Complete
        if action_type in ("open", "launch", "") and delta.app_focused:
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
