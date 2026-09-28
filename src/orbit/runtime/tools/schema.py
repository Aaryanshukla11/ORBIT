"""ORBIT Tool Schema Subsystem.

Provides model-consumable, strongly-typed capability descriptors, JSON schema export,
and strict parameter validation contracts for ORBIT's single authoritative execution path.

Architectural Invariants:
1. Pure description and validation layer (contains ZERO executable logic).
2. Physical screen coordinates (x, y) are strictly forbidden in parameters or targets.
3. Fail-closed validation for unknown, malformed, or unauthorized parameters.
4. Serializes deterministically to standard JSON schema (OpenAI / Anthropic / Gemini compatible).
5. Grounded in canonical ORBIT action contracts and parameter models.
"""

from __future__ import annotations

from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Set, Type, Union
from pydantic import BaseModel, Field, ValidationError

from orbit.runtime.agent.contracts import (
    AbstractActionType,
    SemanticTarget,
)

logger = logging.getLogger(__name__)

# Properties stripped from JSON schemas for clean model consumption
EXCLUDED_JSON_SCHEMA_PROPERTIES: Set[str] = {"title", "$defs", "definitions"}

# Invariant: Physical screen coordinates must NEVER originate from the model/tool layer
FORBIDDEN_COORDINATE_KEYS: Set[str] = {
    "x", "y", "screen_x", "screen_y", "coord_x", "coord_y", "pos_x", "pos_y",
    "screen_position", "coordinates", "raw_x", "raw_y", "bbox", "bounding_box"
}

# Dangerous payloads blocked at schema validation boundary
DANGEROUS_PAYLOAD_PATTERNS: List[re.Pattern] = [
    re.compile(r"__import__\s*\(", re.IGNORECASE),
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bexec\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.", re.IGNORECASE),
    re.compile(r"os\.system\s*\(", re.IGNORECASE),
    re.compile(r"<script[\s>]", re.IGNORECASE),
]


class ToolCategory(str, Enum):
    """Categorization of tools matching ORBIT primitive hierarchy."""

    COMPUTER_PRIMITIVE = "computer_primitive"      # Tier 1 physical UI/desktop interactions
    OBSERVATION_PRIMITIVE = "observation_primitive"  # Tier 2 sensory perception
    ENVIRONMENT_INTERFACE = "environment_interface"  # Tier 3 external providers
    CONTROL_SIGNAL = "control_signal"                # Task completion / abort
    CUSTOM = "custom"


class ToolValidationResult(BaseModel):
    """Outcome report for parameter validation against a ToolSchema."""

    is_valid: bool = Field(..., description="Whether parameters strictly conform to tool schema")
    errors: List[str] = Field(default_factory=list, description="Diagnostic error messages if validation failed")
    validated_parameters: Dict[str, Any] = Field(default_factory=dict, description="Cleaned, typed parameters if valid")
    action_type: Optional[AbstractActionType] = Field(default=None, description="Bound canonical primitive type")


def clean_json_schema(obj: Any) -> Any:
    """Recursively strip title and internal metadata from generated Pydantic JSON schema."""
    if isinstance(obj, dict):
        return {
            k: clean_json_schema(v)
            for k, v in obj.items()
            if k not in EXCLUDED_JSON_SCHEMA_PROPERTIES
        }
    elif isinstance(obj, list):
        return [clean_json_schema(item) for item in obj]
    return obj


