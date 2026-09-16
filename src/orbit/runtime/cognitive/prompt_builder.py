"""Multimodal Prompt Builder for Model-First Decision Loop (Phase 2C).

Assembles structured, token-efficient multimodal payloads delivering screenshot frames,
compact WorldState summaries, top perceived UI controls, task state, and explicit
diagnostic failure feedback into the multimodal model.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any, Dict, List, Optional
from PIL import Image

from orbit.runtime.cognitive.model_proposal import ModelActionType

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are ORBIT, an authoritative multimodal autonomous computer-use agent operating a Windows desktop.

You directly perceive the live desktop through screenshots, accessible UI elements, and OCR tokens, and propose the exact NEXT action to progress towards the user's goal.

Output your next action STRICTLY as a JSON object matching this schema:
{
  "action_type": "CLICK" | "DOUBLE_CLICK" | "RIGHT_CLICK" | "TYPE" | "HOTKEY" | "LAUNCH" | "SAVE_FILE" | "WAIT" | "SCROLL" | "DRAG" | "DRAW" | "COMPLETE" | "FAIL",
  "target_selector": {
    "role": "button" | "menu_item" | "window" | "text_field" | "canvas" | null,
    "name": "Accessible label or target name" | null,
    "bounds": [ymin, xmin, ymax, xmax] | null,
    "selector": "Identifier" | null,
    "ocr_text": "Text in UI" | null
  },
  "parameters": {
    "text": "text to type",
    "key_combination": "ctrl+s",
    "application_name": "app to launch",
    "filename": "save path or name",
    "format": "png",
    "shape": "circle"
  },
  "expected_outcome": "Precise description of the expected visual or OS state change",
  "confidence": 1.0,
  "diagnostic_reasoning": "Short 1-sentence diagnostic rationale"
}

RULES:
1. ONLY propose canonical action_type values.
2. DO NOT include fake or hallucinated UI elements.
3. If an action previously failed, inspect the failure diagnostics and switch strategies.
4. When saving a file, always specify filename and format in parameters.
5. Propose "COMPLETE" only when all aspects of the user's goal are fully achieved and verified on screen/disk.
"""


class MultimodalPromptBuilder:
    """Constructs token-efficient multimodal payloads for the decision model."""

    def __init__(self, max_perceived_elements: int = 40) -> None:
        self.max_perceived_elements = max_perceived_elements

    def build_prompt(
        self,
        user_goal: str,
        current_observation: Any,
        task_requirements: Optional[List[str]] = None,
        action_history: Optional[List[Dict[str, Any]]] = None,
        failure_feedback: Optional[str] = None,
        image_data: Optional[bytes | Image.Image] = None,
    ) -> Dict[str, Any]:
        """Assemble the complete multimodal model payload."""
        text_sections: List[str] = []

        # 1. Goal & Requirements
        text_sections.append(f"## USER GOAL\n{user_goal.strip()}\n")
        if task_requirements:
            req_text = "\n".join(f"- [ ] {r}" for r in task_requirements)
            text_sections.append(f"## MANDATORY REQUIREMENTS\n{req_text}\n")

        # 2. Desktop State Summary & Layered WorldState Context
        world_state = getattr(current_observation, "world_state", None)
        if world_state and hasattr(world_state, "compact_context"):
            cc = world_state.compact_context
            active_title = cc.foreground_window_title or getattr(current_observation, "active_window_title", "Unknown")
            active_proc = cc.active_process_name or getattr(current_observation, "active_process_name", "Unknown")
            active_hwnd = getattr(current_observation, "active_window_hwnd", None)
            text_sections.append(
                f"## CURRENT DESKTOP STATE (WorldState Obs ID: {world_state.observation_id})\n"
                f"- Foreground Window: \"{active_title}\"\n"
                f"- Active Process: {active_proc} (HWND: {active_hwnd})\n"
                f"- Resolution: {cc.screen_resolution}\n"
                f"- Focus App Context: {cc.app_context}\n"
            )
            if cc.interactive_summary:
                perceived = [
                    f"- [{elem.get('role', 'control')}] \"{elem.get('name', '')}\" at {elem.get('bounds', [])}"
                    for elem in cc.interactive_summary[:self.max_perceived_elements]
                ]
            else:
                perceived = []
        else:
            active_title = getattr(current_observation, "active_window_title", "Unknown")
            active_proc = getattr(current_observation, "active_process_name", "Unknown")
            active_hwnd = getattr(current_observation, "active_window_hwnd", None)
            text_sections.append(
                f"## CURRENT DESKTOP STATE\n"
                f"- Foreground Window: \"{active_title}\"\n"
                f"- Active Process: {active_proc} (HWND: {active_hwnd})\n"
            )

            # 3. Top Perceived Elements (UIA / OCR)
            perceived = []
            d_obs = getattr(current_observation, "desktop_observation", None)
            if d_obs:
                raw_elements = (getattr(d_obs, "perceived_elements", None) or []) + (getattr(d_obs, "uia_elements", None) or [])
                for elem in raw_elements[:self.max_perceived_elements]:
                    name = getattr(elem, "name", "")
                    role = getattr(elem, "role", getattr(elem, "control_type", ""))
                    bounds = getattr(elem, "bounds", getattr(elem, "bounding_box", None))
                    if name or role:
                        perceived.append(f"- [{role}] \"{name}\" at {bounds}")

        if perceived:
            text_sections.append(f"## VISIBLE UI CONTROLS (Top {len(perceived)})\n" + "\n".join(perceived) + "\n")

        # 4. Action History
        if action_history:
            hist_lines = []
            for i, h in enumerate(action_history[-5:], 1):
                act = h.get("action", {})
                verif = h.get("verified", False)
                reason = h.get("reason", "")
                status_str = "VERIFIED SUCCESS" if verif else f"UNVERIFIED / FAILED ({reason})"
                hist_lines.append(f"{i}. Action: {act.get('action_type', 'UNKNOWN')} -> {status_str}")
            text_sections.append("## RECENT ACTION HISTORY\n" + "\n".join(hist_lines) + "\n")

        # 5. Explicit Failure Diagnostic Feedback
        if failure_feedback:
            text_sections.append(
                f"## ⚠️ PREVIOUS STEP FAILURE DIAGNOSTIC\n"
                f"{failure_feedback.strip()}\n"
                f"Your previous action did not produce the expected outcome. Reason over this failure and choose an alternative path.\n"
            )

        # 6. Encode Image if available
        encoded_image = None
        if image_data:
            if isinstance(image_data, Image.Image):
                buf = io.BytesIO()
                image_data.save(buf, format="PNG")
                encoded_image = base64.b64encode(buf.getvalue()).decode("utf-8")
            elif isinstance(image_data, bytes):
                encoded_image = base64.b64encode(image_data).decode("utf-8")
        elif hasattr(current_observation, "screenshot") and current_observation.screenshot:
            sc = current_observation.screenshot
            if isinstance(sc, Image.Image):
                buf = io.BytesIO()
                sc.save(buf, format="PNG")
                encoded_image = base64.b64encode(buf.getvalue()).decode("utf-8")
            elif isinstance(sc, bytes):
                encoded_image = base64.b64encode(sc).decode("utf-8")

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": "\n".join(text_sections),
            "image_base64": encoded_image,
            "mime_type": "image/png" if encoded_image else None,
        }
