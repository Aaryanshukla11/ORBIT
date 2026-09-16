import base64
from typing import Any, Optional
import pytest
from PIL import Image

from orbit.runtime.cognitive.model_proposal import (
    ModelActionProposal,
    ModelActionType,
    TargetSelector,
)
from orbit.runtime.cognitive.prompt_builder import MultimodalPromptBuilder
from orbit.runtime.cognitive.primitive_validator import (
    ModelProposalValidator,
    ProposalValidationStage,
)
from orbit.runtime.cognitive.recovery import ModelRecoveryManager


class DummyObservation:
    def __init__(
        self,
        active_title: str = "Untitled - Paint",
        active_proc: str = "mspaint.exe",
        active_hwnd: int = 12345,
        screenshot: Optional[Image.Image] = None,
    ):
        self.active_window_title = active_title
        self.active_process_name = active_proc
        self.active_window_hwnd = active_hwnd
        self.screenshot = screenshot
        self.visible_windows = [
            {"title": "Untitled - Paint", "process_name": "mspaint.exe", "hwnd": 12345}
        ]


def test_01_declarative_model_proposal_schema():
    """Verify clean declarative schema without forced thought field."""
    proposal = ModelActionProposal(
        action_type=ModelActionType.CLICK,
        target_selector=TargetSelector(role="button", name="Save", bounds=[100, 200, 150, 250]),
        parameters={},
        expected_outcome="Save dialog appears",
        confidence=0.95,
        diagnostic_reasoning="Clicking save to open file dialog",
    )
    assert proposal.action_type == ModelActionType.CLICK
    assert proposal.target_selector is not None
    assert proposal.target_selector.name == "Save"
    assert proposal.expected_outcome == "Save dialog appears"
    # Verify no mandatory internal 'thought' field
    data = proposal.model_dump()
    assert "thought" not in data


def test_02_prompt_builder_structure():
    """Verify prompt builder formats goal, desktop state, and elements."""
    builder = MultimodalPromptBuilder()
    img = Image.new("RGB", (100, 100), color="white")
    obs = DummyObservation(screenshot=img)

    payload = builder.build_prompt(
        user_goal="Draw a red circle in Paint",
        current_observation=obs,
        task_requirements=["Launch Paint", "Draw circle", "Save file"],
        action_history=[
            {"action": {"action_type": "LAUNCH"}, "verified": True, "reason": "Paint launched"}
        ],
        failure_feedback=None,
    )

    assert "Draw a red circle in Paint" in payload["user_prompt"]
    assert "Untitled - Paint" in payload["user_prompt"]
    assert "Launch Paint" in payload["user_prompt"]
    assert "RECENT ACTION HISTORY" in payload["user_prompt"]
    assert payload["image_base64"] is not None
    assert payload["mime_type"] == "image/png"


def test_03_prompt_builder_injects_failure_diagnostics():
    """Verify prompt builder injects explicit failure diagnostic when present."""
    builder = MultimodalPromptBuilder()
    obs = DummyObservation()

    payload = builder.build_prompt(
        user_goal="Save image as test.png",
        current_observation=obs,
        failure_feedback="Save dialog did not appear after Ctrl+S hotkey",
    )

    assert "PREVIOUS STEP FAILURE DIAGNOSTIC" in payload["user_prompt"]
    assert "Save dialog did not appear after Ctrl+S hotkey" in payload["user_prompt"]


def test_04_validator_stage1_schema_valid():
    """Verify validator passes valid proposal."""
    validator = ModelProposalValidator()
    proposal_dict = {
        "action_type": "CLICK",
        "target_selector": {"role": "button", "name": "Save"},
        "parameters": {},
        "expected_outcome": "Save dialog opens",
    }
    result = validator.validate_proposal(proposal_dict)
    assert result.is_valid is True
    assert result.validated_proposal is not None
    assert result.validated_proposal.action_type == ModelActionType.CLICK


def test_05_validator_stage1_schema_missing_expected_outcome():
    """Verify validator rejects proposal without expected outcome."""
    validator = ModelProposalValidator()
    proposal_dict = {
        "action_type": "CLICK",
        "target_selector": {"role": "button", "name": "Save"},
        "parameters": {},
        "expected_outcome": "",
    }
    result = validator.validate_proposal(proposal_dict)
    assert result.is_valid is False
    assert result.failed_stage == ProposalValidationStage.SCHEMA
    assert result.failure_reason is not None
    assert "expected_outcome" in result.failure_reason.lower()


def test_06_validator_stage2_capability_invalid_action():
    """Verify validator rejects unsupported action types."""
    validator = ModelProposalValidator()
    proposal_dict = {
        "action_type": "HACK_DATABASE",
        "target_selector": None,
        "parameters": {},
        "expected_outcome": "Database hacked",
    }
    result = validator.validate_proposal(proposal_dict)
    assert result.is_valid is False
    assert result.failed_stage == ProposalValidationStage.SCHEMA or result.failed_stage == ProposalValidationStage.CAPABILITY


def test_07_validator_stage3_safety_restricted_keyword():
    """Verify safety gate rejects dangerous OS commands."""
    validator = ModelProposalValidator()
    proposal_dict = {
        "action_type": "TYPE",
        "target_selector": None,
        "parameters": {"text": "rmdir /s /q C:\\Windows"},
        "expected_outcome": "Directory deleted",
    }
    result = validator.validate_proposal(proposal_dict)
    assert result.is_valid is False
    assert result.failed_stage == ProposalValidationStage.SAFETY
    assert result.diagnostic_feedback is not None
    assert "security" in result.diagnostic_feedback.lower()


def test_08_validator_stage4_grounding_out_of_bounds():
    """Verify grounding gate rejects out-of-bounds bounding boxes."""
    validator = ModelProposalValidator()
    proposal_dict = {
        "action_type": "CLICK",
        "target_selector": {"role": "button", "bounds": [500, 200, 1500, 250]},  # ymax > 1000
        "parameters": {},
        "expected_outcome": "Button clicked",
    }
    result = validator.validate_proposal(proposal_dict)
    assert result.is_valid is False
    assert result.failed_stage == ProposalValidationStage.GROUNDING
    assert result.failure_reason is not None
    assert "bounding box" in result.failure_reason.lower() or "bounds" in result.failure_reason.lower()


def test_09_recovery_manager_formats_modal_diagnostic():
    """Verify recovery manager detects modals in visible windows and provides guidance."""
    recovery_mgr = ModelRecoveryManager()
    obs = DummyObservation()
    obs.visible_windows.append({"title": "Confirm Save As", "process_name": "mspaint.exe", "hwnd": 999})

    diagnostic = recovery_mgr.format_recovery_diagnostic(
        action_type="SAVE_FILE",
        expected_outcome="File saved to disk",
        verification_reason="File not found on disk",
        current_observation=obs,
        attempt=1,
    )

    assert "Failed Action: SAVE_FILE" in diagnostic
    assert "Confirm Save As" in diagnostic
    assert "Detected Modal Dialog" in diagnostic
