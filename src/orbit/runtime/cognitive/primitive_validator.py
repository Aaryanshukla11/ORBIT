"""Primitive Validator enforcing strict action contracts and parameter schemas.

Guardrail 1: Single Execution Path
Guardrail 3: Canonical Primitives Only (No legacy aliases permitted here)
Guardrail 4: LLM Does Not Control Physical Coordinates
Guardrail 7: Verification Must Be Semantic (Action must declare an expected effect/contract)
"""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionValidationFailureCode,
    ActionValidationResult,
    TIER1_COMPUTER_PRIMITIVES,
    TIER2_OBSERVATION_PRIMITIVES,
    TIER3_ENVIRONMENT_INTERFACES,
    CONTROL_SIGNAL_PRIMITIVES,
)

logger = logging.getLogger(__name__)


class PrimitiveValidationResult(BaseModel):
    """Validation report for an AbstractAction or ComposedPrimitiveSequence."""

    is_valid: bool = Field(..., description="Whether action satisfies all primitive contract rules")
    failure_code: Optional[ActionValidationFailureCode] = Field(default=None, description="Failure code if invalid")
    failure_reason: Optional[str] = Field(default=None, description="Diagnostic explanation of validation failure")
    validated_action: Optional[AbstractAction] = Field(default=None, description="Normalized validated action")


