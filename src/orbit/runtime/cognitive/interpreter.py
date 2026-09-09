"""LLM Intent Interpreter parsing natural language user prompts into StructuredObjectives."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from orbit.runtime.cognitive.models import StructuredObjective
from orbit.runtime.models.models import ModelGenerateRequest

logger = logging.getLogger(__name__)

INTENT_INTERPRETATION_SYSTEM_PROMPT = """You are the ORBIT Cognitive Intent Interpreter.
Your job is to analyze the user's prompt and extract a structured, verifiable objective for OS desktop automation.

Output ONLY a single valid JSON object with the following fields:
{
  "user_goal": "<concise summary of what the user wants to achieve>",
  "end_condition": "<verifiable physical/perceptual end state condition, e.g. canvas_has_cube_drawing, notepad_contains_hello_world, calc_shows_42>",
  "target_entities": ["<application or control names, e.g. mspaint, notepad, calculator, canvas, button>"],
  "constraints": ["<any negative or positive constraints, e.g. do_not_close_unsaved>"],
  "deliverable": "<expected concrete output deliverable if any, e.g. spreadsheet, text document, drawing, or null>",
  "success_criteria": ["<explicit observable criteria that confirm completion>"],
  "assumptions": ["<allowed operating assumptions>"],
  "subtasks": ["<high-level milestone subtasks if compound goal>"],
  "parameters": {
     "app_name": "<primary app executable or name, e.g. mspaint, notepad.exe, calc>",
     "action_type": "<e.g. draw, type, click, open, calculate>",
     "shape": "<shape name if drawing, e.g. cube, square, circle>",
     "text": "<literal text payload if typing>",
     "target_label": "<label if clicking>"
  }
}
Do not include markdown code block formatting (e.g. ```json), just the plain JSON string.
"""


class LLMIntentInterpreter:
    """Interprets raw user prompts into StructuredObjective using active LLM or deterministic fallback."""

    def __init__(self, model_session_manager: Optional[Any] = None) -> None:
        self._model_session_manager = model_session_manager

    def set_model_session_manager(self, msm: Any) -> None:
        self._model_session_manager = msm

    @property
    def model_session_manager(self) -> Optional[Any]:
        return self._model_session_manager

    async def interpret(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> StructuredObjective:
        """Interpret a natural language user prompt into a StructuredObjective."""
        clean_prompt = prompt.strip() if prompt else ""
        if not clean_prompt:
            return StructuredObjective(
                raw_prompt="",
                user_goal="Empty prompt",
                end_condition="no_action_required",
                target_entities=[],
                constraints=[],
                parameters={},
            )

        # 1. Try LLM inference if ModelSessionManager is active
        if self._model_session_manager is not None:
            try:
                active_ctx = (
                    self._model_session_manager.get_active_context()
                    if hasattr(self._model_session_manager, "get_active_context")
                    else None
                )
                if active_ctx:
                    logger.debug("Interpreting intent via active LLM model (%s)", active_ctx.model_id)
                    gen_req = ModelGenerateRequest(
                        prompt=f"User Prompt: {clean_prompt}",
                        system_prompt=INTENT_INTERPRETATION_SYSTEM_PROMPT,
                        temperature=0.0,
                    )
                    resp = await self._model_session_manager.generate(gen_req)
                    content = resp.content.strip()
                    # Strip any markdown code formatting
                    if content.startswith("```"):
                        content = re.sub(r"^```(?:json)?\s*", "", content)
                        content = re.sub(r"\s*```$", "", content)
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "user_goal" in parsed and "end_condition" in parsed:
                        return StructuredObjective(
                            raw_prompt=clean_prompt,
                            user_goal=str(parsed.get("user_goal", clean_prompt)),
                            end_condition=str(parsed.get("end_condition", "goal_achieved")),
                            target_entities=list(parsed.get("target_entities", [])),
                            constraints=list(parsed.get("constraints", [])),
                            deliverable=parsed.get("deliverable"),
                            success_criteria=list(parsed.get("success_criteria", [])),
                            assumptions=list(parsed.get("assumptions", [])),
                            subtasks=list(parsed.get("subtasks", [])),
                            parameters=dict(parsed.get("parameters", {})),
                        )
            except Exception as ex:
                logger.warning("LLM Intent Interpretation fallback to heuristic parsing: %s", ex)

        # 2. Deterministic Heuristic Parser Fallback
        return self._interpret_heuristic(clean_prompt, context or {})

    def _interpret_heuristic(self, prompt: str, context: Dict[str, Any]) -> StructuredObjective:
        """Deterministic heuristic parsing ensuring reliable offline operation."""
        lower = prompt.lower()
        entities: List[str] = []
        constraints: List[str] = []
        parameters: Dict[str, Any] = {}

        # Detect negative constraints
        if "don't" in lower or "do not" in lower or "never" in lower:
            for part in prompt.split(","):
                p_low = part.lower()
                if "don't" in p_low or "do not" in p_low or "never" in p_low:
                    constraints.append(part.strip())

        # Application mapping
        app_name = None
        if "paint" in lower or "draw" in lower or "cube" in lower or "square" in lower or "circle" in lower or "sketch" in lower:
            if "paint" in lower or "mspaint" in lower or "draw" in lower:
                app_name = "mspaint"
                entities.append("mspaint")
                entities.append("canvas")
        elif "notepad" in lower or "note" in lower or "text editor" in lower:
            app_name = "notepad"
            entities.append("notepad")
        elif "calc" in lower or "calculator" in lower:
            app_name = "calculator"
            entities.append("calculator")
        elif "browser" in lower or "chrome" in lower or "edge" in lower:
            app_name = "edge"
            entities.append("edge")

        if app_name:
            parameters["app_name"] = app_name

        # Drawing Intent (e.g. "open paint and draw a car", "draw a cube", "draw a square")
        if "draw" in lower or "sketch" in lower or "cube" in lower or ("paint" in lower and any(w in lower for w in ("car", "house", "tree", "box", "circle", "square", "triangle", "star"))):
            parameters["action_type"] = "draw"
            shape = "cube"
            # Extract requested shape/subject from prompt
            shape_match = re.search(r'(?:draw|sketch)\s+(?:a\s+|an\s+)?([a-zA-Z0-9_\-]+)', prompt, re.IGNORECASE)
            if shape_match:
                extracted = shape_match.group(1).lower().strip()
                if extracted not in {"in", "on", "using", "with", "the", "paint", "mspaint", "canvas"}:
                    shape = extracted
            if "car" in lower or "automobile" in lower or "vehicle" in lower:
                shape = "car"
            elif "cube" in lower:
                shape = "cube"
            elif "square" in lower:
                shape = "square"
            elif "circle" in lower:
                shape = "circle"
            elif "rectangle" in lower or "box" in lower:
                shape = "rectangle"
            elif "triangle" in lower:
                shape = "triangle"
            elif "star" in lower:
                shape = "star"
            elif "house" in lower:
                shape = "house"
            elif "tree" in lower:
                shape = "tree"
            elif "stickman" in lower or "person" in lower:
                shape = "stickman"
            parameters["shape"] = shape
            end_condition = f"canvas_has_{shape}_drawing"
            user_goal = f"Open Paint and draw a {shape} on the canvas"
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=user_goal,
                end_condition=end_condition,
                target_entities=entities or ["mspaint", "canvas"],
                constraints=constraints,
                parameters=parameters,
            )

        # Typing/Writing Intent (e.g. "open notepad and type hello", "write test in notepad")
        if "type" in lower or "write" in lower or "text" in lower:
            parameters["action_type"] = "type"
            # Extract text payload
            text_match = re.search(r'(?:type|write)\s+["\']([^"\']+)["\']', prompt, re.IGNORECASE)
            if not text_match:
                text_match = re.search(r'(?:type|write)\s+(.+?)(?:\s+in|\s+into|\s+to|$)', prompt, re.IGNORECASE)
            text_payload = text_match.group(1).strip() if text_match else "Hello World"
            parameters["text"] = text_payload
            end_condition = f"{app_name or 'document'}_contains_{text_payload[:15].replace(' ', '_').lower()}"
            user_goal = f"Open {app_name or 'editor'} and type '{text_payload}'"
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=user_goal,
                end_condition=end_condition,
                target_entities=entities or [app_name or "notepad"],
                constraints=constraints,
                parameters=parameters,
            )

        # Calculation Intent (e.g. "open calculator and calculate 2 + 2")
        if "calc" in lower or "calculate" in lower or "+" in lower or "*" in lower:
            parameters["action_type"] = "calculate"
            user_goal = f"Open calculator and compute expression in '{prompt}'"
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=user_goal,
                end_condition="calculator_shows_result",
                target_entities=entities or ["calculator"],
                constraints=constraints,
                parameters=parameters,
            )

        # Generic Open / Interaction
        if "open" in lower or "launch" in lower:
            parameters["action_type"] = "open"
            target = app_name or prompt.replace("open", "").replace("launch", "").strip()
            user_goal = f"Launch and focus {target}"
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=user_goal,
                end_condition=f"{target}_is_open_and_active",
                target_entities=entities or [target],
                constraints=constraints,
                parameters=parameters,
            )

        # Default Generic Objective
        return StructuredObjective(
            raw_prompt=prompt,
            user_goal=prompt,
            end_condition="task_completed",
            target_entities=entities,
            constraints=constraints,
            parameters=parameters,
        )
