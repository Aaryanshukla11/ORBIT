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
        """Deterministic heuristic parsing ensuring reliable offline operation without task-specific shortcuts."""
        lower = prompt.lower()
        entities: List[str] = []
        constraints: List[str] = []
        parameters: Dict[str, Any] = {}

        # 1. Detect negative constraints
        if "don't" in lower or "do not" in lower or "never" in lower:
            for part in prompt.split(","):
                p_low = part.lower()
                if "don't" in p_low or "do not" in p_low or "never" in p_low:
                    constraints.append(part.strip())

        # 2. Extract explicit or mentioned Application Target (purely from application identifiers, NOT from shape or drawing words)
        from orbit.runtime.capabilities.application_launcher import APPROVED_APPLICATION_REGISTRY
        app_name = None

        # Check explicit prepositional / container phrases e.g. "in Figma", "into Notepad", "using Paint", "with Calculator"
        m_app_ctx = re.search(r"\b(?:in|into|using|with|on|from)\s+([a-zA-Z0-9_\-]+)", prompt, re.IGNORECASE)
        if m_app_ctx:
            cand_app = m_app_ctx.group(1).strip().lower()
            if cand_app not in {"the", "a", "an", "this", "desktop", "canvas", "file", "disk", "workspace"}:
                app_name = cand_app

        # Check launch / open verb phrases e.g. "open Edge", "launch Microsoft Edge", "start Paint", "bring up Notepad"
        if not app_name:
            m_launch_phrase = re.search(
                r"\b(?:open|launch|start|bring\s+up|run|switch\s+to)\s+(?:the\s+)?(?:application\s+|app\s+|program\s+)?([a-zA-Z0-9_\-]+(?:\s+[a-zA-Z0-9_\-]+)?)",
                prompt,
                re.IGNORECASE,
            )
            if m_launch_phrase:
                extracted = m_launch_phrase.group(1).strip().lower()
                # Strip trailing conjunctions and next verbs
                for stop_w in (" and", " then", " to", " with", " do", " draw", " type", " save", " &"):
                    if extracted.endswith(stop_w) or f"{stop_w} " in extracted:
                        extracted = extracted.split(stop_w)[0].strip()
                # Exclude non-application direct objects like "search box", "file", "document", "dialog"
                if extracted and extracted not in {"search box", "search", "file", "document", "dialog", "window", "tab", "menu", "button", "link"}:
                    if extracted in APPROVED_APPLICATION_REGISTRY or not any(w in extracted for w in ("search", "button", "box")):
                        app_name = extracted

        # Check if known registered application alias is explicitly in the prompt text
        if not app_name:
            for alias in APPROVED_APPLICATION_REGISTRY:
                # Require word-boundary match so "paint" doesn't match inside other words
                if re.search(rf"\b{re.escape(alias)}\b", lower):
                    app_name = alias
                    break

        if app_name:
            # Canonical normalization for standard aliases
            if app_name == "paint":
                app_name = "mspaint"
            elif app_name in ("calc", "calculator.exe"):
                app_name = "calculator"
            elif app_name in ("msedge", "microsoft edge"):
                app_name = "edge"
            parameters["app_name"] = app_name
            entities.append(app_name)

        # 3. Detect File Save / Persistence Parameters (Extract WHAT is to be saved, do NOT invent fake defaults)
        has_save_intent = bool(re.search(r"\b(?:save|export|persist|write|store)\b", lower))
        save_match = re.search(
            r"\b(?:save|export|persist|write|store)\b.*?\b(?:as|to|into)?\s*['\"]?([a-zA-Z0-9_\-\.\:\/\\]+\.[a-zA-Z0-9]{2,5})['\"]?",
            prompt,
            re.IGNORECASE,
        )
        if not save_match and has_save_intent:
            save_match = re.search(r"['\"]?([a-zA-Z0-9_\-\.\:\/\\]+\.[a-zA-Z0-9]{2,5})['\"]?", prompt)

        target_file = None
        target_dir = "desktop" if "desktop" in lower else ("documents" if "documents" in lower else "workspace")
        expected_format = None
        if save_match:
            target_file = save_match.group(1).strip()
            if "." in target_file:
                expected_format = target_file.rsplit(".", 1)[-1].lower()
            parameters["requires_save"] = True
            parameters["filename"] = target_file
            parameters["target_dir"] = target_dir
            if expected_format:
                parameters["format"] = expected_format
            if target_file not in entities:
                entities.append(target_file)
        elif has_save_intent:
            parameters["requires_save"] = True
            parameters["target_dir"] = target_dir

        # 4. Action Classification & Semantic Parameters
        has_draw_verb = bool(re.search(r"\b(?:draw|sketch|render|illustrate)\b", lower))
        has_type_verb = bool(re.search(r"\b(?:type|write|enter\s+text|input)\b", lower))
        has_launch_verb = bool(re.search(r"\b(?:open|launch|start|bring\s+up|run|switch\s+to|focus)\b", lower))
        has_calc_expr = bool(re.search(r"\d+\s*[\+\-\*\/x×÷]\s*\d+", prompt)) or ("calculate" in lower and any(char.isdigit() for char in prompt))

        # A. Pure Application Launch Intent
        if has_launch_verb and not has_draw_verb and not has_save_intent and not has_type_verb and not has_calc_expr:
            parameters["action_type"] = "open"
            target = app_name or prompt
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=prompt,
                end_condition=f"{target}_is_open_and_active",
                target_entities=entities or [target],
                constraints=constraints,
                parameters=parameters,
            )

        # B. Drawing / Visual Content
        if has_draw_verb or (app_name in ("paint", "mspaint") and any(w in lower for w in ("circle", "square", "rectangle", "triangle", "line", "cube", "star", "shape")) and not re.match(r"^\s*(?:open|launch|start|bring\s+up)\s+(?:the\s+)?(?:app\s+)?(?:mspaint|paint)\s*$", lower)):
            parameters["action_type"] = "draw"
            if "canvas" not in entities:
                entities.append("canvas")
            # Extract requested shape/subject from prompt purely as content data
            shape = "geometric_shape"
            shape_match = re.search(
                r"\b(?:draw|sketch|render)\s+(?:a\s+|an\s+)?(?:[a-zA-Z]+\s+)?([a-zA-Z0-9_\-]+)",
                prompt,
                re.IGNORECASE,
            )
            if shape_match:
                extracted = shape_match.group(1).lower().strip()
                if extracted not in {"in", "on", "using", "with", "the", "paint", "mspaint", "canvas", "it", "this"}:
                    shape = extracted
            parameters["shape"] = shape

            end_cond = f"content_rendered_{shape}"
            if target_file:
                end_cond += f"_and_file_{target_file}_saved"

            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=prompt,
                end_condition=end_cond,
                target_entities=entities,
                constraints=constraints,
                parameters=parameters,
            )

        # C. Pure Save File Intent
        if has_save_intent and target_file and not has_draw_verb and not has_type_verb and not has_launch_verb:
            parameters["action_type"] = "save"
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=prompt,
                end_condition=f"file_{target_file}_saved",
                target_entities=entities,
                constraints=constraints,
                parameters=parameters,
            )

        # D. Typing / Text Entry Intent
        if has_type_verb:
            parameters["action_type"] = "type"
            text_match = re.search(r'(?:type|write|input)\s+["\']([^"\']+)["\']', prompt, re.IGNORECASE)
            if not text_match:
                text_match = re.search(r'(?:type|write|input)\s+(.+?)(?:\s+in|\s+into|\s+to|$)', prompt, re.IGNORECASE)
            text_payload = text_match.group(1).strip() if text_match else "Hello World"
            parameters["text"] = text_payload
            target_label = app_name or "document"
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=prompt,
                end_condition=f"{target_label}_contains_text",
                target_entities=entities or [target_label],
                constraints=constraints,
                parameters=parameters,
            )

        # E. Calculation Intent
        if has_calc_expr or ("calculate" in lower and not has_launch_verb):
            parameters["action_type"] = "calculate"
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=prompt,
                end_condition="calculation_result_displayed",
                target_entities=entities or ["calculator"],
                constraints=constraints,
                parameters=parameters,
            )

        # F. Generic Fallback Launch Intent
        if has_launch_verb:
            parameters["action_type"] = "open"
            target = app_name or prompt
            return StructuredObjective(
                raw_prompt=prompt,
                user_goal=prompt,
                end_condition=f"{target}_is_open_and_active",
                target_entities=entities or [target],
                constraints=constraints,
                parameters=parameters,
            )

        # Default Generalized Objective
        return StructuredObjective(
            raw_prompt=prompt,
            user_goal=prompt,
            end_condition="task_completed",
            target_entities=entities,
            constraints=constraints,
            parameters=parameters,
        )
