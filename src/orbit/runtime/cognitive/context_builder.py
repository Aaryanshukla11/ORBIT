"""Multimodal Agent Reasoning Context Builder (Step 4).

Converts live DesktopObservation (Win32 windows, UIA tree, OCR tokens, Screenshot),
StructuredObjective, step history, and task context into a compact, token-efficient
multimodal prompt envelope for Local and Cloud AI models.

SECURITY INVARIANT:
Zero secrets or credentials are ever emitted, logged, or serialized.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple, Union

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionResult,
)
from orbit.runtime.cognitive.models import (
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.models.capabilities import ModelCapabilityProfile
from orbit.runtime.models.models import (
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelRole,
)
from orbit.runtime.perception.models import DesktopObservation

DECISION_SYSTEM_PROMPT = """You are ORBIT's AI Decision Brain, an autonomous computer agent operating a Windows desktop.
Given the User Goal, the Structured Objective, the Current Screen/Window State, and the Action History, decide the SINGLE NEXT ACTION.

SAFETY INVARIANT:
Do NOT generate physical screen coordinates (x, y, bbox, screen_x, screen_y). 
ORBIT's runtime target locator resolves physical coordinates dynamically from UI elements and OCR evidence.
You decide WHAT to interact with semantically (name, role, context, text_hint).

Output ONLY a single valid JSON object strictly matching this schema:
{
  "decision_summary": "<concise assessment of desktop state vs goal>",
  "goal_progress": "<IN_PROGRESS | COMPLETED | UNACHIEVABLE>",
  "confidence": <float between 0.0 and 1.0>,
  "evidence_used": [
    "<concrete observation evidence e.g. 'OCR: Submit', 'UIA: button named Save', 'Window: Notepad'>"
  ],
  "expected_state_transition": "<expected observable state delta after this action>",
  "reason_summary": "<why this action is required next>",
  "next_action": {
    "action_type": "<LAUNCH_APPLICATION | FOCUS_WINDOW | CLICK | DOUBLE_CLICK | RIGHT_CLICK | TYPE_TEXT | SEND_HOTKEY | SCROLL | DRAW_STROKES | WAIT | COMPLETE_GOAL | ABORT_TASK>",
    "target": {
      "name": "<logical label, button text, window title, or text hint>",
      "role": "<button | edit | window | canvas | tab | menu | link | custom>",
      "context": "<app or container name e.g. Chrome, Notepad, File Explorer>",
      "text_hint": "<optional text to find on screen via OCR>"
    },
    "parameters": {
      "<action-specific parameters e.g. application_name for LAUNCH_APPLICATION, text for TYPE_TEXT, keys for SEND_HOTKEY, shape for DRAW_STROKES>"
    },
    "expected_effect": "<observable effect e.g. 'File dialog opens', 'Text typed into search box'>"
  }
}

