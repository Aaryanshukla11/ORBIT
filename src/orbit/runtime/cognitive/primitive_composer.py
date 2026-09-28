"""Primitive Composer generating canonical primitive action sequences.

Guardrail 1: Single Execution Path
Guardrail 2: No Hardcoded Task-Specific Logic (Zero if paint/if laptop/DRAW_HOUSE shortcuts)
Guardrail 3: Canonical Primitives Only
Guardrail 4: LLM Does Not Control Physical Coordinates
Guardrail 9: Failure Analyst Only Diagnoses (Composer consumes FailureReport to re-compose)
Guardrail 11: Bounded Context
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.context_builder import StructuredAgentContext
from orbit.runtime.cognitive.models import (
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.primitive_validator import PrimitiveValidator
from orbit.runtime.models.models import ModelGenerateRequest

logger = logging.getLogger(__name__)


COMPOSER_SYSTEM_PROMPT = """You are the ORBIT Primitive Composer.
Your job is to translate a high-level goal or sub-objective into a minimal, logical sequence of CANONICAL PRIMITIVE ACTIONS.

CANONICAL VOCABULARY:
- Physical Computer: LAUNCH_APPLICATION, FOCUS_WINDOW, CLICK, DOUBLE_CLICK, RIGHT_CLICK, TYPE_TEXT, SEND_HOTKEY, SCROLL, DRAG, DRAW_STROKES, SELECT_OPTION, WAIT, WAIT_SETTLE
- Observation: SCREENSHOT, READ_UI_ELEMENT, READ_OCR_TEXT
- Environment Interfaces: FILE_READ, FILE_WRITE, BROWSER_NAVIGATE, SPREADSHEET_READ, SPREADSHEET_WRITE
- Control Signals: COMPLETE_GOAL, ABORT_TASK

CRITICAL SAFETY INVARIANTS:
1. Physical screen coordinates (x, y) MUST NEVER be output. Use SemanticTarget (name, role, context, anchor, text_hint).
2. Every interactive action MUST specify an "outcome_contract" declaring the expected observable state transition.
3. Use ONLY canonical action names listed above. Do not use aliases (e.g. CLICK_ELEMENT, DRAW, TYPE are forbidden).
4. Keep the sequence concise, minimal, and directly verifiable.

