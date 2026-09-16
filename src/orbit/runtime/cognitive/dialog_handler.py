"""Modal Dialog Detection, Classification, and Trap Escape Engine (Phase 2G.2).

Detects Windows OS modal dialogs (#32770, DirectUIHWND, UAC, Save As, Overwrite collisions,
Unsaved Changes warnings), classifies their intent, and synthesizes safe escape/resolution primitives.
"""

from __future__ import annotations

from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.models import CurrentStateObservation

logger = logging.getLogger(__name__)


class DialogIntent(str, Enum):
    """Semantic intent classification of a detected Windows dialog."""

    SAVE_AS_PROMPT = "SAVE_AS_PROMPT"           # Standard file save dialog
    FILE_COLLISION = "FILE_COLLISION"           # File already exists / replace warning
    CONFIRM_DISCARD = "CONFIRM_DISCARD"         # Unsaved changes on app close (Save / Don't Save / Cancel)
    ERROR_ALERT = "ERROR_ALERT"                 # Application or OS error message box
    INFO_NOTIFICATION = "INFO_NOTIFICATION"     # Informational popup / warning
    SECURITY_PROMPT = "SECURITY_PROMPT"         # Elevation / Security confirmation
    GENERIC_MODAL = "GENERIC_MODAL"             # Unclassified modal window


class DialogResolutionStrategy(str, Enum):
    """Action strategy to resolve or escape a modal dialog."""

    CONFIRM_REPLACE = "CONFIRM_REPLACE"         # Confirm overwrite (Yes / Replace / Alt+Y)
    DISCARD_AND_CLOSE = "DISCARD_AND_CLOSE"     # Discard unsaved changes (Don't Save / Alt+N)
    DISMISS_ALERT = "DISMISS_ALERT"             # Acknowledge error/info (OK / Enter)
    CANCEL_DIALOG = "CANCEL_DIALOG"             # Cancel and return to app (Cancel / Escape)
    RENAME_AND_SAVE = "RENAME_AND_SAVE"         # Input alternative filename and proceed


class DetectedDialog(BaseModel):
    """Structured inspection model for an active modal or pop-up dialog."""

    dialog_id: str = Field(default_factory=lambda: f"dlg_{uuid4().hex[:8]}")
    hwnd: int = Field(..., description="Win32 Window Handle")
    title: str = Field(default="", description="Dialog caption or title")
    class_name: str = Field(default="", description="Win32 class name e.g. #32770")
    intent: DialogIntent = Field(default=DialogIntent.GENERIC_MODAL)
    is_foreground: bool = Field(default=False)
    is_modal: bool = Field(default=True)
    interactive_buttons: List[str] = Field(default_factory=list, description="Extracted button labels")
    message_text: str = Field(default="", description="Dialog body or alert text extracted via OCR/UIA")
    parent_hwnd: Optional[int] = Field(default=None)


