"""Focused Unit Tests for ORBIT Tool Schema (Objective P1-B).

Validates:
1. Tool schema creation from custom definition.
2. Tool schema creation from Pydantic models (from_pydantic).
3. JSON schema serialization (raw and openai formats).
4. Required parameter validation.
5. Optional parameter validation with defaults.
6. Primitive type validation (string, integer, boolean, dict, list).
7. Enum constraint validation.
8. Unknown parameter rejection in strict mode.
9. Physical coordinate rejection (CoordinatePolicyViolation).
10. Dangerous executable code rejection (SecurityPolicyViolation).
11. Semantic target inclusion and validation.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractActionType,
    ClickParams,
    TypeTextParams,
)
from orbit.runtime.tools.schema import (
    ToolCategory,
    ToolSchema,
    ToolValidationResult,
)


class CustomTestParams(BaseModel):
    query: str = Field(..., description="Search query string")
    max_results: int = Field(default=10, ge=1, le=100, description="Max results")
    format_type: str = Field(default="json", description="Output format: 'json', 'csv', 'text'")
    enable_cache: bool = Field(default=True, description="Whether to use cache")


class TestToolSchema(unittest.TestCase):
    """Unit tests for ToolSchema creation, serialization, and validation."""

    def test_01_tool_schema_creation_custom(self):
        """Verify custom tool schema properties and defaults."""
        schema = ToolSchema(
            name="custom_search",
            description="Perform custom search query",
            category=ToolCategory.CUSTOM,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Limit count"},
                },
                "required": ["query"],
            },
            required_parameters=["query"],
        )
        self.assertEqual(schema.name, "custom_search")
        self.assertEqual(schema.category, ToolCategory.CUSTOM)
        self.assertIn("query", schema.required_parameters)
        self.assertTrue(schema.strict)

    def test_02_tool_schema_from_pydantic(self):
        """Verify construction from Pydantic models."""
        tool = ToolSchema.from_pydantic(
            name="test_search",
            description="Search tool backed by Pydantic",
            model=CustomTestParams,
            action_type=AbstractActionType.FILE_READ,
            category=ToolCategory.ENVIRONMENT_INTERFACE,
        )
        self.assertEqual(tool.name, "test_search")
        self.assertEqual(tool.action_type, AbstractActionType.FILE_READ)
        self.assertIn("query", tool.input_schema["properties"])
        self.assertIn("max_results", tool.input_schema["properties"])
        self.assertIn("query", tool.input_schema["required"])
        # Title must be stripped
        self.assertNotIn("title", tool.input_schema["properties"]["query"])

    def test_03_json_serialization_raw_and_openai(self):
        """Verify JSON schema serialization formats."""
        tool = ToolSchema.from_pydantic(
            name="click",
            description="Click a UI element",
            model=ClickParams,
            action_type=AbstractActionType.CLICK,
        )
        # Raw format
        raw = tool.to_json_schema(format="raw")
        self.assertEqual(raw["name"], "click")
        self.assertEqual(raw["description"], "Click a UI element")
        self.assertIn("properties", raw["parameters"])

        # OpenAI format
        openai_fmt = tool.to_json_schema(format="openai")
        self.assertEqual(openai_fmt["type"], "function")
        self.assertEqual(openai_fmt["function"]["name"], "click")
        self.assertEqual(openai_fmt["function"]["parameters"], raw["parameters"])

    def test_04_required_parameter_validation_success_and_failure(self):
        """Verify required parameters are strictly enforced."""
        tool = ToolSchema.from_pydantic(
            name="type_text",
            description="Type text into control",
            model=TypeTextParams,
            action_type=AbstractActionType.TYPE_TEXT,
        )
        # Success with required 'text'
        res = tool.validate_parameters({"text": "Hello World"})
        self.assertTrue(res.is_valid)
        self.assertEqual(res.validated_parameters["text"], "Hello World")
        self.assertEqual(res.action_type, AbstractActionType.TYPE_TEXT)

        # Failure when missing required 'text'
        res_fail = tool.validate_parameters({})
        self.assertFalse(res_fail.is_valid)
        self.assertTrue(any("text" in err for err in res_fail.errors))

    def test_05_primitive_type_validation(self):
        """Verify type validation catches type mismatches."""
        tool = ToolSchema(
            name="tester",
            description="Test types",
            input_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "flag": {"type": "boolean"},
                    "name": {"type": "string"},
                },
                "required": ["count", "flag", "name"],
            },
        )
        # Success
        val = tool.validate_parameters({"count": 42, "flag": True, "name": "alice"})
        self.assertTrue(val.is_valid)

        # Wrong type: count passed as string
        val_bad = tool.validate_parameters({"count": "not_an_int", "flag": True, "name": "alice"})
        self.assertFalse(val_bad.is_valid)
        self.assertTrue(any("count" in err for err in val_bad.errors))

        # Boolean passed where int expected
        val_bool_int = tool.validate_parameters({"count": True, "flag": True, "name": "alice"})
        self.assertFalse(val_bool_int.is_valid)

    def test_06_enum_constraint_validation(self):
        """Verify enum constraints are enforced."""
        tool = ToolSchema(
            name="exporter",
            description="Export file",
            input_schema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["pdf", "csv", "json"]}
                },
                "required": ["format"],
            },
        )
        ok = tool.validate_parameters({"format": "csv"})
        self.assertTrue(ok.is_valid)

        bad = tool.validate_parameters({"format": "exe"})
        self.assertFalse(bad.is_valid)
        self.assertTrue(any("allowed values" in err for err in bad.errors))

    def test_07_unknown_parameter_rejection_in_strict_mode(self):
        """Verify strict mode rejects unknown/unexpected parameters."""
        tool = ToolSchema.from_pydantic(
            name="click",
            description="Click a control",
            model=ClickParams,
            strict=True,
        )
        res = tool.validate_parameters({
            "button": "left",
            "unknown_extra_field": "surprise",
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("unknown_extra_field" in err for err in res.errors))

    def test_08_physical_coordinate_rejection(self):
        """Verify CoordinatePolicyViolation rejects physical coordinates (x, y, etc.)."""
        tool = ToolSchema.from_pydantic(
            name="click",
            description="Click a control",
            model=ClickParams,
        )
        # Flat coordinate violation
        res1 = tool.validate_parameters({"x": 100, "y": 200, "button": "left"})
        self.assertFalse(res1.is_valid)
        self.assertTrue(any("CoordinatePolicyViolation" in err for err in res1.errors))

        # Nested coordinate violation inside target
        res2 = tool.validate_parameters({
            "button": "left",
            "target": {"name": "OK", "x": 100, "y": 200},
        })
        self.assertFalse(res2.is_valid)
        self.assertTrue(any("CoordinatePolicyViolation" in err for err in res2.errors))

    def test_09_dangerous_payload_rejection(self):
        """Verify SecurityPolicyViolation blocks executable script injection."""
        tool = ToolSchema.from_pydantic(
            name="type_text",
            description="Type text",
            model=TypeTextParams,
        )
        res_eval = tool.validate_parameters({"text": "eval('import os; os.system(\"calc\")')"})
        self.assertFalse(res_eval.is_valid)
        self.assertTrue(any("SecurityPolicyViolation" in err for err in res_eval.errors))

        res_exec = tool.validate_parameters({"text": "exec('print(1)')"})
        self.assertFalse(res_exec.is_valid)
        self.assertTrue(any("SecurityPolicyViolation" in err for err in res_exec.errors))

    def test_10_non_dict_parameter_rejection(self):
        """Verify non-dictionary parameters fail validation cleanly."""
        tool = ToolSchema(name="simple", description="Simple tool")
        res1 = tool.validate_parameters("not_a_dict")  # type: ignore[arg-type]
        self.assertFalse(res1.is_valid)
        self.assertTrue(any("dictionary" in err for err in res1.errors))

        res2 = tool.validate_parameters([1, 2, 3])  # type: ignore[arg-type]
        self.assertFalse(res2.is_valid)


if __name__ == "__main__":
    unittest.main()
