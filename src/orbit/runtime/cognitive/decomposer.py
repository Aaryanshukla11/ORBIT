"""Hierarchical Goal Decomposer.

Decomposes composite user goals into an ordered sequence of SubObjective milestones.
STRICT GUARDRAILS (Guardrails 2 & 8):
- Fast-path decomposition is strictly restricted to generic linguistic syntax (e.g. 'and then', 'after that', numbered lists).
- NO domain-specific keyword branching ('if laptop...', 'if email...', 'if spreadsheet...').
- Complex semantic decomposition is handled purely by the LLM.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from orbit.runtime.cognitive.models import DecomposedPlan, StructuredObjective, SubObjective
from orbit.runtime.models.models import ModelGenerateRequest

logger = logging.getLogger(__name__)

DECOMPOSITION_SYSTEM_PROMPT = """You are ORBIT's Hierarchical Goal Decomposer.
Your role is to break down a high-level user goal into a sequential list of atomic, milestone sub-objectives.

Output ONLY a valid JSON object matching this schema:
{
  "reasoning": "<concise justification for the sub-objective breakdown>",
  "sub_objectives": [
    {
      "title": "<short descriptive milestone title>",
      "description": "<what should be achieved in this milestone>",
      "target_entity": "<primary application, website, file, or tool needed, or null>",
      "success_criteria": ["<verifiable criteria that indicate this milestone is complete>"],
      "constraints": ["<any specific constraints for this step>"]
    }
  ]
}
Do not include markdown code block formatting (e.g. ```json), just the plain JSON string.
"""


class HierarchicalGoalDecomposer:
    """Decomposes structured objectives into ordered milestone sub-objectives."""

    # Generic linguistic conjunctions for syntactic splitting
    _CONJUNCTION_PATTERN = re.compile(
        r"\s+(?:and\s+then|after\s+that|followed\s+by)\s+",
        re.IGNORECASE,
    )
    _NUMBERED_LIST_PATTERN = re.compile(
        r"(?:^|\r?\n)\s*\d+[\.\)]\s+",
        re.MULTILINE,
    )

    def __init__(self, model_session_manager: Optional[Any] = None) -> None:
        self._model_session_manager = model_session_manager

    def set_model_session_manager(self, msm: Any) -> None:
        self._model_session_manager = msm

    async def decompose(
        self,
        objective: StructuredObjective,
        world_model: Optional[Any] = None,
    ) -> DecomposedPlan:
        """Decompose a StructuredObjective into an ordered DecomposedPlan."""
        prompt = objective.raw_prompt.strip()

        # 1. If StructuredObjective already has explicit subtasks extracted, use them
        if objective.subtasks and len(objective.subtasks) > 1:
            subs = [
                SubObjective(
                    title=task.strip(),
                    description=f"Accomplish subtask: {task.strip()}",
                    success_criteria=[f"Subtask '{task.strip()}' completed"],
                    constraints=list(objective.constraints),
                )
                for task in objective.subtasks
                if task.strip()
            ]
            if len(subs) > 1:
                return DecomposedPlan(
                    objective_id=objective.objective_id,
                    raw_prompt=prompt,
                    sub_objectives=subs,
                    reasoning="Decomposed from explicit intent subtasks",
                )

        # 2. Pure Linguistic Syntax Splitting (Fast-path without domain keywords)
        linguistic_subs = self._split_linguistic_syntax(prompt, objective)
        if linguistic_subs and len(linguistic_subs) > 1:
            return DecomposedPlan(
                objective_id=objective.objective_id,
                raw_prompt=prompt,
                sub_objectives=linguistic_subs,
                reasoning="Syntactic linguistic conjunction splitting",
            )

        # 3. LLM-Driven Decomposition for complex multi-step goals
        if self._model_session_manager is not None:
            try:
                llm_plan = await self._decompose_with_llm(objective)
                if llm_plan and len(llm_plan.sub_objectives) > 1:
                    return llm_plan
            except Exception as e:
                logger.warning("[DECOMPOSER] LLM decomposition fallback to atomic goal: %s", e)

        # 4. Atomic Goal (Single milestone sub-objective)
        return DecomposedPlan(
            objective_id=objective.objective_id,
            raw_prompt=prompt,
            sub_objectives=[
                SubObjective(
                    title=objective.user_goal,
                    description=f"Achieve overall goal: {objective.user_goal}",
                    target_entity=objective.target_entities[0] if objective.target_entities else None,
                    success_criteria=objective.success_criteria or [objective.end_condition],
                    constraints=list(objective.constraints),
                )
            ],
            reasoning="Single atomic milestone",
        )

    def _split_linguistic_syntax(
        self,
        prompt: str,
        objective: StructuredObjective,
    ) -> Optional[List[SubObjective]]:
        """Splits composite goals strictly on generic linguistic syntax.

        NO domain keywords (laptop, paint, email, etc.) are allowed here.
        """
        # Check numbered list pattern: "1. do X\n 2. do Y"
        numbered_parts = self._NUMBERED_LIST_PATTERN.split(prompt)
        cleaned_numbered = [p.strip() for p in numbered_parts if p.strip()]
        if len(cleaned_numbered) >= 2:
            return [
                SubObjective(
                    title=clause,
                    description=clause,
                    success_criteria=[f"Completed: {clause}"],
                    constraints=list(objective.constraints),
                )
                for clause in cleaned_numbered
            ]

        # Check sequential conjunctions: "X and then Y", "X after that Y"
        conjunction_parts = self._CONJUNCTION_PATTERN.split(prompt)
        cleaned_conjunctions = [p.strip() for p in conjunction_parts if p.strip()]
        if len(cleaned_conjunctions) >= 2:
            return [
                SubObjective(
                    title=clause,
                    description=clause,
                    success_criteria=[f"Completed: {clause}"],
                    constraints=list(objective.constraints),
                )
                for clause in cleaned_conjunctions
            ]

        return None

    async def _decompose_with_llm(self, objective: StructuredObjective) -> Optional[DecomposedPlan]:
        """Query active LLM to decompose complex composite goal."""
        active_ctx = (
            self._model_session_manager.get_active_context()
            if hasattr(self._model_session_manager, "get_active_context")
            else None
        )
        if not active_ctx:
            return None

        prompt_payload = (
            f"Goal: {objective.user_goal}\n"
            f"Prompt: {objective.raw_prompt}\n"
            f"Deliverable: {objective.deliverable or 'N/A'}\n"
            f"Success Criteria: {', '.join(objective.success_criteria) if objective.success_criteria else objective.end_condition}\n"
            f"Constraints: {', '.join(objective.constraints) if objective.constraints else 'None'}"
        )

        gen_req = ModelGenerateRequest(
            prompt=prompt_payload,
            system_prompt=DECOMPOSITION_SYSTEM_PROMPT,
            temperature=0.0,
        )
        resp = await self._model_session_manager.generate(gen_req)
        content = resp.content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        parsed = json.loads(content)
        raw_subs = parsed.get("sub_objectives", [])
        if not isinstance(raw_subs, list) or not raw_subs:
            return None

        subs = []
        for s in raw_subs:
            if isinstance(s, dict) and "title" in s:
                subs.append(
                    SubObjective(
                        title=str(s.get("title", "")),
                        description=str(s.get("description", "")),
                        target_entity=s.get("target_entity"),
                        success_criteria=list(s.get("success_criteria", [])),
                        constraints=list(s.get("constraints", [])),
                    )
                )

        if subs:
            return DecomposedPlan(
                objective_id=objective.objective_id,
                raw_prompt=objective.raw_prompt,
                sub_objectives=subs,
                reasoning=str(parsed.get("reasoning", "LLM hierarchical decomposition")),
            )
        return None