class ModalDialogDetector:
    """Detects and categorizes active Win32 modal dialogs from observation."""

    DIALOG_CLASSES: Set[str] = {
        "#32770",                   # Standard Win32 Dialog
        "DirectUIHWND",             # Modern Windows Shell / Explorer Dialog
        "OperationStatusWindow",    # File copy / delete / status dialog
        "Windows.UI.Core.CoreWindow", # UWP / WinUI flyouts
        "TaskDialog",               # Vista+ TaskDialogs
    }

    COLLISION_KEYWORDS = [
        "already exists",
        "do you want to replace",
        "confirm save as",
        "replace it",
        "overwrite",
    ]

    DISCARD_KEYWORDS = [
        "save changes",
        "do you want to save",
        "unsaved",
        "don't save",
        "save your work",
    ]

    ERROR_KEYWORDS = [
        "error",
        "failed",
        "access denied",
        "not found",
        "cannot open",
        "invalid path",
        "unhandled exception",
    ]

    SAVE_AS_KEYWORDS = [
        "save as",
        "save a copy",
        "browse for folder",
    ]

    def detect_dialog(self, observation: CurrentStateObservation) -> Optional[DetectedDialog]:
        """Inspect observation to identify any active foreground or child modal dialog."""
        # 1. Check active foreground window first
        fg_hwnd = observation.active_window_hwnd or 0
        fg_title = (observation.active_window_title or "").strip()
        fg_class = (observation.active_window_class or "").strip()

        # Check foreground against dialog patterns
        if self._is_dialog_window(fg_title, fg_class):
            return self._build_detected_dialog(
                hwnd=fg_hwnd,
                title=fg_title,
                class_name=fg_class,
                is_foreground=True,
                observation=observation,
            )

        # 2. Check visible top-level windows for modal dialogs
        for win in observation.visible_windows:
            w_hwnd = win.get("hwnd", 0) if isinstance(win, dict) else getattr(win, "hwnd", 0)
            w_title = (win.get("title", "") if isinstance(win, dict) else getattr(win, "title", "")).strip()
            w_class = (win.get("class_name", "") if isinstance(win, dict) else getattr(win, "class_name", "")).strip()

            if self._is_dialog_window(w_title, w_class):
                return self._build_detected_dialog(
                    hwnd=w_hwnd,
                    title=w_title,
                    class_name=w_class,
                    is_foreground=(w_hwnd == fg_hwnd),
                    observation=observation,
                )

        return None

    def _is_dialog_window(self, title: str, class_name: str) -> bool:
        """Evaluate if window matches dialog heuristics."""
        if not title and not class_name:
            return False

        if class_name in self.DIALOG_CLASSES:
            return True

        title_lower = title.lower()
        all_kw = (
            self.COLLISION_KEYWORDS
            + self.DISCARD_KEYWORDS
            + self.ERROR_KEYWORDS
            + self.SAVE_AS_KEYWORDS
            + ["confirm", "warning", "alert", "notice"]
        )
        return any(kw in title_lower for kw in all_kw)

    def _build_detected_dialog(
        self,
        hwnd: int,
        title: str,
        class_name: str,
        is_foreground: bool,
        observation: CurrentStateObservation,
    ) -> DetectedDialog:
        """Classify intent and extract buttons for detected dialog."""
        title_lower = title.lower()
        ocr_text = " ".join(observation.ocr_tokens).lower()
        combined_text = f"{title_lower} {ocr_text}"

        intent = DialogIntent.GENERIC_MODAL
        buttons: List[str] = []

        # 1. Collision / Overwrite
        if any(kw in combined_text for kw in self.COLLISION_KEYWORDS):
            intent = DialogIntent.FILE_COLLISION
            buttons = ["Yes", "No", "Cancel"]

        # 2. Confirm Discard / Save Changes
        elif any(kw in combined_text for kw in self.DISCARD_KEYWORDS):
            intent = DialogIntent.CONFIRM_DISCARD
            buttons = ["Save", "Don't Save", "Cancel"]

        # 3. Save As Dialog
        elif any(kw in combined_text for kw in self.SAVE_AS_KEYWORDS) and "replace" not in combined_text:
            intent = DialogIntent.SAVE_AS_PROMPT
            buttons = ["Save", "Cancel"]

        # 4. Error Alert
        elif any(kw in combined_text for kw in self.ERROR_KEYWORDS):
            intent = DialogIntent.ERROR_ALERT
            buttons = ["OK", "Cancel"]

        # 5. Generic Info
        elif any(kw in combined_text for kw in ["warning", "information", "notice"]):
            intent = DialogIntent.INFO_NOTIFICATION
            buttons = ["OK"]

        # Extract buttons from UIA or OCR if present
        if observation.desktop_observation and observation.desktop_observation.perceived_elements:
            extracted_btns = [
                elem.name
                for elem in observation.desktop_observation.perceived_elements
                if "button" in str(elem.role).lower() and elem.name
            ]
            if extracted_btns:
                buttons = extracted_btns

        return DetectedDialog(
            hwnd=hwnd,
            title=title,
            class_name=class_name,
            intent=intent,
            is_foreground=is_foreground,
            is_modal=True,
            interactive_buttons=buttons,
            message_text=combined_text[:200],
        )


