"""Primitive Validator enforcing strict action contracts and parameter schemas.

Guardrail 1: Single Execution Path
Guardrail 3: Canonical Primitives Only (No legacy aliases permitted here)
Guardrail 4: LLM Does Not Control Physical Coordinates
Guardrail 7: Verification Must Be Semantic (Action must declare an expected effect/contract)
"""

from __future__ import annotations

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

    CANONICAL_ACTION_TYPES: Set[AbstractActionType] = (
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
        elif action_type in (AbstractActionType.FILE_READ, AbstractActionType.FILE_WRITE):
            if "path" not in params and "file_path" not in params:
                return "Missing required parameter 'path'"
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