class ToolSchema(BaseModel):
    """Declarative capability specification consumable by AI models.

    Defines tool name, description, JSON input schema, and validation rules.
    Does NOT contain executable callbacks or invocation logic.
    """

    name: str = Field(..., description="Stable capability identifier (e.g. 'click', 'type_text')")
    description: str = Field(..., description="Human/model-readable description of what the capability does")
    action_type: Optional[AbstractActionType] = Field(default=None, description="Underlying canonical primitive")
    category: ToolCategory = Field(default=ToolCategory.COMPUTER_PRIMITIVE, description="Capability category")
    input_schema: Dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})
    required_parameters: List[str] = Field(default_factory=list, description="List of required parameter names")
    parameter_model: Optional[Any] = Field(default=None, exclude=True, description="Backing Pydantic model if any")
    is_destructive: bool = Field(default=False, description="Whether capability alters system or file state")
    strict: bool = Field(default=True, description="Whether unknown parameters are strictly rejected")

    model_config = {
        "arbitrary_types_allowed": True,
    }

    def to_json_schema(self, format: str = "openai") -> Dict[str, Any]:
        """Export tool definition in model-compatible JSON schema format.

        Supported formats:
        - 'openai': {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        - 'raw': {"name": ..., "description": ..., "parameters": ...}
        """
        params = self.input_schema or {"type": "object", "properties": {}}

        if format.lower() == "openai":
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": params,
                },
            }
        # Default raw format (Anthropic / Gemini / direct function descriptor)
        return {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }

    @property
    def json_schema(self) -> Dict[str, Any]:
        """Convenience property returning standard raw function descriptor schema."""
        return self.to_json_schema(format="raw")

    def validate_parameters(self, params: Dict[str, Any]) -> ToolValidationResult:
        """Validate input parameters against this tool's contract.

        Enforces:
        1. Reject non-dict input.
        2. Prohibit physical coordinates (x, y, etc.).
        3. Prohibit dangerous code execution strings.
        4. Validate against Pydantic parameter_model if present.
        5. Check required fields and data types.
        6. Reject unknown fields if strict=True.
        """
        if not isinstance(params, dict):
            return ToolValidationResult(
                is_valid=False,
                errors=["Parameters must be provided as a dictionary object."],
                action_type=self.action_type,
            )

        errors: List[str] = []

        # 1. Coordinate isolation check
        self._check_forbidden_coordinates(params, errors)
        if errors:
            return ToolValidationResult(
                is_valid=False,
                errors=errors,
                action_type=self.action_type,
            )

        # 2. Dangerous string payload check
        self._check_dangerous_payloads(params, errors)
        if errors:
            return ToolValidationResult(
                is_valid=False,
                errors=errors,
                action_type=self.action_type,
            )

        # 3. Pydantic model validation if available
        if self.parameter_model is not None and issubclass(self.parameter_model, BaseModel):
            # Separate target from action parameters if target is defined on model vs top-level
            model_fields = self.parameter_model.model_fields.keys()
            filtered_params = {k: v for k, v in params.items() if k in model_fields}
            
            # Check for unknown fields if strict
            if self.strict:
                allowed_keys = set(model_fields) | {"target", "semantic_target", "rationale", "expected_effect"}
                unknown_keys = set(params.keys()) - allowed_keys
                if unknown_keys:
                    errors.append(f"Unexpected unknown parameters for tool '{self.name}': {sorted(unknown_keys)}")

            try:
                validated_obj = self.parameter_model(**filtered_params)
                clean_params = validated_obj.model_dump()
                # Preserve valid top-level target/context if passed
                if "target" in params and "target" not in clean_params:
                    clean_params["target"] = params["target"]
                if "rationale" in params and "rationale" not in clean_params:
                    clean_params["rationale"] = params["rationale"]

                if errors:
                    return ToolValidationResult(
                        is_valid=False,
                        errors=errors,
                        action_type=self.action_type,
                    )

                return ToolValidationResult(
                    is_valid=True,
                    errors=[],
                    validated_parameters=clean_params,
                    action_type=self.action_type,
                )
            except ValidationError as val_err:
                for err in val_err.errors():
                    loc = ".".join(str(x) for x in err.get("loc", []))
                    msg = err.get("msg", "Invalid value")
                    errors.append(f"Parameter '{loc}': {msg}")
                return ToolValidationResult(
                    is_valid=False,
                    errors=errors,
                    action_type=self.action_type,
                )
            except Exception as ex:
                return ToolValidationResult(
                    is_valid=False,
                    errors=[f"Parameter validation exception: {ex}"],
                    action_type=self.action_type,
                )

        # 4. Fallback schema-driven validation for schema without backing Pydantic model
        properties = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", self.required_parameters)

        for req in required:
            if req not in params:
                errors.append(f"Missing required parameter '{req}' for tool '{self.name}'")

        if self.strict:
            allowed = set(properties.keys()) | {"target", "semantic_target", "rationale", "expected_effect"}
            unknown = set(params.keys()) - allowed
            if unknown:
                errors.append(f"Unexpected unknown parameters for tool '{self.name}': {sorted(unknown)}")

        for key, val in params.items():
            if key in properties:
                prop_spec = properties[key]
                expected_type = prop_spec.get("type")
                if expected_type:
                    if not self._check_type(val, expected_type):
                        errors.append(f"Parameter '{key}' must be of type '{expected_type}', got {type(val).__name__}")
                if "enum" in prop_spec and val not in prop_spec["enum"]:
                    errors.append(f"Parameter '{key}' value '{val}' not in allowed values: {prop_spec['enum']}")

        if errors:
            return ToolValidationResult(
                is_valid=False,
                errors=errors,
                action_type=self.action_type,
            )

        return ToolValidationResult(
            is_valid=True,
            errors=[],
            validated_parameters=dict(params),
            action_type=self.action_type,
        )

    def _check_forbidden_coordinates(self, data: Any, errors: List[str]) -> None:
        """Recursively scan dict for any prohibited coordinate keys."""
        if isinstance(data, dict):
            found = FORBIDDEN_COORDINATE_KEYS.intersection(k.lower() for k in data.keys())
            if found:
                errors.append(
                    f"CoordinatePolicyViolation: Physical screen coordinates {sorted(found)} are forbidden. "
                    "Use SemanticTarget (name, role, context, text_hint) instead."
                )
            for v in data.values():
                self._check_forbidden_coordinates(v, errors)
        elif isinstance(data, list):
            for item in data:
                self._check_forbidden_coordinates(item, errors)

    def _check_dangerous_payloads(self, data: Any, errors: List[str]) -> None:
        """Inspect string values for arbitrary code execution attempts."""
        if isinstance(data, str):
            for pattern in DANGEROUS_PAYLOAD_PATTERNS:
                if pattern.search(data):
                    errors.append(
                        f"SecurityPolicyViolation: Potentially dangerous executable code pattern detected in string parameter: '{pattern.pattern}'"
                    )
        elif isinstance(data, dict):
            for v in data.values():
                self._check_dangerous_payloads(v, errors)
        elif isinstance(data, list):
            for item in data:
                self._check_dangerous_payloads(item, errors)

    @staticmethod
    def _check_type(val: Any, expected_type: str) -> bool:
        """Validate JSON type against Python value."""
        if val is None:
            return False
        if expected_type == "string":
            return isinstance(val, str)
        if expected_type == "integer":
            return isinstance(val, int) and not isinstance(val, bool)
        if expected_type == "number":
            return isinstance(val, (int, float)) and not isinstance(val, bool)
        if expected_type == "boolean":
            return isinstance(val, bool)
        if expected_type == "array":
            return isinstance(val, list)
        if expected_type == "object":
            return isinstance(val, dict)
        return True

    @classmethod
    def from_pydantic(
        cls,
        name: str,
        description: str,
        model: Type[BaseModel],
        action_type: Optional[AbstractActionType] = None,
        category: ToolCategory = ToolCategory.COMPUTER_PRIMITIVE,
        is_destructive: bool = False,
        strict: bool = True,
        include_target: bool = True,
    ) -> ToolSchema:
        """Construct a ToolSchema automatically from a Pydantic parameter model."""
        raw_schema = model.model_json_schema(mode="serialization")
        cleaned_schema = clean_json_schema(raw_schema)
        properties = cleaned_schema.get("properties", {})
        required = list(cleaned_schema.get("required", []))

        # Optionally add standard SemanticTarget to schema for interactive tools
        if include_target and "target" not in properties:
            properties["target"] = {
                "type": "object",
                "description": "Semantic target to interact with (NO physical coordinates allowed)",
                "properties": {
                    "name": {"type": "string", "description": "Logical target label, button text, or window title"},
                    "role": {"type": "string", "description": "UI role: button, edit, canvas, window, tab, etc."},
                    "context": {"type": "string", "description": "Surrounding application or window title"},
                    "text_hint": {"type": "string", "description": "Visible text to locate via OCR"},
                    "accessibility_hint": {"type": "string", "description": "AutomationId or ClassName hint"},
                },
            }

        input_schema = {
            "type": "object",
            "properties": properties,
            "required": required,
        }

        return cls(
            name=name,
            description=description,
            action_type=action_type,
            category=category,
            input_schema=input_schema,
            required_parameters=required,
            parameter_model=model,
            is_destructive=is_destructive,
            strict=strict,
        )