class PrimitiveValidator:
    """Validates that primitive actions adhere to canonical vocabulary and safety invariants.

    Enforces:
    1. Canonical vocabulary only (legacy aliases rejected).
    2. Zero physical screen coordinates in SemanticTarget or action parameters.
    3. Mandatory semantic outcome contract / expected effect.
    4. Target role / semantic context presence for interactive pointer primitives.
    """

    CANONICAL_ACTION_TYPES: frozenset[AbstractActionType] = (
        TIER1_COMPUTER_PRIMITIVES
        | TIER2_OBSERVATION_PRIMITIVES
        | TIER3_ENVIRONMENT_INTERFACES
        | CONTROL_SIGNAL_PRIMITIVES
    )

    FORBIDDEN_COORDINATE_KEYS: Set[str] = {
        "x", "y", "screen_x", "screen_y", "coord_x", "coord_y", "pos_x", "pos_y",
        "screen_position", "coordinates", "raw_x", "raw_y", "bbox", "bounding_box"
    }

    POINTER_INTERACTION_TYPES: Set[AbstractActionType] = {
        AbstractActionType.CLICK,
        AbstractActionType.DOUBLE_CLICK,
        AbstractActionType.RIGHT_CLICK,
        AbstractActionType.SELECT_OPTION,
        AbstractActionType.DRAG,
    }

    def validate_action(
        self,
        action: Any,
        available_capabilities: Optional[Set[str]] = None,
    ) -> PrimitiveValidationResult:
        """Validate an individual primitive action against canonical rules."""
        if action is None:
            return PrimitiveValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.INVALID_ACTION,
                failure_reason="Action cannot be None",
            )

        # 1. Parse or unwrap into AbstractAction
        if isinstance(action, dict):
            # Proactively check coordinate violation on raw dict before schema parsing
            params = action.get("parameters", {})
            if isinstance(params, dict):
                found_coords = self.FORBIDDEN_COORDINATE_KEYS.intersection(k.lower() for k in params.keys())
                if found_coords:
                    return PrimitiveValidationResult(
                        is_valid=False,
                        failure_code=ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION,
                        failure_reason=f"Action parameters contain prohibited physical coordinates: {found_coords}",
                    )
            target = action.get("target") or action.get("semantic_target")
            if isinstance(target, dict):
                found_coords = self.FORBIDDEN_COORDINATE_KEYS.intersection(k.lower() for k in target.keys())
                if found_coords:
                    return PrimitiveValidationResult(
                        is_valid=False,
                        failure_code=ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION,
                        failure_reason=f"Semantic target contains prohibited physical coordinates: {found_coords}",
                    )
            try:
                action_obj = AbstractAction.model_validate(action)
            except Exception as e:
                return PrimitiveValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.INVALID_ACTION,
                    failure_reason=f"Action failed schema validation: {e}",
                )
        elif isinstance(action, AbstractAction):
            action_obj = action
        else:
            return PrimitiveValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.INVALID_ACTION,
                failure_reason=f"Unsupported action object type: {type(action)}",
            )

        # 2. Canonical Primitive Vocabulary Invariant
        raw_type = action_obj.action_type
        if not isinstance(raw_type, AbstractActionType) or raw_type not in self.CANONICAL_ACTION_TYPES:
            return PrimitiveValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.UNSUPPORTED_ACTION,
                failure_reason=f"Non-canonical action type: '{raw_type}'. Must be one of canonical AbstractActionType.",
            )

        # 3. Coordinate Policy Invariant
        if action_obj.parameters:
            found_coords = self.FORBIDDEN_COORDINATE_KEYS.intersection(k.lower() for k in action_obj.parameters.keys())
            if found_coords:
                return PrimitiveValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.COORDINATE_POLICY_VIOLATION,
                    failure_reason=f"Action contains prohibited physical coordinates in parameters: {found_coords}",
                )

        # 4. Semantic Target Invariant for Pointer Interactions
        if action_obj.action_type in self.POINTER_INTERACTION_TYPES:
            if action_obj.target is None and action_obj.action_type != AbstractActionType.DRAG:
                return PrimitiveValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.MISSING_SEMANTIC_TARGET,
                    failure_reason=f"Action type '{action_obj.action_type.value}' requires a SemanticTarget (no raw clicks without target)",
                )

        # 5. Semantic Expected Outcome Contract Invariant
        if action_obj.action_type not in CONTROL_SIGNAL_PRIMITIVES and action_obj.action_type not in (
            AbstractActionType.WAIT,
            AbstractActionType.WAIT_SETTLE,
        ):
            has_contract = action_obj.outcome_contract is not None
            has_effect = bool(action_obj.expected_effect and action_obj.expected_effect.strip())
            if not has_contract and not has_effect:
                return PrimitiveValidationResult(
                    is_valid=False,
                    failure_code=ActionValidationFailureCode.MISSING_OUTCOME_CONTRACT,
                    failure_reason=f"Action '{action_obj.action_type.value}' must specify an outcome_contract or expected_effect.",
                )

        # 6. Type-specific Parameter Schema Check
        param_err = self._validate_parameters(action_obj.action_type, action_obj.parameters)
        if param_err:
            return PrimitiveValidationResult(
                is_valid=False,
                failure_code=ActionValidationFailureCode.INVALID_PARAMETERS,
                failure_reason=f"Parameter validation failed for {action_obj.action_type.value}: {param_err}",
            )

        return PrimitiveValidationResult(
            is_valid=True,
            failure_code=ActionValidationFailureCode.VALID,
            validated_action=action_obj,
        )

    def _validate_parameters(self, action_type: AbstractActionType, params: Dict[str, Any]) -> Optional[str]:
        """Validate type-specific parameters."""
        if action_type == AbstractActionType.LAUNCH_APPLICATION:
            if not params.get("application_name") and not params.get("app_name") and not params.get("name"):
                return "Missing required parameter 'application_name'"
        elif action_type == AbstractActionType.TYPE_TEXT:
            if "text" not in params and "query" not in params:
                return "Missing required parameter 'text'"
        elif action_type == AbstractActionType.SEND_HOTKEY:
            if "hotkey" not in params and "keys" not in params and "key" not in params:
                return "Missing required parameter 'hotkey' or 'keys'"
        elif action_type == AbstractActionType.SCROLL:
            direction = str(params.get("direction", "down")).lower()
            if direction not in ("up", "down", "left", "right"):
                return f"Invalid scroll direction: '{direction}'"
        elif action_type in (AbstractActionType.FILE_READ, AbstractActionType.FILE_WRITE, AbstractActionType.SAVE_FILE):
            if "path" not in params and "file_path" not in params and "target_path" not in params and "filename" not in params:
                return "Missing required parameter 'path' or 'target_path' or 'filename'"
        elif action_type == AbstractActionType.BROWSER_NAVIGATE:
            if "url" not in params:
                return "Missing required parameter 'url'"
        elif action_type == AbstractActionType.DRAW_STROKES:
            strokes = params.get("strokes")
            if not strokes and not params.get("shape") and not params.get("target"):
                return "DRAW_STROKES requires 'target' and normalized 'strokes' geometry"
            if strokes is not None:
                if not isinstance(strokes, list):
                    return "Parameter 'strokes' must be a list of stroke point sequences"
                for s_idx, stroke in enumerate(strokes):
                    if not isinstance(stroke, list):
                        return f"Stroke {s_idx} must be a list of 2-numeric points (u, v)"
                    for p_idx, pt in enumerate(stroke):
                        if isinstance(pt, dict):
                            return f"Stroke {s_idx} point {p_idx} cannot be a dictionary (raw coordinate dictionaries are prohibited)"
                        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                            return f"Stroke {s_idx} point {p_idx} must be a 2-tuple of numeric coordinates (u, v)"
                        u, v = pt
                        if not isinstance(u, (int, float)) or not isinstance(v, (int, float)):
                            return f"Stroke {s_idx} point {p_idx} coordinates must be numbers"
                        if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
                            return f"Stroke {s_idx} point {p_idx} ({u}, {v}) violates normalized canvas bounds [0.0, 1.0]"
        return None


