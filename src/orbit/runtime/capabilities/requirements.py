"""Goal Requirement Extractor decomposing objectives into declarative requirement specifications."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from orbit.runtime.capabilities.models import (
    CapabilityCategory,
    GoalRequirement,
    GoalRequirementSet,
)
from orbit.runtime.cognitive.models import StructuredObjective

logger = logging.getLogger(__name__)


class GoalRequirementExtractor:
    """Extracts declarative goal requirements (WHAT is required) without prematurely deciding HOW."""

    COMPLEX_VISUAL_KEYWORDS = {
        "portrait", "face", "boy", "girl", "man", "woman", "person",
        "human", "dog", "cat", "animal", "landscape", "scenery",
        "painting", "photo", "photograph", "realistic", "character", "tree", "car"
    }

    BASIC_GEOMETRY_KEYWORDS = {
        "cube", "square", "circle", "rectangle", "triangle", "star",
        "line", "box", "polygon", "oval", "cube_3d", "diamond"
    }

    def extract_requirements(self, objective: StructuredObjective) -> GoalRequirementSet:
        """Decompose a StructuredObjective into an ordered, decoupled GoalRequirementSet."""
        prompt = getattr(objective, "raw_prompt", str(objective.user_goal or "")).strip()
        p_lower = prompt.lower()
        action_type = str(objective.parameters.get("action_type", "")).lower()
        target_app = str(objective.parameters.get("app_name", "")).strip()

        if not target_app and objective.target_entities:
            target_app = objective.target_entities[0].strip()

        requirements: List[GoalRequirement] = []
        target_domain = "general"
        required_fidelity = "STANDARD"

        # 1. Host Application Lifecycle Requirement
        if target_app or "open" in p_lower or "launch" in p_lower:
            requirements.append(
                GoalRequirement(
                    requirement_id="req_app_lifecycle",
                    requirement_type="APPLICATION_LIFECYCLE",
                    semantic_description=f"Host application '{target_app or 'desktop'}' must be launched and focused in foreground",
                    required_capability_category=CapabilityCategory.DESKTOP_CONTROL,
                    mandatory=True,
                    success_criteria=[f"window_active:{target_app.lower()}" if target_app else "desktop_ready"],
                    alternatives=["web_browser_alternative", "secondary_installed_tool"],
                    parameters={"application_name": target_app},
                )
            )

        # 2. Creative / Visual Content Creation Requirement
        if action_type == "draw" or "draw" in p_lower or "paint" in p_lower or "sketch" in p_lower:
            target_domain = "creative_drawing"
            is_complex = any(re.search(rf"\b{kw}\b", p_lower) for kw in self.COMPLEX_VISUAL_KEYWORDS)
            is_basic = any(re.search(rf"\b{kw}\b", p_lower) for kw in self.BASIC_GEOMETRY_KEYWORDS)

            subject = "visual_content"
            for kw in self.COMPLEX_VISUAL_KEYWORDS:
                if re.search(rf"\b{kw}\b", p_lower):
                    subject = kw
                    break
            if subject == "visual_content" and is_basic:
                for kw in self.BASIC_GEOMETRY_KEYWORDS:
                    if re.search(rf"\b{kw}\b", p_lower):
                        subject = kw
                        break

            if is_complex and not is_basic:
                required_fidelity = "HIGH_FIDELITY_SEMANTIC"
                visual_type = "portrait" if ("portrait" in p_lower or "face" in p_lower or "boy" in p_lower or "girl" in p_lower) else "complex_scene"
                requirements.append(
                    GoalRequirement(
                        requirement_id="req_content_visual",
                        requirement_type="CONTENT_CREATION",
                        semantic_description=f"Render recognizable, high-fidelity visual artwork representing '{subject}' on target canvas",
                        required_capability_category=CapabilityCategory.CREATIVE_VISUAL,
                        mandatory=True,
                        success_criteria=[f"semantic_entity_recognized:{subject}", "fidelity_level:recognizable_semantic_representation"],
                        alternatives=[
                            "ai_image_generation_and_paste",
                            "browser_image_generation_and_import",
                            "external_art_tool_composition",
                        ],
                        parameters={
                            "semantic_subject": subject,
                            "visual_type": visual_type,
                            "required_fidelity": "HIGH_FIDELITY_SEMANTIC",
                            "min_semantic_confidence": 0.85,
                        },
                    )
                )
            else:
                required_fidelity = "PRIMITIVE"
                shape = objective.parameters.get("shape", subject if is_basic else "cube")
                requirements.append(
                    GoalRequirement(
                        requirement_id="req_content_visual",
                        requirement_type="CONTENT_CREATION",
                        semantic_description=f"Render clean geometric contour for shape '{shape}' on canvas",
                        required_capability_category=CapabilityCategory.CREATIVE_VISUAL,
                        mandatory=True,
                        success_criteria=[f"geometric_contour_present:{shape}"],
                        alternatives=["vector_stroke_drawing", "shape_tool_selection"],
                        parameters={
                            "shape": shape,
                            "visual_type": "geometric_primitive",
                            "required_fidelity": "PRIMITIVE",
                        },
                    )
                )

        # 3. Text Entry Requirement
        elif action_type == "type" or "type" in p_lower or "write" in p_lower:
            target_domain = "document_editing"
            text_payload = str(objective.parameters.get("text", "")).strip()
            if not text_payload:
                m = re.search(r"['\"]([^'\"]+)['\"]", prompt)
                if m:
                    text_payload = m.group(1)
                else:
                    text_payload = prompt

            requirements.append(
                GoalRequirement(
                    requirement_id="req_text_input",
                    requirement_type="DATA_INPUT",
                    semantic_description=f"Input exact textual payload into document buffer",
                    required_capability_category=CapabilityCategory.INPUT,
                    mandatory=True,
                    success_criteria=[f"text_buffer_contains:{text_payload[:15]}"],
                    alternatives=["keyboard_keystrokes", "clipboard_atomic_paste"],
                    parameters={"text": text_payload},
                )
            )

        # 4. Calculation Requirement
        elif action_type == "calculate" or "calculate" in p_lower or "multiplied" in p_lower:
            target_domain = "system_automation"
            requirements.append(
                GoalRequirement(
                    requirement_id="req_calculation",
                    requirement_type="DATA_EXTRACTION",
                    semantic_description="Compute arithmetic expression and observe displayed result",
                    required_capability_category=CapabilityCategory.INPUT,
                    mandatory=True,
                    success_criteria=["arithmetic_result_displayed"],
                    alternatives=["calculator_gui_buttons", "calculator_keyboard_numpad"],
                    parameters={"expression": prompt},
                )
            )

        # 5. Final State Verification Requirement
        end_cond = str(objective.end_condition or "goal_completed")
        requirements.append(
            GoalRequirement(
                requirement_id="req_state_verification",
                requirement_type="STATE_VERIFICATION",
                semantic_description=f"Independently verify end condition '{end_cond}' against fresh desktop perception",
                required_capability_category=CapabilityCategory.SYSTEM,
                mandatory=True,
                success_criteria=[f"verified_end_condition:{end_cond}"],
                alternatives=["tripartite_goal_verifier"],
                parameters={"end_condition": end_cond},
            )
        )

        return GoalRequirementSet(
            objective_id=getattr(objective, "objective_id", f"reqset_{abs(hash(prompt)) % 100000}"),
            raw_goal=prompt,
            requirements=requirements,
            target_domain=target_domain,
            required_fidelity=required_fidelity,
        )
