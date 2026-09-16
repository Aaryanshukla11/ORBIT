"""Unified Multi-Modal Reasoning Context Builder.

Phase 3A (Astra 6 Modernization):
Constructs standardized, high-density Vision-Action reasoning payloads combining
Set-of-Marks (SOM) visual overlays, hierarchical UIA accessibility trees,
compacted trajectory histories, and diagnostic failure feedback for frontier VLMs.
"""

from __future__ import annotations

import base64
import io
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image

from orbit.adapters.observation.snapshot import ObservedElement, ObservedWindow
from orbit.runtime.cognitive.context_compactor import ContextCompactor
from orbit.runtime.cognitive.models import (
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.trajectory_memory import TrajectoryMemory
from orbit.runtime.perception.set_of_marks import SetOfMarksGenerator, SOMResult

logger = logging.getLogger(__name__)

ASTRA6_SYSTEM_PROMPT = """You are ORBIT (Astra 6 Architecture), an authoritative autonomous computer-using agent operating a native Windows desktop.

You perceive the desktop state through high-resolution screenshots with Set-of-Marks (SOM) visual tags, structured UI Automation element trees, and OCR token streams.

Your goal is to inspect the current state, reason about progress, and propose the exact NEXT single atomic action to advance towards the user's objective.

Output your next action STRICTLY as a JSON object matching this schema:
{
  "thought": "1-2 sentence step-by-step reasoning explaining what you observe and why this action was selected",
  "action_type": "CLICK" | "DOUBLE_CLICK" | "RIGHT_CLICK" | "TYPE_TEXT" | "SEND_HOTKEY" | "LAUNCH_APPLICATION" | "SAVE_FILE" | "WAIT" | "SCROLL" | "DRAG" | "COMPLETE_GOAL" | "FAIL_GOAL",
  "target": {
    "name": "Target name or Set-of-Marks tag, e.g. 'Save Button [4]' or 'File name:'",
    "role": "button" | "edit" | "window" | "menu_item" | "tab" | "canvas" | null,
    "mark_id": 4,
    "box_2d": [ymin, xmin, ymax, xmax]
  },
  "parameters": {
    "text": "text to type",
    "hotkey": "Ctrl+S",
    "application_name": "notepad",
    "filename": "document.txt"
  },
  "expected_effect": "Precise description of the expected UI or system state transition",
  "confidence": 0.95
}

CRITICAL RULES:
1. Always reference existing UI elements or Set-of-Marks tags [N]. Never hallucinate coordinate points.
2. If an action previously failed, consult the failure feedback and choose an alternate strategy or recovery action.
3. Propose COMPLETE_GOAL ONLY when the objective is fully verified on screen or disk.
"""


@dataclass
class MultimodalContextPayload:
    """Standardized multimodal token and image payload for LLM/VLM backends."""

    system_prompt: str
    user_text_prompt: str
    som_image_base64: Optional[str] = None
    som_image_mime: str = "image/jpeg"
    som_result: Optional[SOMResult] = None
    compacted_history: str = ""
    uia_tree_summary: str = ""
    active_window_summary: str = ""
    diagnostic_feedback: str = ""
    estimated_tokens: int = 0
    build_duration_ms: float = 0.0

    def to_openai_messages(self, model_name: str = "gpt-4o") -> List[Dict[str, Any]]:
        """Convert payload to standard OpenAI Vision Chat Completion messages format."""
        user_content: List[Dict[str, Any]] = []

        # 1. Attach SOM Image if available
        if self.som_image_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{self.som_image_mime};base64,{self.som_image_base64}",
                    "detail": "high",
                },
            })

        # 2. Attach text reasoning prompt
        user_content.append({
            "type": "text",
            "text": self.user_text_prompt,
        })

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

    def to_anthropic_messages(self) -> Tuple[str, List[Dict[str, Any]]]:
        """Convert payload to Anthropic Claude 3.5 Sonnet Messages API format."""
        content: List[Dict[str, Any]] = []

        if self.som_image_base64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self.som_image_mime,
                    "data": self.som_image_base64,
                },
            })

        content.append({
            "type": "text",
            "text": self.user_text_prompt,
        })

        return self.system_prompt, [{"role": "user", "content": content}]