OUTPUT FORMAT:
Output ONLY a JSON array of actions adhering to the schema:
[
  {
    "action_type": "<CANONICAL_PRIMITIVE>",
    "target": {
      "name": "<logical label or window title>",
      "role": "<button | edit | window | canvas | tab>",
      "context": "<container/app name>",
      "text_hint": "<visible text if applicable>"
    },
    "parameters": { ... },
    "outcome_contract": {
      "expected_state_transition": "<verifiable physical or UI state change>",
      "verification_strategy": "<WINDOW_FOCUS | OCR_TEXT | UIA_TEXT | UIA_STATE | CANVAS_CHANGE | AUTO_ROUTED>"
    },
    "rationale": "<why this primitive is needed>"
  }
]
Do not output markdown text or explanations outside the JSON array.
"""


class ComposedPrimitiveSequence(BaseModel):
    """An executable sequence of canonical primitives planned for a sub-objective."""

    sequence_id: str = Field(default_factory=lambda: f"seq_{uuid4().hex[:8]}")
    sub_objective_id: Optional[str] = Field(default=None)
    actions: List[AbstractAction] = Field(default_factory=list)
    rationale: str = Field(default="")
    estimated_steps: int = Field(default=0)


class PrimitiveComposer:
    """Composes canonical primitive sequences from structured context and objectives.

    Operates without domain-specific heuristics. Driven by LLM / StructuredAgentContext
    or deterministic fallback for standard generic sub-goals.
    """

    def __init__(
        self,
        model_client: Optional[Any] = None,
        validator: Optional[PrimitiveValidator] = None,
    ):
        self._model_client = model_client
        self._validator = validator or PrimitiveValidator()

    async def compose(
        self,
        objective: StructuredObjective,
        sub_objective: Optional[SubObjective],
        context: StructuredAgentContext,
    ) -> ComposedPrimitiveSequence:
        """Compose a canonical primitive sequence for the given sub-objective.

        P0 Invariant: PrimitiveComposer does NOT act as an independent planner.
        If an LLM is available, it proposes a primitive sequence subject to strict validation;
        otherwise, it fails closed without inventing deterministic semantic plans.
        """
        goal_text = sub_objective.title if sub_objective else (objective.user_goal or objective.raw_prompt)

        # 1. Attempt LLM-driven composition using bounded context
        if self._model_client is not None:
            try:
                seq = await self._compose_via_llm(goal_text, objective, sub_objective, context)
                if seq and seq.actions:
                    return seq
            except Exception as e:
                logger.warning("LLM primitive composition failed: %s", e)

        # 2. FAIL-CLOSED: Zero semantic plan invention without authoritative PlanDirective
        logger.warning(
            "[PrimitiveComposer] Composition without PlanDirective failed closed for goal: '%s'",
            goal_text,
        )
        return ComposedPrimitiveSequence(
            sub_objective_id=sub_objective.sub_id if sub_objective else None,
            actions=[],
            rationale="Composition failed closed: PlanDirective required for authoritative execution",
            estimated_steps=0,
        )

    async def recompose_after_failure(
        self,
        objective: StructuredObjective,
        sub_objective: Optional[SubObjective],
        context: StructuredAgentContext,
        failure_report: Any,
    ) -> ComposedPrimitiveSequence:
        """Recompose primitive sequence incorporating failure diagnosis (Guardrail 9).

        P0 Invariant: Replanning is exclusively owned by AgentPlanner.replan().
        PrimitiveComposer does not independently invent alternative task plans.
        """
        logger.info(
            "[PRIMITIVE COMPOSER] Recomposing request received with failure diagnosis: %s",
            getattr(failure_report, "diagnosis", str(failure_report)),
        )
        return await self.compose(objective, sub_objective, context)

    def compose_from_directive(
        self,
        directive: PlanDirective,
        context: Optional[StructuredAgentContext] = None,
    ) -> ComposedPrimitiveSequence:
        """Compose canonical primitives mechanically from an authoritative PlanDirective."""
        if not directive or not directive.preferred_primitives:
            logger.warning("[PrimitiveComposer] Cannot compose from empty or missing PlanDirective (Fail-Closed)")
            return ComposedPrimitiveSequence(
                sub_objective_id=directive.subgoal_id if directive else None,
                actions=[],
                rationale="Empty or invalid PlanDirective",
                estimated_steps=0,
            )

        actions: List[AbstractAction] = []

        for prim_type in directive.preferred_primitives:
            target = (
                directive.semantic_targets[0]
                if directive.semantic_targets
                else SemanticTarget(name=directive.subgoal_title, role="control")
            )
            params: Dict[str, Any] = {}

            if prim_type == AbstractActionType.DRAW_STROKES:
                if directive.creative_payload and "strokes" in directive.creative_payload:
                    params["strokes"] = directive.creative_payload["strokes"]
            elif prim_type == AbstractActionType.TYPE_TEXT:
                if directive.creative_payload and "text" in directive.creative_payload:
                    params["text"] = directive.creative_payload["text"]
                    params["press_enter"] = True
                else:
                    params["text"] = directive.subgoal_title
                    params["press_enter"] = True
            elif prim_type == AbstractActionType.LAUNCH_APPLICATION:
                payload = directive.creative_payload or {}
                app = payload.get("application_name") or payload.get("app_name") or target.name or "application"
                params["application_name"] = app
            elif prim_type == AbstractActionType.SAVE_FILE:
                payload = directive.creative_payload or {}
                fname = payload.get("filename") or (target.name if (target and target.name not in ("file", "current_artifact", "artifact")) else "")
                params["filename"] = fname
                params["target_path"] = payload.get("target_path", fname)
                params["target_dir"] = payload.get("target_dir", "desktop")
                params["format"] = payload.get("format", fname.rsplit(".", 1)[-1] if "." in fname else "")
            elif prim_type == AbstractActionType.SEND_HOTKEY:
                payload = directive.creative_payload or {}
                params["hotkey"] = payload.get("hotkey") or ("Ctrl+S" if "save" in directive.subgoal_title.lower() or "ctrl" in directive.subgoal_title.lower() else "enter")
            elif prim_type == AbstractActionType.FOCUS_WINDOW:
                payload = directive.creative_payload or {}
                if "hwnd" in payload:
                    params["hwnd"] = payload["hwnd"]
                params["application_name"] = target.name if target else ""

            action = AbstractAction(
                action_type=prim_type,
                target=target,
                parameters=params,
                outcome_contract=directive.expected_outcome,
                expected_effect=directive.expected_outcome.expected_state_transition,
                rationale=f"Composed from PlanDirective '{directive.directive_id}' for subgoal '{directive.subgoal_id}'",
            )
            val_res = self._validator.validate_action(action)
            if val_res.is_valid and val_res.validated_action:
                actions.append(val_res.validated_action)
            elif val_res.is_valid:
                actions.append(action)
            else:
                logger.warning("Directive action validation failed: %s (%s)", val_res.failure_reason, val_res.failure_code)

        return ComposedPrimitiveSequence(
            sub_objective_id=directive.subgoal_id,
            actions=actions,
            rationale=f"Composed mechanically from PlanDirective {directive.directive_id}",
            estimated_steps=len(actions),
        )

    async def _compose_via_llm(
        self,
        goal_text: str,
        objective: StructuredObjective,
        sub_objective: Optional[SubObjective],
        context: StructuredAgentContext,
    ) -> Optional[ComposedPrimitiveSequence]:
        """Invoke LLM to generate canonical primitive sequence."""
        context_str = json.dumps(context.to_dict(), indent=2)
        prompt = (
            f"OBJECTIVE: {goal_text}\n\n"
            f"BOUNDED CONTEXT:\n{context_str}\n\n"
            "Generate the canonical primitive action sequence as a JSON array."
        )

        resp = await self._model_client.generate(
            ModelGenerateRequest(
                system_prompt=COMPOSER_SYSTEM_PROMPT,
                prompt=prompt,
                temperature=0.0,
            )
        )

        content = resp.content.strip()
        m = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
        if m:
            content = m.group(0)

        raw_actions = json.loads(content)
        validated_actions: List[AbstractAction] = []
        for raw in raw_actions:
            v_res = self._validator.validate_action(raw)
            if v_res.is_valid and v_res.validated_action:
                validated_actions.append(v_res.validated_action)
            else:
                logger.warning("Composer generated invalid action: %s (%s)", v_res.failure_reason, v_res.failure_code)

        if validated_actions:
            return ComposedPrimitiveSequence(
                sub_objective_id=sub_objective.sub_id if sub_objective else None,
                actions=validated_actions,
                rationale="LLM-composed primitive sequence",
                estimated_steps=len(validated_actions),
            )
        return None
