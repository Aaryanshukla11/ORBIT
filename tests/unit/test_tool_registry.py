"""Focused Unit Tests for ORBIT Tool Registry (Objective P1-B).

Validates:
1. ToolRegistry initialization and pre-populated canonical primitives.
2. Custom tool registration.
3. Invalid tool name rejection (InvalidToolNameError).
4. Duplicate tool registration rejection (DuplicateToolRegistrationError).
5. Tool override behavior with allow_override=True.
6. Case-insensitive and normalized tool lookup.
7. Tool presence check (has).
8. Tool unregistration.
9. Listing tools filtered by category.
10. Exporting model-consumable schema lists.
11. Integration with EnvironmentProviderRegistry.
12. Structural invariant: Registry has zero execution methods.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orbit.runtime.agent.contracts import AbstractActionType
from orbit.runtime.tools.registry import (
    DuplicateToolRegistrationError,
    InvalidToolNameError,
    ToolRegistry,
)
from orbit.runtime.tools.schema import (
    ToolCategory,
    ToolSchema,
)


class TestToolRegistry(unittest.TestCase):
    """Unit tests for ToolRegistry lifecycle, discovery, and invariants."""

    def test_01_registry_initialization_with_builtins(self):
        """Verify registry initializes with canonical ORBIT primitives by default."""
        registry = ToolRegistry(auto_register_builtins=True)
        self.assertGreater(registry.count(), 15)

        # Tier 1 primitives
        self.assertTrue(registry.has("click"))
        self.assertTrue(registry.has("type_text"))
        self.assertTrue(registry.has("launch_application"))
        self.assertTrue(registry.has("focus_window"))
        self.assertTrue(registry.has("send_hotkey"))
        self.assertTrue(registry.has("scroll"))
        self.assertTrue(registry.has("drag"))
        self.assertTrue(registry.has("wait"))
        self.assertTrue(registry.has("draw_strokes"))

        # Tier 2 observation
        self.assertTrue(registry.has("screenshot"))
        self.assertTrue(registry.has("read_ui_element"))
        self.assertTrue(registry.has("read_ocr_text"))

        # Tier 3 environment
        self.assertTrue(registry.has("file_read"))
        self.assertTrue(registry.has("file_write"))
        self.assertTrue(registry.has("spreadsheet_read"))

        # Control signals
        self.assertTrue(registry.has("complete_goal"))
        self.assertTrue(registry.has("abort_task"))

    def test_02_empty_registry_initialization(self):
        """Verify registry can be created empty when auto_register_builtins=False."""
        registry = ToolRegistry(auto_register_builtins=False)
        self.assertEqual(registry.count(), 0)
        self.assertFalse(registry.has("click"))

    def test_03_custom_tool_registration(self):
        """Verify registering a valid custom tool."""
        registry = ToolRegistry(auto_register_builtins=False)
        tool = ToolSchema(
            name="custom_calc",
            description="Perform calculation",
            category=ToolCategory.CUSTOM,
        )
        registry.register(tool)
        self.assertTrue(registry.has("custom_calc"))
        retrieved = registry.get("custom_calc")
        self.assertIsNotNone(retrieved)
        assert retrieved is not None
        self.assertEqual(retrieved.name, "custom_calc")

    def test_04_invalid_tool_name_rejection(self):
        """Verify invalid tool names raise InvalidToolNameError."""
        registry = ToolRegistry(auto_register_builtins=False)

        # Empty name
        with self.assertRaises(InvalidToolNameError):
            tool = ToolSchema(name="valid", description="x")
            tool.name = ""
            registry.register(tool)

        # Name with spaces
        with self.assertRaises(InvalidToolNameError):
            tool = ToolSchema(name="valid", description="x")
            tool.name = "my tool"
            registry.register(tool)

        # Name starting with number
        with self.assertRaises(InvalidToolNameError):
            tool = ToolSchema(name="valid", description="x")
            tool.name = "123tool"
            registry.register(tool)

    def test_05_duplicate_registration_prevention(self):
        """Verify registering duplicate tool raises DuplicateToolRegistrationError unless allow_override=True."""
        registry = ToolRegistry(auto_register_builtins=False)
        tool1 = ToolSchema(name="lookup", description="First version")
        tool2 = ToolSchema(name="lookup", description="Second version")

        registry.register(tool1)

        with self.assertRaises(DuplicateToolRegistrationError):
            registry.register(tool2, allow_override=False)

        # Success when allow_override=True
        registry.register(tool2, allow_override=True)
        retrieved = registry.get("lookup")
        self.assertIsNotNone(retrieved)
        assert retrieved is not None
        self.assertEqual(retrieved.description, "Second version")

    def test_06_case_insensitive_and_normalized_lookup(self):
        """Verify lookup normalizes case and leading/trailing whitespace."""
        registry = ToolRegistry(auto_register_builtins=False)
        registry.register(ToolSchema(name="click", description="Click"))

        self.assertIsNotNone(registry.get("click"))
        self.assertIsNotNone(registry.get("CLICK"))
        self.assertIsNotNone(registry.get(" Click "))
        self.assertTrue(registry.has("ClIcK"))

    def test_07_unregistration(self):
        """Verify unregistering a tool removes it from the catalog."""
        registry = ToolRegistry(auto_register_builtins=False)
        registry.register(ToolSchema(name="temp_tool", description="Temporary"))
        self.assertTrue(registry.has("temp_tool"))

        removed = registry.unregister("temp_tool")
        self.assertTrue(removed)
        self.assertFalse(registry.has("temp_tool"))

        # Second unregister returns False
        self.assertFalse(registry.unregister("temp_tool"))

    def test_08_category_filtering(self):
        """Verify tools can be filtered by category."""
        registry = ToolRegistry(auto_register_builtins=True)

        comp_tools = registry.list_tools(category=ToolCategory.COMPUTER_PRIMITIVE)
        self.assertTrue(all(t.category == ToolCategory.COMPUTER_PRIMITIVE for t in comp_tools))
        self.assertTrue(any(t.name == "click" for t in comp_tools))

        obs_tools = registry.list_tools(category=ToolCategory.OBSERVATION_PRIMITIVE)
        self.assertTrue(all(t.category == ToolCategory.OBSERVATION_PRIMITIVE for t in obs_tools))
        self.assertTrue(any(t.name == "screenshot" for t in obs_tools))

    def test_09_list_schemas_format(self):
        """Verify schema listing formats for model providers."""
        registry = ToolRegistry(auto_register_builtins=True)

        openai_schemas = registry.list_schemas(format="openai")
        self.assertIsInstance(openai_schemas, list)
        self.assertTrue(len(openai_schemas) > 0)
        first_op = openai_schemas[0]
        self.assertEqual(first_op.get("type"), "function")
        self.assertIn("name", first_op.get("function", {}))

        raw_schemas = registry.list_schemas(format="raw")
        first_raw = raw_schemas[0]
        self.assertIn("name", first_raw)
        self.assertIn("parameters", first_raw)

    def test_10_environment_provider_registry_integration(self):
        """Verify registering capabilities from EnvironmentProviderRegistry."""
        mock_env_registry = MagicMock()
        mock_provider = MagicMock()
        mock_provider.supported_features = ["excel", "formulas", "csv"]
        mock_env_registry.get_all_registered_providers.side_effect = lambda prim: [mock_provider] if prim == AbstractActionType.SPREADSHEET_WRITE else []

        tool_reg = ToolRegistry(auto_register_builtins=True)
        count = tool_reg.register_from_environment_providers(mock_env_registry)
        self.assertGreaterEqual(count, 1)

        sheet_tool = tool_reg.get("spreadsheet_write")
        self.assertIsNotNone(sheet_tool)
        assert sheet_tool is not None
        self.assertIn("excel", sheet_tool.description.lower())

    def test_11_registry_has_no_execution_methods(self):
        """Verify registry is purely descriptive and contains no execution methods."""
        forbidden_methods = {
            "execute", "invoke", "ainvoke", "dispatch", "run", "click", "type",
            "launch", "shell", "call", "simulate",
        }
        registry = ToolRegistry(auto_register_builtins=False)
        attrs = set(dir(registry))
        collisions = forbidden_methods.intersection(attrs)
        self.assertEqual(len(collisions), 0, f"ToolRegistry must not have execution methods: {collisions}")


if __name__ == "__main__":
    unittest.main()
