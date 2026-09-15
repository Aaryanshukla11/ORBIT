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
        "painting", "photo", "photograph", "realistic", "character", "tree"
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

        # 1. Host Application Lifecycle Requirements (supporting multi-application compound goals)
        detected_apps: List[str] = []
        if target_app:
            detected_apps.append(target_app)
        if objective.target_entities:
            for ent in objective.target_entities:
                if ent and ent not in detected_apps:
                    detected_apps.append(ent)

        known_app_patterns = {
            "calculator": r"\b(calculator|calc)\b",
            "notepad": r"\b(notepad)\b",
            "paint": r"\b(paint|mspaint)\b",
            "browser": r"\b(browser|chrome|edge|firefox)\b",
            "wordpad": r"\b(wordpad)\b",
            "excel": r"\b(excel)\b",
            "word": r"\b(word|winword)\b",
        }
        for app_canonical, pat in known_app_patterns.items():
            if re.search(pat, p_lower):
                if not any(app_canonical in d.lower() for d in detected_apps):
                    detected_apps.append(app_canonical.capitalize())

        if not detected_apps and ("open" in p_lower or "launch" in p_lower):
            m_open = re.search(r"(?:open|launch)\s+([a-zA-Z0-9_\-]+)", prompt, re.IGNORECASE)
            if m_open:
                detected_apps.append(m_open.group(1).strip())
            else:
                detected_apps.append("desktop")

        for idx, app_name in enumerate(detected_apps):
            req_id = "req_app_lifecycle" if len(detected_apps) == 1 else f"req_app_lifecycle_{app_name.lower()}"
            requirements.append(
                GoalRequirement(
                    requirement_id=req_id,
                    requirement_type="APPLICATION_LIFECYCLE",
                    semantic_description=f"Host application '{app_name}' must be launched and focused in foreground",
                    required_capability_category=CapabilityCategory.DESKTOP_CONTROL,
                    mandatory=True,
                    success_criteria=[f"window_active:{app_name.lower()}" if app_name.lower() != "desktop" else "desktop_ready"],
                    alternatives=["web_browser_alternative", "secondary_installed_tool"],
                    parameters={"application_name": app_name},
                )
            )

        # 2. Creative / Visual Content Creation Requirement
        has_drawing = action_type == "draw" or "draw" in p_lower or "paint" in p_lower or "sketch" in p_lower
        if has_drawing:
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

        # 3. Calculation Requirement (independent of drawing/text in compound goals)
        has_calc = (
            action_type == "calculate"
            or "calculate" in p_lower
            or "multiplied" in p_lower
            or bool(re.search(r"\d+\s*[\+\-\*\/x×÷]\s*\d+", prompt))
        )
        calculated_result = ""
        if has_calc:
            calc_expr = prompt
            m_expr = re.search(r"(\d+(?:\.\d+)?)\s*([\+\-\*\/xX×÷]|multiplied by|times|plus|minus|divided by)\s*(\d+(?:\.\d+)?)", prompt)
            if m_expr:
                try:
                    op_str = m_expr.group(2).lower()
                    n1 = float(m_expr.group(1))
                    n2 = float(m_expr.group(3))
                    if op_str in ("*", "x", "×", "multiplied by", "times"):
                        res_val = n1 * n2
                    elif op_str in ("+", "plus"):
                        res_val = n1 + n2
                    elif op_str in ("-", "minus"):
                        res_val = n1 - n2
                    elif op_str in ("/", "÷", "divided by") and n2 != 0:
                        res_val = n1 / n2
                    else:
                        res_val = None
                    if res_val is not None:
                        calculated_result = str(int(res_val) if res_val.is_integer() else res_val)
                        calc_expr = f"{int(n1) if n1.is_integer() else n1} {op_str} {int(n2) if n2.is_integer() else n2}"
                except Exception:
                    pass

            if not calculated_result:
                m_direct = re.search(r"calculate\s+(\d+)", prompt, re.IGNORECASE)
                if m_direct:
                    calculated_result = m_direct.group(1)

            requirements.append(
                GoalRequirement(
                    requirement_id="req_calculation",
                    requirement_type="DATA_EXTRACTION",
                    semantic_description=f"Compute arithmetic expression '{calc_expr}' and observe displayed result",
                    required_capability_category=CapabilityCategory.INPUT,
                    mandatory=True,
                    success_criteria=[f"arithmetic_result_displayed:{calculated_result}" if calculated_result else "arithmetic_result_displayed"],
                    alternatives=["calculator_gui_buttons", "calculator_keyboard_numpad"],
                    parameters={"expression": calc_expr, "expected_result": calculated_result},
                )
            )

        # 4. Text Entry Requirement (independent of calculation/drawing in compound goals)
        has_text = action_type == "type" or "type" in p_lower or "write" in p_lower or "enter" in p_lower
        if has_text:
            text_payload = str(objective.parameters.get("text", "")).strip()
            text_source = "explicit"
            if not text_payload:
                m_quote = re.search(r"['\"]([^'\"]+)['\"]", prompt)
                if m_quote:
                    text_payload = m_quote.group(1)
                elif has_calc and ("result" in p_lower or "answer" in p_lower):
                    text_payload = calculated_result
                    text_source = "calculation_result"
                else:
                    m_typed = re.search(r"(?:type|write|enter)\s+([a-zA-Z0-9_\s]+?)(?:\s+(?:into|in|on)\b|\s*$)", prompt, re.IGNORECASE)
                    if m_typed and m_typed.group(1).strip().lower() not in ("the result", "result"):
                        text_payload = m_typed.group(1).strip()
                    else:
                        text_payload = prompt

            # Infer target application for text entry if specified in compound goal
            text_target_app = ""
            m_target_app = re.search(r"(?:into|in|on)\s+([a-zA-Z0-9_\-]+)", prompt, re.IGNORECASE)
            if m_target_app:
                candidate_app = m_target_app.group(1).strip()
                if candidate_app.lower() in known_app_patterns or any(candidate_app.lower() in d.lower() for d in detected_apps):
                    text_target_app = candidate_app
            if not text_target_app and detected_apps:
                for a in detected_apps:
                    if a.lower() in ("notepad", "wordpad", "word", "document", "editor"):
                        text_target_app = a
                        break

            requirements.append(
                GoalRequirement(
                    requirement_id="req_text_input",
                    requirement_type="DATA_INPUT",
                    semantic_description="Input exact textual payload into document buffer",
                    required_capability_category=CapabilityCategory.INPUT,
                    mandatory=True,
                    success_criteria=[f"text_buffer_contains:{text_payload[:15]}"],
                    alternatives=["keyboard_keystrokes", "clipboard_atomic_paste"],
                    parameters={"text": text_payload, "text_source": text_source, "target_application": text_target_app},
                )
            )

        # 5. File Persistence / Save Requirement (independent mandatory requirement)
        # Check if the prompt specifically mandates saving, exporting, or writing an artifact to disk / file
        has_file_save = (
            action_type in ("save", "export", "file_management")
            or bool(re.search(r"\b(?:save|export|persist)\b", p_lower))
            or bool(re.search(r"\b(?:write|store|output|download)\s+(?:to|into)\s+(?:file|disk|[a-zA-Z0-9_\-\.\:\/\\]+\.[a-zA-Z0-9]{2,5})\b", prompt, re.IGNORECASE))
            or bool(re.search(r"\b(?:as|to)\s+['\"]?[a-zA-Z0-9_\-\.\:\/\\]+\.[a-zA-Z0-9]{2,5}['\"]?\b", prompt, re.IGNORECASE))
            or bool(objective.parameters.get("file_path"))
            or bool(objective.parameters.get("filename"))
        )
        if has_file_save:
            filename = ""
            target_directory = ""
            target_path = ""
            expected_format = ""

            # 1. Structured parameters take precedence
            if objective.parameters.get("file_path"):
                target_path = str(objective.parameters.get("file_path")).strip()
            elif objective.parameters.get("filename"):
                filename = str(objective.parameters.get("filename")).strip()
            if objective.parameters.get("target_directory"):
                target_directory = str(objective.parameters.get("target_directory")).strip()

            # 2. Generalized natural language decomposition
            if not target_path and not filename:
                m_file = re.search(
                    r"\b(?:save|export|write|persist|store|download|output)\s+(?:it\s+|the\s+file\s+|the\s+image\s+|the\s+document\s+|the\s+result\s+)?(?:as|to|into)\s+['\"]?([a-zA-Z0-9_\-\.\:\/\\]+)['\"]?(?:\s+(?:on|in|to)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\:\/\\]+))?",
                    prompt,
                    re.IGNORECASE,
                )
                if m_file:
                    cand_target = m_file.group(1).strip()
                    cand_dest = m_file.group(2).strip() if m_file.group(2) else ""
                    if "." in cand_target:
                        filename = cand_target
                        if cand_dest:
                            target_directory = cand_dest
                    elif "/" in cand_target or "\\" in cand_target:
                        target_path = cand_target
                    else:
                        if cand_dest:
                            target_directory = cand_dest
                            filename = cand_target
                        else:
                            filename = cand_target

                if not filename and not target_path:
                    m_ext = re.search(r"\b(?:as|to|into)\s+['\"]?([a-zA-Z0-9_\-\.\:\/\\]+\.[a-zA-Z0-9]{2,5})['\"]?", prompt, re.IGNORECASE)
                    if m_ext:
                        cand = m_ext.group(1).strip()
                        if "/" in cand or "\\" in cand or ":" in cand:
                            target_path = cand
                        else:
                            filename = cand

            if not target_path:
                if filename and target_directory:
                    target_path = f"{target_directory}/{filename}"
                elif filename:
                    target_path = filename
                elif target_directory:
                    target_path = target_directory
                else:
                    target_path = "artifact_file"

            if "." in target_path:
                expected_format = target_path.rsplit(".", 1)[-1].lower()
            elif "." in filename:
                expected_format = filename.rsplit(".", 1)[-1].lower()

            requirements.append(
                GoalRequirement(
                    requirement_id="req_file_management",
                    requirement_type="FILE_MANAGEMENT",
                    semantic_description=f"Persist document/artifact to disk at target location '{target_path}'",
                    required_capability_category=CapabilityCategory.DOCUMENT,
                    mandatory=True,
                    success_criteria=[f"file_exists_on_disk:{target_path}", f"file_non_empty:{target_path}"],
                    alternatives=["save_as_dialog_automation", "shortcut_ctrl_s_automation", "direct_file_export"],
                    parameters={
                        "file_path": target_path,
                        "filename": filename or target_path,
                        "target_directory": target_directory,
                        "expected_format": expected_format,
                        "target_application": detected_apps[0] if detected_apps else "",
                    },
                )
            )

        # Domain classification
        domain_count = sum([1 for flag in (has_drawing, has_calc, has_text, has_file_save) if flag])
        if domain_count > 1 or len(detected_apps) > 1:
            target_domain = "compound_multi_stage"
        elif has_drawing:
            target_domain = "creative_drawing"
        elif has_text:
            target_domain = "document_editing"
        elif has_calc:
            target_domain = "system_automation"
        elif has_file_save:
            target_domain = "document_editing"
        else:
            target_domain = "general"

        # 6. Final State Verification Requirement
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
