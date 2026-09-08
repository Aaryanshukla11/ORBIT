"""Cognitive LLM-powered multi-step plan synthesizer for complex desktop automation workflows."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from orbit.adapters.observation.snapshot import ObservationSnapshot
from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import ModelChatRequest, ModelChatMessage, ModelRole
from orbit.runtime.planning.models import (
    DeferredGroundingRequirement,
    ExecutableTaskPlan,
    PlanActionType,
    PlanStatus,
    PlanStep,
    Postcondition,
    Precondition,
)
from orbit.runtime.task_understanding.models import (
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
    TaskUnderstandingResult,
)
from orbit.runtime.targeting.models import TargetStrategy

logger = logging.getLogger(__name__)


class LLMPlanSynthesizer:
    """Synthesizes dependency-aware ExecutableTaskPlan DAGs for complex or open-ended multi-step instructions."""

    SYSTEM_PROMPT = """You are ORBIT's Autonomous Plan Synthesizer for Windows 11 Desktop Automation.
Your role is to construct a validated, multi-step execution graph (DAG) of PlanSteps to achieve the user's objective.

AVAILABLE PLAN ACTION TYPES:
- ENSURE_APPLICATION_OPEN: Launch or focus the specified application window (target_app: "Notepad", "Calculator", "Paint", "Chrome", "Word", "Terminal").
- FOCUS_APPLICATION: Bring application window to foreground.
- LOCATE_INPUT_SURFACE: Focus document text editor, canvas, or input field.
- ENTER_TEXT: Type specified text payload into focused surface (content: "text string").
- ACTIVATE_CONTROL: Click a button, icon, tab, or interactive element (identifier: "Button Name", "Equal Button", "Canvas").
- SEARCH_QUERY: Enter query into browser address bar or search box.
- VERIFY_APPLICATION_AVAILABLE: Verify application is responsive.
- VERIFY_TARGET_EFFECT: Verify state change or calculation.

OUTPUT FORMAT:
Output ONLY a valid JSON object matching this schema:
{
  "thought": "Reasoning on plan structure and step dependencies",
  "steps": [
    {
      "step_id": "step_1",
      "action_type": "ENSURE_APPLICATION_OPEN",
      "description": "Ensure application 'Calculator' is open and ready",
      "target_app": "Calculator",
      "target_role": "window",
      "content": null,
      "dependencies": []
    },
    {
      "step_id": "step_2",
      "action_type": "ACTIVATE_CONTROL",
      "description": "Click buttons for calculation",
      "target_app": "Calculator",
      "target_role": "button",
      "content": "456 * 23 =",
      "dependencies": ["step_1"]
    },
    {
      "step_id": "step_3",
      "action_type": "ENSURE_APPLICATION_OPEN",
      "description": "Ensure application 'Notepad' is open",
      "target_app": "Notepad",
      "target_role": "window",
      "content": null,
      "dependencies": ["step_2"]
    },
    {
      "step_id": "step_4",
      "action_type": "ENTER_TEXT",
      "description": "Type calculated result into Notepad",
      "target_app": "Notepad",
      "target_role": "edit",
      "content": "Result: 10,488",
      "dependencies": ["step_3"]
    }
  ]
}

SAFETY INVARIANTS:
1. Do NOT pre-bake physical screen coordinates (x, y). All grounding is resolved dynamically at runtime.
2. Dependencies must form a valid DAG (no cycles).
3. Output valid JSON only without conversational markdown.
"""

    def __init__(self, model_session_manager: Optional[ModelSessionManager] = None) -> None:
        self._msm = model_session_manager

    def set_model_session_manager(self, msm: ModelSessionManager) -> None:
        self._msm = msm

    async def synthesize_plan(
        self,
        understanding: TaskUnderstandingResult,
        task_id: Optional[str] = None,
        snapshot: Optional[ObservationSnapshot] = None,
    ) -> Optional[List[PlanStep]]:
        """Synthesize multi-step execution plan using active AI model."""
        if self._msm is None or not self._msm.is_model_active():
            return None

        prompt_text = understanding.raw_request.raw_text
        open_windows = [w.window_title for w in (snapshot.windows if snapshot else []) if w.window_title]

        context_msg = f"User Request: \"{prompt_text}\"\n"
        if open_windows:
            context_msg += f"Currently Open Desktop Windows: {open_windows[:8]}\n"

        chat_req = ModelChatRequest(
            messages=[
                ModelChatMessage(role=ModelRole.SYSTEM, content=self.SYSTEM_PROMPT),
                ModelChatMessage(role=ModelRole.USER, content=context_msg),
            ],
            temperature=0.1,
            max_tokens=768,
        )

        try:
            resp = await asyncio.wait_for(self._msm.chat(chat_req), timeout=4.0)
            raw_content = (resp.content or "").strip()
            return self._parse_llm_plan_steps(raw_content, prompt_text)
        except Exception as ex:
            logger.warning("LLMPlanSynthesizer failed: %s", ex)
            return None

    def _parse_llm_plan_steps(self, raw_content: str, prompt_text: str) -> Optional[List[PlanStep]]:
        """Parse, validate, and construct PlanStep instances from model JSON."""
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)

        try:
            data = json.loads(cleaned)
        except Exception as ex:
            logger.warning("Failed to decode JSON plan from LLM: %s", ex)
            return None

        steps_data = data.get("steps", [])
        if not isinstance(steps_data, list) or not steps_data:
            return None

        thought = data.get("thought", "")
        plan_steps: List[PlanStep] = []
        id_map: Dict[str, str] = {}

        for item in steps_data:
            if not isinstance(item, dict):
                continue

            raw_step_id = item.get("step_id", f"step_{uuid4().hex[:6]}")
            act_type_str = str(item.get("action_type", "ENSURE_APPLICATION_OPEN")).upper()
            try:
                act_type = PlanActionType(act_type_str)
            except ValueError:
                act_type = PlanActionType.ENSURE_APPLICATION_OPEN

            app_name = item.get("target_app") or "Application"
            desc = item.get("description") or f"Execute {act_type.value} on {app_name}"
            content = item.get("content")
            raw_deps = item.get("dependencies", [])

            # Generate unique internal step_id
            real_step_id = f"step_{uuid4().hex[:6]}"
            id_map[raw_step_id] = real_step_id

            target_ref = TargetReference(
                semantic_type="application" if act_type in (PlanActionType.ENSURE_APPLICATION_OPEN, PlanActionType.FOCUS_APPLICATION) else "ui_control",
                identifier=app_name,
                role=item.get("target_role", "window"),
                is_ambiguous=False,
            )

            constraints = TaskConstraints(
                application_name=app_name,
                content=content,
                is_negated=False,
            )

            resolved_deps = [id_map[d] for d in raw_deps if d in id_map]

            step = PlanStep(
                step_id=real_step_id,
                action_type=act_type,
                description=desc,
                target=target_ref,
                constraints=constraints,
                dependencies=resolved_deps,
                deferred_grounding=DeferredGroundingRequirement(
                    strategy_preferences=[TargetStrategy.WINDOW_TITLE, TargetStrategy.ACCESSIBILITY_ELEMENT],
                    target_reference=target_ref,
                    grounding_notes=f"Synthesized step for '{app_name}'",
                ),
                evidence=[
                    f"llm_synthesized_action: {act_type.value}",
                    f"task: {prompt_text[:50]}",
                ],
                is_ambiguous=False,
            )
            plan_steps.append(step)

        if plan_steps:
            logger.info("LLMPlanSynthesizer produced %d valid plan steps (thought: %s)", len(plan_steps), thought[:60])
            return plan_steps

        return None
