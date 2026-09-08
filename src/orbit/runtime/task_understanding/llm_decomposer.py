"""Cognitive LLM-powered task understanding and multi-step intent decomposer.

Enables ORBIT to understand complex, compound, conversational, and open-ended
natural language instructions by leveraging active local or cloud AI models.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from orbit.runtime.model_runtime.session_manager import ModelSessionManager
from orbit.runtime.models.models import ModelChatRequest, ModelChatMessage, ModelRole
from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)

logger = logging.getLogger(__name__)


class LLMTaskDecomposer:
    """Cognitive intent decomposer transforming arbitrary natural language instructions into structured task intents."""

    SYSTEM_PROMPT = """You are ORBIT's Cognitive Task Decomposition Engine for Windows 11 Desktop Automation.
Your role is to analyze a natural language user request and decompose it into an ordered sequence of discrete, structured execution intents.

SUPPORTED GOALS:
- OPEN_APPLICATION: Launch or switch to an application (e.g., Notepad, Calculator, Paint, Chrome, Word, Terminal, File Explorer).
- WRITE_TEXT: Type or compose text into an active application or document.
- CALCULATE: Perform arithmetic or numerical calculation.
- DRAW: Draw, sketch, or render illustrations/shapes on canvas (e.g., in Paint).
- SEARCH: Search the web, browser, or local files.
- CLICK_TARGET: Click a specific UI button, tab, menu, or control.
- COPY_CONTENT: Copy text or files to clipboard.
- PASTE_CONTENT: Paste clipboard content into active document.
- SAVE_DOCUMENT: Save current file/document to disk.
- CLOSE_APPLICATION: Close or terminate an application.
- SELECT_OPTION: Choose an item from dropdown, list, or radio options.
- NAVIGATE: Navigate to a URL, directory path, or view.

OUTPUT FORMAT REQUIREMENTS:
You MUST output ONLY a valid JSON object matching this exact schema:
{
  "thought_process": "Brief step-by-step reasoning of how to achieve the goal on Windows",
  "intents": [
    {
      "goal": "OPEN_APPLICATION",
      "application_name": "Notepad",
      "target_role": "window",
      "content": null,
      "parameters": {}
    },
    {
      "goal": "WRITE_TEXT",
      "application_name": "Notepad",
      "target_role": "edit",
      "content": "Exact text to type, or description of content",
      "parameters": {}
    }
  ]
}

CRITICAL RULES:
1. Do NOT include conversational filler, explanations outside JSON, or markdown blocks unless JSON-formatted.
2. If the user asks for multi-application workflows (e.g. calculate something and write to notepad), decompose into ordered steps.
3. Preserve all exact strings, numbers, formulas, and filenames.
4. Output valid, parseable JSON only.
"""

    def __init__(self, model_session_manager: Optional[ModelSessionManager] = None) -> None:
        self._msm = model_session_manager

    def set_model_session_manager(self, msm: ModelSessionManager) -> None:
        self._msm = msm

    async def decompose_request(self, raw_request: Union[RawTaskRequest, str]) -> List[StructuredTaskIntent]:
        """Use active AI model to decompose natural language request into structured intents."""
        if isinstance(raw_request, str):
            req_obj = RawTaskRequest(raw_text=raw_request)
        else:
            req_obj = raw_request

        if self._msm is None:
            logger.debug("LLMTaskDecomposer: ModelSessionManager unavailable")
            return []

        if not self._msm.is_model_active():
            # Attempt auto-activation of registered local model
            try:
                reg = getattr(self._msm, "_registry", None)
                if reg and hasattr(reg, "list_models"):
                    models = await reg.list_models()
                    if models:
                        await self._msm.activate_model(models[0].model_id)
            except Exception as auto_act_err:
                logger.debug("Auto-activation in decomposer: %s", auto_act_err)

        if not self._msm.is_model_active():
            logger.debug("LLMTaskDecomposer: No active AI model available for cognitive decomposition")
            return []

        user_text = req_obj.raw_text.strip()
        logger.info("LLMTaskDecomposer: Decomposing complex task '%s' via active model...", user_text)

        chat_req = ModelChatRequest(
            messages=[
                ModelChatMessage(role=ModelRole.SYSTEM, content=self.SYSTEM_PROMPT),
                ModelChatMessage(
                    role=ModelRole.USER,
                    content=f"Decompose this Windows desktop automation instruction:\n\n\"{user_text}\"",
                ),
            ],
            temperature=0.1,
            max_tokens=512,
        )

        try:
            resp = await asyncio.wait_for(self._msm.chat(chat_req), timeout=4.0)
            raw_content = (resp.content or "").strip()
            return self._parse_llm_json_response(raw_content, req_obj)
        except Exception as ex:
            logger.warning("LLMTaskDecomposer failed: %s", ex)
            return []

    async def decompose(self, raw_request: Union[RawTaskRequest, str]) -> TaskUnderstandingResult:
        """Decompose request into a fully validated TaskUnderstandingResult."""
        from orbit.runtime.task_understanding.validator import TaskUnderstandingValidator
        if isinstance(raw_request, str):
            req_obj = RawTaskRequest(raw_text=raw_request)
        else:
            req_obj = raw_request

        intents = await self.decompose_request(req_obj)
        validator = TaskUnderstandingValidator()
        return validator.validate(req_obj, intents)


    def _parse_llm_json_response(self, raw_content: str, raw_request: RawTaskRequest) -> List[StructuredTaskIntent]:
        """Safely extract, repair, and deserialize JSON intents from model output."""
        # 1. Clean markdown code fences if present
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        # 2. Extract JSON object substring
        json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)

        try:
            data = json.loads(cleaned)
        except Exception as json_err:
            logger.warning("Failed to parse JSON from LLM: %s. Raw: %s", json_err, raw_content[:200])
            return []

        intents_data = data.get("intents", [])
        if not isinstance(intents_data, list) or not intents_data:
            return []

        thought = data.get("thought_process", "")
        structured_intents: List[StructuredTaskIntent] = []

        for idx, item in enumerate(intents_data):
            if not isinstance(item, dict):
                continue

            goal_str = str(item.get("goal", "UNKNOWN")).upper()
            try:
                goal_enum = TaskGoal(goal_str)
            except ValueError:
                goal_enum = TaskGoal.UNKNOWN

            app_name = (
                item.get("application_name")
                or item.get("target_name")
                or item.get("target")
                or item.get("app")
            )
            target_role = item.get("target_role", "window")
            content = item.get("content")
            params = item.get("parameters") or {}


            # Generate target reference
            target = TargetReference(
                semantic_type="application" if goal_enum == TaskGoal.OPEN_APPLICATION else "ui_control",
                identifier=app_name,
                role=target_role,
                is_ambiguous=False,
            )

            # Generate constraints
            constraints = TaskConstraints(
                application_name=app_name,
                content=content,
                custom_parameters=params,
                is_negated=False,
            )

            evidence = [
                f"source_goal: {goal_enum.value}",
                f"llm_cognitive_decomposition: {raw_request.raw_text[:60]}",
            ]
            if thought:
                evidence.append(f"reasoning: {thought[:80]}")

            intent = StructuredTaskIntent(
                sequence_index=idx,
                goal=goal_enum,
                target=target,
                constraints=constraints,
                evidence=evidence,
                is_negated=False,
                is_ambiguous=False,
            )
            structured_intents.append(intent)

        logger.info("LLMTaskDecomposer successfully produced %d structured intents", len(structured_intents))
        return structured_intents