class ProposalValidationStage(str, Enum):
    """Validation stages in the deterministic model proposal gate."""

    SCHEMA = "SCHEMA"
    CAPABILITY = "CAPABILITY"
    SAFETY = "SAFETY"
    GROUNDING = "GROUNDING"


class ModelProposalValidationResult(BaseModel):
    """Validation report for a ModelActionProposal."""

    is_valid: bool = Field(..., description="Whether proposal passed all 4 validation gates")
    failed_stage: Optional[ProposalValidationStage] = Field(default=None, description="Stage that failed")
    failure_reason: Optional[str] = Field(default=None, description="Detailed failure description")
    diagnostic_feedback: Optional[str] = Field(default=None, description="Actionable diagnostic prompt for model retry")
    validated_proposal: Optional[Any] = Field(default=None, description="Validated ModelActionProposal instance")


class ModelProposalValidator:
    """Multi-stage deterministic validation gate for LLM-generated action proposals.

    Guarantees:
    1. Schema Validation: Checks structure, required fields, and valid action types.
    2. Capability Validation: Ensures action type and requested target are supported.
    3. Safety Policy Gate: Prevents dangerous OS commands, unauthorized writes, or malicious syntax.
    4. Grounding Validation: Verifies bounding box coordinates and target role/selector validity.
    """

    ALLOWED_ACTION_TYPES: Set[str] = {
        "CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "TYPE", "HOTKEY",
        "LAUNCH", "SAVE_FILE", "WAIT", "SCROLL", "DRAG", "DRAW", "COMPLETE", "FAIL"
    }

    RESTRICTED_KEYWORDS: Set[str] = {
        "rmdir", "del /f", "format ", "format c:", "drop database", "sudo rm",
        "powershell -e", "certutil -urlcache", "reg delete", "shutdown /s"
    }

    def validate_proposal(
        self,
        proposal: Any,
        supported_capabilities: Optional[Set[str]] = None,
        screen_bounds: Optional[Dict[str, int]] = None,
        current_observation_id: Optional[str] = None,
    ) -> ModelProposalValidationResult:
        """Evaluate action proposal through the 4 validation stages."""
        from orbit.runtime.cognitive.model_proposal import ModelActionProposal, ModelActionType

        # ---------------------------------------------------------
        # STAGE 1: Schema Validation
        # ---------------------------------------------------------
        if proposal is None:
            return self._reject(
                ProposalValidationStage.SCHEMA,
                "Model returned empty/null proposal.",
                "Proposal was null. Please generate a valid JSON object matching the ModelActionProposal schema."
            )

        if isinstance(proposal, dict):
            try:
                proposal_obj = ModelActionProposal.model_validate(proposal)
            except Exception as e:
                return self._reject(
                    ProposalValidationStage.SCHEMA,
                    f"Schema parsing error: {e}",
                    f"Your proposal JSON did not match the expected schema: {e}. Please correct the JSON structure."
                )
        elif isinstance(proposal, ModelActionProposal):
            proposal_obj = proposal
        else:
            return self._reject(
                ProposalValidationStage.SCHEMA,
                f"Unsupported proposal type: {type(proposal)}",
                "Proposal must be a JSON object conforming to ModelActionProposal."
            )

        if not proposal_obj.expected_outcome or not proposal_obj.expected_outcome.strip():
            return self._reject(
                ProposalValidationStage.SCHEMA,
                "Missing 'expected_outcome' in proposal.",
                "Every action proposal MUST include an 'expected_outcome' describing the anticipated visual/OS change."
            )

        # ---------------------------------------------------------
        # STAGE 2: Capability Validation
        # ---------------------------------------------------------
        act_type_str = proposal_obj.action_type.value
        if act_type_str not in self.ALLOWED_ACTION_TYPES:
            return self._reject(
                ProposalValidationStage.CAPABILITY,
                f"Unsupported action type '{act_type_str}'.",
                f"Action type '{act_type_str}' is not supported. Use one of: {sorted(self.ALLOWED_ACTION_TYPES)}"
            )

        if supported_capabilities:
            if act_type_str == "SAVE_FILE" and "save" not in supported_capabilities and "save_file" not in supported_capabilities:
                pass  # Base OS capability always supports file save

        # ---------------------------------------------------------
        # STAGE 3: Safety Policy Gate
        # ---------------------------------------------------------
        param_str = str(proposal_obj.parameters).lower()
        for kw in self.RESTRICTED_KEYWORDS:
            if kw in param_str:
                return self._reject(
                    ProposalValidationStage.SAFETY,
                    f"Prohibited security-sensitive keyword detected: '{kw}'",
                    f"Security policy violation: Command contains restricted sequence '{kw}'. Propose a safe alternative."
                )

        # ---------------------------------------------------------
        # STAGE 4: Grounding Validation & Freshness
        # ---------------------------------------------------------
        target = proposal_obj.target_selector
        if target:
            # Check observation freshness if provided
            if current_observation_id:
                prop_obs_id = target.observation_id or proposal_obj.observation_id
                if prop_obs_id and prop_obs_id != current_observation_id:
                    return self._reject(
                        ProposalValidationStage.GROUNDING,
                        f"STALE_GROUNDING_REJECTED: Proposal was grounded against observation '{prop_obs_id}', but current active observation is '{current_observation_id}'.",
                        f"Stale grounding detected. Re-grounding against current observation '{current_observation_id}' is required."
                    )

            if target.bounds:
                bounds = target.bounds
                if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
                    return self._reject(
                        ProposalValidationStage.GROUNDING,
                        f"Target bounds must be a 4-element list [ymin, xmin, ymax, xmax], got {bounds}",
                        f"Invalid bounding box {bounds}. Must be 4 integers normalized between 0 and 1000."
                    )
                ymin, xmin, ymax, xmax = bounds
                if not all(isinstance(v, (int, float)) for v in (ymin, xmin, ymax, xmax)):
                    return self._reject(
                        ProposalValidationStage.GROUNDING,
                        f"Target bounds coordinates must be numbers, got {bounds}",
                        "Bounding box coordinates must be numeric values."
                    )
                if ymin < 0 or xmin < 0 or ymax > 1000 or xmax > 1000 or ymin > ymax or xmin > xmax:
                    return self._reject(
                        ProposalValidationStage.GROUNDING,
                        f"Normalized bounding box {bounds} violates range [0, 1000]",
                        f"Bounding box {bounds} is out of bounds. Normalized screen coordinates must be between 0 and 1000 with ymin <= ymax and xmin <= xmax."
                    )

        return ModelProposalValidationResult(
            is_valid=True,
            validated_proposal=proposal_obj,
        )

    def _reject(
        self,
        stage: ProposalValidationStage,
        reason: str,
        feedback: str,
    ) -> ModelProposalValidationResult:
        """Construct rejection validation result."""
        logger.warning("Model Proposal Rejected at [%s]: %s", stage.value, reason)
        return ModelProposalValidationResult(
            is_valid=False,
            failed_stage=stage,
            failure_reason=reason,
            diagnostic_feedback=feedback,
        )