Rules:
1. If the goal is fully achieved according to the live observation, set "goal_progress": "COMPLETED", "next_action.action_type": "COMPLETE_GOAL".
2. If the application is not running or visible, launch it using LAUNCH_APPLICATION.
3. If the application is open but in the background, bring it forward using FOCUS_WINDOW.
4. Output plain JSON. Do NOT include markdown fences (```json).
"""


class AgentReasoningContextBuilder:
    """Constructs prompt envelopes and image attachments from DesktopObservation."""

    @staticmethod
    def build_prompt_text(
        objective: StructuredObjective,
        observation: Union[DesktopObservation, CurrentStateObservation],
        step_history: Optional[List[CognitiveStepResult]] = None,
        step_index: int = 0,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a compact, token-efficient text description of current state."""
        history = step_history or []
        lines: List[str] = []

        # 1. User Goal & Objective
        lines.append("=== USER GOAL ===")
        lines.append(f"Prompt: {objective.raw_prompt}")
        lines.append(f"Goal: {objective.user_goal}")
        lines.append(f"End Condition: {objective.end_condition}")
        if objective.target_entities:
            lines.append(f"Target Entities: {', '.join(objective.target_entities)}")

        # 2. Extract Desktop State
        lines.append("\n=== CURRENT DESKTOP STATE ===")
        active_window_title = "Unknown"
        active_window_class = "Unknown"
        visible_windows: List[str] = []
        ocr_tokens: List[str] = []
        ui_elements: List[str] = []
        visual_summary = ""

        if isinstance(observation, DesktopObservation):
            # Windows
            if observation.foreground_window:
                active_window_title = observation.foreground_window.title or "Unknown"
                active_window_class = observation.foreground_window.window_class or "Unknown"
            elif hasattr(observation, "windows") and observation.windows:
                active_window_title = getattr(observation.windows, "foreground_title", "Unknown")
                active_window_class = getattr(observation.windows, "foreground_class", "Unknown")

            if observation.visible_windows:
                visible_windows = [w.title for w in observation.visible_windows if getattr(w, "title", None)][:10]
            elif hasattr(observation, "windows") and observation.windows:
                visible_windows = [
                    w.title for w in getattr(observation.windows, "visible_windows", []) if getattr(w, "title", None)
                ][:10]

            # OCR
            if observation.ocr_tokens:
                ocr_tokens = [t.text for t in observation.ocr_tokens if getattr(t, "text", "").strip()][:30]
            elif hasattr(observation, "ocr") and observation.ocr and hasattr(observation.ocr, "tokens"):
                ocr_tokens = [t.text for t in observation.ocr.tokens if getattr(t, "text", "").strip()][:30]

            # UI Elements & Fusion
            if observation.perceived_elements:
                for elem in observation.perceived_elements[:15]:
                    role = elem.role.value if hasattr(elem.role, "value") else str(elem.role)
                    ui_elements.append(f"[{role}] '{elem.name}'")
            elif hasattr(observation, "fused_elements") and observation.fused_elements:
                for elem in observation.fused_elements[:15]:
                    role = elem.role.value if hasattr(elem.role, "value") else str(elem.role)
                    ui_elements.append(f"[{role}] '{elem.name}'")
            elif observation.uia_elements:
                for elem in observation.uia_elements[:15]:
                    ui_elements.append(f"[{elem.control_type}] '{elem.name}'")
            elif hasattr(observation, "uia") and observation.uia and hasattr(observation.uia, "elements"):
                for elem in observation.uia.elements[:15]:
                    ui_elements.append(f"[{elem.control_type}] '{elem.name}'")

            visual_summary = observation.desktop_summary or getattr(observation, "visual_summary", "")

        elif isinstance(observation, CurrentStateObservation):
            active_window_title = observation.active_window_title
            active_window_class = observation.active_window_class
            visible_windows = [
                w.get("title", "") if isinstance(w, dict) else getattr(w, "title", "")
                for w in observation.visible_windows
                if (w.get("title", "") if isinstance(w, dict) else getattr(w, "title", ""))
            ][:10]
            ocr_tokens = observation.ocr_tokens[:30]
            if observation.desktop_observation and observation.desktop_observation.perceived_elements:
                for elem in observation.desktop_observation.perceived_elements[:15]:
                    role = elem.role.value if hasattr(elem.role, "value") else str(elem.role)
                    ui_elements.append(f"[{role}] '{elem.name}'")
            visual_summary = observation.screen_summary or ""

        lines.append(f"Active Window: '{active_window_title}' (Class: {active_window_class})")
        if visible_windows:
            lines.append(f"Visible Windows: {', '.join(visible_windows)}")
        if ui_elements:
            lines.append("Interactive UI Elements:")
            for elem_str in ui_elements:
                lines.append(f"  - {elem_str}")
        if ocr_tokens:
            lines.append(f"OCR Tokens: {' | '.join(ocr_tokens)}")
        if visual_summary:
            lines.append(f"Visual Summary: {visual_summary}")

        # 3. Recent Action History
        lines.append(f"\n=== EXECUTION CONTEXT (Step {step_index}) ===")
        if history:
            last_step = history[-1]
            act = last_step.action_dispatched
            if act:
                lines.append(f"Recent Action: {act.action_type.value} on '{act.target.name if act.target else 'N/A'}'")
            lines.append(f"Recent Verified: {last_step.outcome_verified}")
            if last_step.execution_result and last_step.execution_result.error_message:
                lines.append(f"Recent Error: {last_step.execution_result.error_message}")
        else:
            lines.append("Recent Action: Initial step (No actions dispatched yet)")

        lines.append("\nDecide the next single action to make progress toward the user goal.")
        return "\n".join(lines)

    @staticmethod
    def extract_screenshot_base64(
        observation: Union[DesktopObservation, CurrentStateObservation],
    ) -> Optional[str]:
        """Extract base64-encoded screenshot from observation if present."""
        ss = None
        if isinstance(observation, DesktopObservation):
            ss = observation.screenshot_reference or getattr(observation, "screenshot", None)
        elif isinstance(observation, CurrentStateObservation):
            if observation.desktop_observation:
                ss = observation.desktop_observation.screenshot_reference or getattr(observation.desktop_observation, "screenshot", None)

        if ss is not None:
            if getattr(ss, "image_base64", None):
                return ss.image_base64
            img_bytes = getattr(ss, "raw_bytes", None) or getattr(ss, "image_bytes", None)
            if img_bytes:
                return base64.b64encode(img_bytes).decode("utf-8")

        return None

    @classmethod
    def build_chat_request(
        cls,
        objective: StructuredObjective,
        observation: Union[DesktopObservation, CurrentStateObservation],
        model_profile: ModelCapabilityProfile,
        step_history: Optional[List[CognitiveStepResult]] = None,
        step_index: int = 0,
        task_context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
    ) -> Tuple[ModelChatRequest, bool]:
        """Build ModelChatRequest and indicate whether visual frame was attached.

        Returns:
            (ModelChatRequest, attached_vision: bool)
        """
        prompt_text = cls.build_prompt_text(
            objective=objective,
            observation=observation,
            step_history=step_history,
            step_index=step_index,
            task_context=task_context,
        )

        attached_vision = False
        images: Optional[List[str]] = None

        if model_profile.supports_vision:
            b64_img = cls.extract_screenshot_base64(observation)
            if b64_img:
                images = [b64_img]
                attached_vision = True

        user_message = ModelChatMessage(
            role=ModelRole.USER.value,
            content=prompt_text,
            images=images,
        )

        system_message = ModelChatMessage(
            role=ModelRole.SYSTEM.value,
            content=DECISION_SYSTEM_PROMPT,
        )

        request = ModelChatRequest(
            messages=[system_message, user_message],
            temperature=temperature,
        )
        return request, attached_vision
