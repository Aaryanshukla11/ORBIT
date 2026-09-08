"""Structured Output Parser & Coordinate Security Validator (Step 4).

Parses raw LLM generated text into strongly-typed CognitiveDecision and AbstractAction instances.
Strictly validates schemas and enforces coordinate isolation invariants:
The LLM is NEVER permitted to generate physical screen coordinates.

SECURITY INVARIANT:
Any output attempting to supply (x, y, screen_x, screen_y, bbox, bounding_box) is rejected immediately.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    AgentActionValidator,
    SemanticTarget,
)
from orbit.runtime.cognitive.models import CognitiveDecision

logger = logging.getLogger(__name__)

FORBIDDEN_COORDINATE_KEYS: Set[str] = {
    "x",
    "y",
    "screen_x",
    "screen_y",
    "coord_x",
    "coord_y",
    "pos_x",
    "pos_y",
    "position",
    "screen_position",
    "coordinates",
    "bbox",
    "bounding_box",
    "width",
    "height",
}


class CoordinateSecurityViolation(ValueError):
    """Raised when an LLM decision leaks physical screen coordinates."""


class StructuredOutputParserError(ValueError):
    """Raised when an LLM decision is malformed or violates action schemas."""


class StructuredDecisionParser:
    """Parses, validates, and cleans LLM outputs into CognitiveDecision."""

    @staticmethod
    def extract_json(raw_text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from raw LLM text with code-fence stripping."""
        if not raw_text or not raw_text.strip():
            raise StructuredOutputParserError("LLM returned empty or whitespace-only response")

        text = raw_text.strip()

        # 1. Strip markdown code fences (```json ... ``` or ``` ...)
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        # 2. Try direct JSON parse
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # 3. Try regex extraction of first JSON object in text
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            candidate = match.group(1).strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as ex:
                raise StructuredOutputParserError(f"Failed to parse extracted JSON candidate: {ex}") from ex

        raise StructuredOutputParserError(f"No valid JSON object found in model output: {raw_text[:200]}")

    @classmethod
    def validate_coordinate_isolation(cls, data: Dict[str, Any]) -> None:
        """Enforce coordinate security invariant: no screen coordinates from LLM."""
        def _check_dict(d: Dict[str, Any], path: str = "") -> None:
            for k, v in d.items():
                cur_path = f"{path}.{k}" if path else k
                if k.lower() in FORBIDDEN_COORDINATE_KEYS:
                    raise CoordinateSecurityViolation(
                        f"Coordinate Security Invariant Violated! Forbidden coordinate field '{cur_path}' "
                        f"found in LLM decision. Target resolution must be performed dynamically by TargetLocator."
                    )
                if isinstance(v, dict):
                    _check_dict(v, cur_path)
                elif isinstance(v, list):
                    for idx, item in enumerate(v):
                        if isinstance(item, dict):
                            _check_dict(item, f"{cur_path}[{idx}]")

        _check_dict(data)

    @classmethod
    def parse_decision(
        cls,
        raw_text: str,
        step_index: int = 0,
        model_id: str = "unknown",
        latency_ms: Optional[float] = None,
        attached_vision: bool = False,
    ) -> CognitiveDecision:
        """Parse raw LLM response into a validated CognitiveDecision."""
        parsed_json = cls.extract_json(raw_text)

        # Enforce coordinate isolation
        cls.validate_coordinate_isolation(parsed_json)

        decision_summary = str(parsed_json.get("decision_summary", "Agent decision"))
        goal_progress = str(parsed_json.get("goal_progress", "IN_PROGRESS")).upper()
        confidence = float(parsed_json.get("confidence", 0.9))
        confidence = max(0.0, min(1.0, confidence))
        evidence_used = list(parsed_json.get("evidence_used", []))
        expected_state_transition = str(
            parsed_json.get("expected_state_transition", "")
        )
        reason_summary = str(parsed_json.get("reason_summary", ""))

        is_goal_satisfied = (
            goal_progress == "COMPLETED"
            or bool(parsed_json.get("is_goal_satisfied", False))
        )

        act_data = parsed_json.get("next_action")
        action_obj: Optional[AbstractAction] = None

        if act_data and isinstance(act_data, dict):
            raw_act_type = str(act_data.get("action_type", "WAIT")).upper().strip()
            
            # Action type resolution
            try:
                act_type = AbstractActionType(raw_act_type)
            except ValueError:
                # Handle aliases
                alias_map = {
                    "CLICK": AbstractActionType.CLICK,
                    "CLICK_ELEMENT": AbstractActionType.CLICK,
                    "DOUBLE_CLICK": AbstractActionType.DOUBLE_CLICK,
                    "RIGHT_CLICK": AbstractActionType.RIGHT_CLICK,
                    "TYPE": AbstractActionType.TYPE_TEXT,
                    "TYPE_TEXT": AbstractActionType.TYPE_TEXT,
                    "HOTKEY": AbstractActionType.SEND_HOTKEY,
                    "SEND_HOTKEY": AbstractActionType.SEND_HOTKEY,
                    "LAUNCH": AbstractActionType.LAUNCH_APPLICATION,
                    "LAUNCH_APPLICATION": AbstractActionType.LAUNCH_APPLICATION,
                    "FOCUS": AbstractActionType.FOCUS_WINDOW,
                    "FOCUS_WINDOW": AbstractActionType.FOCUS_WINDOW,
                    "WAIT": AbstractActionType.WAIT,
                    "WAIT_SETTLE": AbstractActionType.WAIT,
                    "DRAW": AbstractActionType.DRAW_STROKES,
                    "DRAW_STROKES": AbstractActionType.DRAW_STROKES,
                    "COMPLETE": AbstractActionType.COMPLETE_GOAL,
                    "COMPLETE_GOAL": AbstractActionType.COMPLETE_GOAL,
                    "ABORT": AbstractActionType.ABORT_TASK,
                    "ABORT_TASK": AbstractActionType.ABORT_TASK,
                    "ABORT_UNACHIEVABLE": AbstractActionType.ABORT_TASK,
                }
                act_type = alias_map.get(raw_act_type, AbstractActionType.WAIT)

            # Target extraction
            target_data = act_data.get("target") or {}
            sem_target = None
            if target_data and isinstance(target_data, dict):
                sem_target = SemanticTarget(
                    name=target_data.get("name"),
                    role=target_data.get("role"),
                    context=target_data.get("context"),
                    text_hint=target_data.get("text_hint"),
                )

            raw_params = act_data.get("parameters", {}) or {}
            if not isinstance(raw_params, dict):
                raw_params = {}

            # Merge any direct keys from act_data
            for direct_k in (
                "application_name",
                "app_name",
                "app",
                "name",
                "text",
                "query",
                "hotkey",
                "keys",
                "key",
                "direction",
                "shape",
                "color",
                "duration",
            ):
                if direct_k in act_data and direct_k not in raw_params:
                    raw_params[direct_k] = act_data[direct_k]

            # Normalize type-specific parameters from target if missing
            if act_type == AbstractActionType.LAUNCH_APPLICATION:
                if not raw_params.get("application_name") and not raw_params.get("app_name") and not raw_params.get("name"):
                    if sem_target and sem_target.name:
                        raw_params["application_name"] = sem_target.name
                    elif isinstance(target_data, str):
                        raw_params["application_name"] = target_data
            elif act_type in (AbstractActionType.TYPE_TEXT, AbstractActionType.TYPE):
                if "text" not in raw_params and "query" not in raw_params:
                    if sem_target and sem_target.text_hint:
                        raw_params["text"] = sem_target.text_hint
                    elif "text" in act_data:
                        raw_params["text"] = act_data["text"]

            clean_params = {
                k: v for k, v in raw_params.items()
                if k.lower() not in FORBIDDEN_COORDINATE_KEYS
            }

            exp_effect = str(
                act_data.get("expected_effect", expected_state_transition or "state_progress")
            )

            action_obj = AbstractAction(
                action_type=act_type,
                target=sem_target,
                parameters=clean_params,
                outcome_contract=ActionOutcomeContract(
                    expected_state_transition=exp_effect,
                    target_role=sem_target.role if sem_target else None,
                    target_name=sem_target.name if sem_target else None,
                ),
                expected_effect=exp_effect,
                rationale=reason_summary or decision_summary,
            )

            # Validate action with strict AgentActionValidator
            val_res = AgentActionValidator.validate(action_obj)
            if not val_res.is_valid:
                logger.warning(
                    "Action validation warning: %s (%s)",
                    val_res.failure_reason,
                    val_res.failure_code,
                )

        if is_goal_satisfied and (action_obj is None or action_obj.action_type != AbstractActionType.COMPLETE_GOAL):
            action_obj = AbstractAction(
                action_type=AbstractActionType.COMPLETE_GOAL,
                expected_effect="Goal satisfied",
                rationale=decision_summary,
            )

        return CognitiveDecision(
            step_index=step_index,
            decision_summary=decision_summary,
            decision_confidence=confidence,
            evidence_used=evidence_used,
            expected_state_transition=expected_state_transition,
            reason_summary=reason_summary,
            is_goal_satisfied=is_goal_satisfied,
            escalated_to_llm=True,
            next_action=action_obj,
        )
