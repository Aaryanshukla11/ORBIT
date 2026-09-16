"""Declarative Model Action Proposal schema (Phase 2C).

Enforces clean, declarative action proposals from multimodal LLMs without
requiring internal chain-of-thought fields.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class ModelActionType(str, Enum):
    """Canonical model-level action types."""

    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    TYPE = "TYPE"
    HOTKEY = "HOTKEY"
    LAUNCH = "LAUNCH"
    SAVE_FILE = "SAVE_FILE"
    WAIT = "WAIT"
    SCROLL = "SCROLL"
    DRAG = "DRAG"
    DRAW = "DRAW"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"


class TargetSelector(BaseModel):
    """Declarative selector for UI targets."""

    role: Optional[str] = Field(default=None, description="UI role, e.g., button, menu_item, window, text_field")
    name: Optional[str] = Field(default=None, description="Accessible name or label of the target")
    bounds: Optional[List[int]] = Field(default=None, description="Normalized bounding box [ymin, xmin, ymax, xmax] 0-1000")
    selector: Optional[str] = Field(default=None, description="Semantic or automation identifier")
    ocr_text: Optional[str] = Field(default=None, description="Expected OCR text at target location")
    observation_id: Optional[str] = Field(default=None, description="Observation ID against which target was grounded")


class ModelActionProposal(BaseModel):
    """Declarative action proposal returned by the multimodal model."""

    proposal_id: str = Field(default_factory=lambda: f"prop_{uuid4().hex[:8]}", description="Unique proposal ID")
    action_type: ModelActionType = Field(..., description="Canonical action type requested by model")
    target_selector: Optional[TargetSelector] = Field(default=None, description="Semantic target selector")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action arguments (e.g. text, key_combination)")
    expected_outcome: str = Field(..., description="Expected visual or OS state change after action")
    confidence: Optional[float] = Field(default=1.0, ge=0.0, le=1.0, description="Model confidence score")
    diagnostic_reasoning: Optional[str] = Field(default=None, description="Short diagnostic summary (optional, not chain-of-thought)")
    observation_id: Optional[str] = Field(default=None, description="Observation ID from which proposal was derived")

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary for execution pipeline."""
        return {
            "proposal_id": self.proposal_id,
            "action_type": self.action_type.value,
            "target": self.target_selector.model_dump() if self.target_selector else None,
            "parameters": self.parameters,
            "expected_outcome": self.expected_outcome,
            "confidence": self.confidence,
            "observation_id": self.observation_id,
        }