class MultimodalContextBuilder:
    """Assembles rich multimodal reasoning contexts combining visual SOM, UIA trees, and compacted history."""

    def __init__(
        self,
        som_generator: Optional[SetOfMarksGenerator] = None,
        compactor: Optional[ContextCompactor] = None,
        max_image_dimension: int = 1600,
        image_quality: int = 85,
        max_uia_elements: int = 50,
        max_history_chars: int = 3000,
    ) -> None:
        self.som_generator = som_generator or SetOfMarksGenerator()
        self.compactor = compactor or ContextCompactor(max_characters=max_history_chars)
        self.max_image_dimension = max_image_dimension
        self.image_quality = image_quality
        self.max_uia_elements = max_uia_elements

    def build_context(
        self,
        objective: Union[str, StructuredObjective],
        observation: CurrentStateObservation,
        step_history: Optional[List[CognitiveStepResult]] = None,
        step_index: int = 0,
        failure_feedback: Optional[str] = None,
        trajectory_memory: Optional[TrajectoryMemory] = None,
        raw_image: Optional[Image.Image] = None,
    ) -> MultimodalContextPayload:
        """Assemble the complete multimodal context payload with SOM annotations and history compaction."""
        start_ns = time.monotonic_ns()

        # 1. Resolve Goal & Subgoals
        goal_text = ""
        subtasks: List[str] = []
        if isinstance(objective, StructuredObjective):
            goal_text = objective.user_goal or objective.raw_prompt
            subtasks = objective.subtasks or getattr(objective, "subgoals", [])
        elif hasattr(objective, "user_goal"):
            goal_text = getattr(objective, "user_goal", "")
            subtasks = getattr(objective, "subtasks", []) or getattr(objective, "subgoals", [])
        else:
            goal_text = str(objective)

        subgoals_text = ""
        if subtasks:
            subgoals_text = "\n### Subgoal Progress:\n" + "\n".join(
                f"- [{'x' if idx < step_index else ' '}] {sg}"
                for idx, sg in enumerate(subtasks)
            )

        # 2. Compact History & Check Trajectory Loops
        compacted_hist = ""
        if step_history:
            comp_res = self.compactor.compact_history(step_history, current_step=step_index)
            compacted_hist = comp_res.summary_text if hasattr(comp_res, "summary_text") else str(comp_res)

        loop_warning = ""
        if trajectory_memory:
            is_loop, loop_msg = trajectory_memory.is_looping_detected()
            if is_loop and loop_msg:
                guidance = trajectory_memory.get_recovery_guidance() or "Switch to an alternate strategy immediately!"
                loop_warning = f"\n[TRAJECTORY WARNING]: {loop_msg}. Guidance: {guidance}\n"

        # 3. Active Window Context
        win_title = observation.active_window_title or "Desktop / Background"
        win_class = observation.active_window_class or "Unknown"
        win_hwnd = observation.active_window_hwnd or 0
        active_win_text = (
            f"### Foreground Window State:\n"
            f"- Title: \"{win_title}\"\n"
            f"- Class: {win_class} (HWND: {win_hwnd})\n"
            f"- Target App Exists: {observation.target_app_exists}\n"
        )

        # 4. Generate Set-of-Marks (SOM) Visual Overlay
        som_res: Optional[SOMResult] = None
        som_b64: Optional[str] = None
        som_summary = ""

        # Harvest UIA elements from observation fields
        uia_elems = (
            getattr(observation, "interactive_elements", None)
            or observation.raw_evidence.get("interactive_elements")
            or observation.raw_evidence.get("uia_elements")
            or (observation.desktop_observation.interactive_elements if observation.desktop_observation else None)
            or []
        )

        # Acquire PIL Image from input or observation
        pil_img = raw_image
        if pil_img is None and getattr(observation, "screenshot", None) is not None:
            raw_s = observation.screenshot
            if isinstance(raw_s, Image.Image):
                pil_img = raw_s
            elif isinstance(raw_s, (bytes, bytearray)):
                try:
                    pil_img = Image.open(io.BytesIO(raw_s))
                except Exception as e:
                    logger.debug("Failed to decode observation.screenshot into PIL: %s", e)

        if pil_img is not None:
            raw_ocr = (
                observation.raw_evidence.get("ocr_tokens")
                or getattr(observation, "ocr_tokens", [])
                or (observation.desktop_observation.ocr_tokens if observation.desktop_observation else None)
                or []
            )

            # If OCR tokens are strings or dicts, normalize to token dicts
            ocr_dicts = []
            for tok in raw_ocr:
                if isinstance(tok, dict):
                    ocr_dicts.append(tok)
                elif isinstance(tok, str):
                    ocr_dicts.append({"word": tok, "left": 0, "top": 0, "width": 0, "height": 0})

            # Active window bounding box for clipping
            win_bounds: Optional[Tuple[int, int, int, int]] = None
            if observation.active_window_hwnd:
                for w in observation.visible_windows:
                    if w.get("hwnd") == observation.active_window_hwnd and "bounds" in w:
                        b = w["bounds"]
                        win_bounds = (b.get("left", 0), b.get("top", 0), b.get("right", 1920), b.get("bottom", 1080))
                        break

            som_res = self.som_generator.generate_som(
                image=pil_img,
                uia_elements=uia_elems,
                ocr_tokens=ocr_dicts,
                active_window_bounds=win_bounds,
            )
            som_summary = som_res.to_summary_text(max_marks=self.max_uia_elements)

            # Compress and encode SOM annotated image
            som_b64 = self._encode_image_optimized(som_res.annotated_image)

        # 5. Accessibility UI Tree Summary
        uia_text = self._build_uia_tree_text(observation, uia_elems=uia_elems)

        # 6. Assemble Full User Text Prompt
        sections: List[str] = [
            f"# USER OBJECTIVE\n{goal_text.strip()}",
            subgoals_text,
            f"# CURRENT ENVIRONMENT STATE\n{active_win_text}",
        ]

        if som_summary:
            sections.append(f"# DETECTED VISUAL MARKS (Set-of-Marks)\n{som_summary}")

        if uia_text:
            sections.append(f"# ACCESSIBILITY UI CONTROLS\n{uia_text}")

        if compacted_hist:
            sections.append(f"# EXECUTION TRAJECTORY HISTORY\n{compacted_hist}")

        if loop_warning:
            sections.append(loop_warning)

        if failure_feedback:
            sections.append(f"# LAST ACTION FAILURE DIAGNOSTICS\n{failure_feedback}")

        sections.append(
            "# REQUIRED ACTION\n"
            f"Step Index: {step_index}\n"
            "Inspect the screenshot, Set-of-Marks tags, and UI state. "
            "Output your next single atomic action strictly as a JSON object."
        )

        user_prompt = "\n\n".join(s for s in sections if s.strip())

        duration_ms = (time.monotonic_ns() - start_ns) / 1_000_000.0
        est_tokens = len(user_prompt) // 4 + (1000 if som_b64 else 0)

        return MultimodalContextPayload(
            system_prompt=ASTRA6_SYSTEM_PROMPT,
            user_text_prompt=user_prompt,
            som_image_base64=som_b64,
            som_image_mime="image/jpeg",
            som_result=som_res,
            compacted_history=compacted_hist,
            uia_tree_summary=uia_text,
            active_window_summary=active_win_text,
            diagnostic_feedback=failure_feedback or "",
            estimated_tokens=est_tokens,
            build_duration_ms=duration_ms,
        )

    def _build_uia_tree_text(
        self,
        observation: CurrentStateObservation,
        uia_elems: Optional[List[Any]] = None,
    ) -> str:
        """Serialize UIA elements into compact hierarchical text lines."""
        elems = uia_elems if uia_elems is not None else (
            getattr(observation, "interactive_elements", None)
            or observation.raw_evidence.get("interactive_elements")
            or observation.raw_evidence.get("uia_elements")
            or []
        )
        if not elems:
            return "No accessibility elements reported in current observation."

        lines = []
        for el in elems[: self.max_uia_elements]:
            name = getattr(el, "name", "") or getattr(el, "control_name", "") or "Unnamed"
            role = getattr(el, "control_type", "") or getattr(el, "role", "") or "Control"
            auto_id = getattr(el, "automation_id", "") or ""
            id_str = f" id='{auto_id}'" if auto_id else ""
            lines.append(f"- <{role}{id_str}> \"{name}\"")

        if len(elems) > self.max_uia_elements:
            lines.append(f"... and {len(elems) - self.max_uia_elements} additional controls.")

        return "\n".join(lines)

    def _encode_image_optimized(self, img: Image.Image) -> str:
        """Downsample and compress image to high-efficiency JPEG base64."""
        w, h = img.size
        # Resize if exceeding max dimension
        if max(w, h) > self.max_image_dimension:
            scale = self.max_image_dimension / float(max(w, h))
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Convert to RGB (JPEG requires RGB)
        if img.mode in ("RGBA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                rgb_img.paste(img, mask=img.split()[3])
            else:
                rgb_img.paste(img)
            img = rgb_img

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.image_quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