class DialogTrapHandler:
    """Synthesizes targeted canonical primitives to resolve or escape modal dialogs."""

    def __init__(self, detector: Optional[ModalDialogDetector] = None) -> None:
        self.detector = detector or ModalDialogDetector()

    def resolve_dialog(
        self,
        dialog: DetectedDialog,
        preferred_strategy: Optional[DialogResolutionStrategy] = None,
        fallback_filename: Optional[str] = None,
    ) -> AbstractAction:
        """Construct the canonical AbstractAction to execute the resolution strategy."""
        strat = preferred_strategy or self._determine_default_strategy(dialog)

        logger.info(
            "Resolving DetectedDialog '%s' (Intent: %s) with strategy: %s",
            dialog.title,
            dialog.intent.value,
            strat.value,
        )

        # 1. Overwrite Confirmation (e.g. "already exists -> Replace?")
        if strat == DialogResolutionStrategy.CONFIRM_REPLACE:
            # Prefer button click if target is known, else hotkey Alt+Y / Enter
            return AbstractAction(
                action_type=AbstractActionType.CLICK,
                target=SemanticTarget(name="Yes", role="button", context=dialog.title),
                parameters={"hotkey_fallback": "Alt+Y"},
                expected_effect=f"Confirmed file overwrite in dialog '{dialog.title}'",
            )

        # 2. Discard and Close (e.g. "Do you want to save changes? -> Don't Save")
        elif strat == DialogResolutionStrategy.DISCARD_AND_CLOSE:
            return AbstractAction(
                action_type=AbstractActionType.CLICK,
                target=SemanticTarget(name="Don't Save", role="button", context=dialog.title),
                parameters={"hotkey_fallback": "Alt+N"},
                expected_effect=f"Discarded unsaved changes and closed dialog '{dialog.title}'",
            )

        # 3. Dismiss Error or Info Alert (OK / Enter)
        elif strat == DialogResolutionStrategy.DISMISS_ALERT:
            return AbstractAction(
                action_type=AbstractActionType.SEND_HOTKEY,
                target=SemanticTarget(name=dialog.title, role="window"),
                parameters={"hotkey": "Enter"},
                expected_effect=f"Dismissed alert dialog '{dialog.title}' with Enter",
            )

        # 4. Cancel / Escape
        elif strat == DialogResolutionStrategy.CANCEL_DIALOG:
            return AbstractAction(
                action_type=AbstractActionType.SEND_HOTKEY,
                target=SemanticTarget(name=dialog.title, role="window"),
                parameters={"hotkey": "Escape"},
                expected_effect=f"Cancelled modal dialog '{dialog.title}' via Escape",
            )

        # 5. Rename and Save
        elif strat == DialogResolutionStrategy.RENAME_AND_SAVE:
            fn = fallback_filename or f"file_{uuid4().hex[:6]}.txt"
            return AbstractAction(
                action_type=AbstractActionType.TYPE_TEXT,
                target=SemanticTarget(name="File name:", role="edit", context=dialog.title),
                parameters={"text": f"{fn}\n"},
                expected_effect=f"Entered non-colliding filename '{fn}' into dialog",
            )

        # Default fallback: Escape
        return AbstractAction(
            action_type=AbstractActionType.SEND_HOTKEY,
            parameters={"hotkey": "Escape"},
            expected_effect=f"Escaped dialog '{dialog.title}'",
        )

    def _determine_default_strategy(self, dialog: DetectedDialog) -> DialogResolutionStrategy:
        """Select best resolution strategy based on dialog intent."""
        if dialog.intent == DialogIntent.FILE_COLLISION:
            return DialogResolutionStrategy.CONFIRM_REPLACE
        elif dialog.intent == DialogIntent.CONFIRM_DISCARD:
            return DialogResolutionStrategy.DISCARD_AND_CLOSE
        elif dialog.intent in (DialogIntent.ERROR_ALERT, DialogIntent.INFO_NOTIFICATION):
            return DialogResolutionStrategy.DISMISS_ALERT
        elif dialog.intent == DialogIntent.SAVE_AS_PROMPT:
            return DialogResolutionStrategy.CANCEL_DIALOG
        return DialogResolutionStrategy.CANCEL_DIALOG
