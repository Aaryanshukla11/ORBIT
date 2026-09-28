"""Focused Unit Tests for ORBIT Tool Service (Objective P1-B).

Validates:
1. ToolService initialization and schema retrieval.
2. Tool resolution by name.
3. Strict fail-closed request validation (unknown tool, malformed params).
4. Coordinate isolation enforcement (rejects x, y).
5. Code injection security enforcement (rejects eval/exec/import).
6. Canonical AbstractAction creation from validated tool call.
7. CandidatePlan formulation from tool call.
8. Cognitive integration with AgentPlanner (plan_from_action -> PlanDirective).
9. Structural invariant: ToolService contains NO physical execution calls.
10. AST static analysis verifying zero capability/execution imports in tools subsystem.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_planner import AgentPlanner
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.semantic_feasibility import (
    CandidatePlan,
    SemanticFeasibilityEvaluator,
    SemanticFeasibilityReport,
)
from orbit.runtime.tools.registry import ToolRegistry
from orbit.runtime.tools.schema import ToolCategory, ToolSchema
from orbit.runtime.tools.service import StructuredToolRequest, ToolService
from orbit.runtime.world_model.model import AgentWorldModel


class TestToolService(unittest.TestCase):
    """Unit tests for ToolService validation, action creation, and planner integration."""

    def setUp(self):
        self.service = ToolService(auto_register_builtins=True)

    def test_01_tool_service_initialization_and_schemas(self):
        """Verify ToolService exposes available schemas from its registry."""
        schemas = self.service.get_available_schemas(format="openai")
        self.assertIsInstance(schemas, list)
        self.assertGreater(len(schemas), 10)
        tool_names = [s["function"]["name"] for s in schemas]
        self.assertIn("click", tool_names)
        self.assertIn("type_text", tool_names)
        self.assertIn("launch_application", tool_names)

    def test_02_resolve_tool(self):
        """Verify tool resolution finds registered tools and returns None for unknown."""
        click_tool = self.service.resolve_tool("click")
        self.assertIsNotNone(click_tool)
        assert click_tool is not None
        self.assertEqual(click_tool.action_type, AbstractActionType.CLICK)

        unknown = self.service.resolve_tool("nonexistent_tool_xyz")
        self.assertIsNone(unknown)

    def test_03_validate_request_success(self):
        """Verify successful validation on valid parameters."""
        res = self.service.validate_request("click", {
            "button": "left",
            "click_count": 1,
            "target": {"name": "Submit", "role": "button"},
        })
        self.assertTrue(res.is_valid)
        self.assertEqual(len(res.errors), 0)
        self.assertEqual(res.action_type, AbstractActionType.CLICK)

    def test_04_validate_request_unknown_tool_fails_closed(self):
        """Verify unknown tool request fails closed immediately."""
        res = self.service.validate_request("super_hacker_tool", {"param": 1})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Unknown tool" in err for err in res.errors))

    def test_05_validate_request_missing_required_parameter(self):
        """Verify missing required parameter fails closed."""
        res = self.service.validate_request("launch_application", {})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("application_name" in err for err in res.errors))

    def test_06_validate_request_coordinate_policy_violation(self):
        """Verify physical coordinates are rejected at the tool service boundary."""
        res = self.service.validate_request("click", {
            "button": "left",
            "x": 500,
            "y": 300,
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("CoordinatePolicyViolation" in err for err in res.errors))

    def test_07_validate_request_security_policy_violation(self):
        """Verify dangerous code injection strings are rejected."""
        res = self.service.validate_request("type_text", {
            "text": "eval('import os; os.system(\"calc\")')",
        })
        self.assertFalse(res.is_valid)
        self.assertTrue(any("SecurityPolicyViolation" in err for err in res.errors))

    def test_08_create_action_from_tool_call_success(self):
        """Verify converting validated tool call into canonical AbstractAction."""
        action, err = self.service.create_action_from_tool_call(
            name="type_text",
            parameters={
                "text": "Hello World",
                "press_enter": True,
                "target": {"name": "Editor", "role": "edit"},
            },
            expected_effect="Text typed into editor",
            rationale="User requested typing",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(action)
        self.assertEqual(action.action_type, AbstractActionType.TYPE_TEXT)
        self.assertEqual(action.parameters.get("text"), "Hello World")
        self.assertTrue(action.parameters.get("press_enter"))
        self.assertIsNotNone(action.target)
        self.assertEqual(action.target.name, "Editor")
        self.assertEqual(action.target.role, "edit")
        self.assertEqual(action.expected_effect, "Text typed into editor")

    def test_09_create_action_from_tool_call_failure(self):
        """Verify validation errors fail closed and return (None, error_str)."""
        action, err = self.service.create_action_from_tool_call(
            name="click",
            parameters={"x": 100, "y": 200},  # Prohibited coords
        )
        self.assertIsNone(action)
        self.assertIsNotNone(err)
        self.assertIn("CoordinatePolicyViolation", err)

    def test_10_route_tool_call_to_candidate_plan(self):
        """Verify translating tool call to CandidatePlan for feasibility evaluation."""
        candidate, err = self.service.route_tool_call_to_candidate_plan(
            name="launch_application",
            parameters={"application_name": "notepad"},
            subgoal_id="sub_01",
            rationale="Launch notepad app",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.subgoal_id, "sub_01")
        self.assertIn(AbstractActionType.LAUNCH_APPLICATION, candidate.proposed_primitives)
        self.assertEqual(candidate.intent_strategy, "TOOL_CAPABILITY")

    def test_11_planner_integration_emits_plan_directive(self):
        """Verify full flow: Model Tool Call -> ToolService -> AbstractAction -> AgentPlanner -> PlanDirective."""
        planner = AgentPlanner()
        world_model = AgentWorldModel()
        objective = StructuredObjective(
            raw_prompt="Open Notepad",
            user_goal="Open Notepad",
            end_condition="notepad_opened",
            target_entities=["notepad"],
            constraints=[],
        )
        subgoal = SubObjective(
            sub_id="sub_launch",
            title="Launch Notepad",
            description="Launch Notepad via application launcher",
            target_entity="notepad",
        )

        directive, report, err = self.service.submit_to_planner(
            name="launch_application",
            parameters={"application_name": "notepad"},
            planner=planner,
            objective=objective,
            subgoal=subgoal,
            world_model=world_model,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(report)
        self.assertTrue(report.is_feasible)
        self.assertIsNotNone(directive)
        self.assertEqual(directive.subgoal_id, "sub_launch")
        self.assertIn(AbstractActionType.LAUNCH_APPLICATION, directive.preferred_primitives)

    def test_12_tool_service_contains_no_physical_execution(self):
        """Verify ToolService has zero execution methods and cannot execute physical actions."""
        forbidden_methods = {
            "execute", "invoke", "ainvoke", "dispatch", "run", "click", "type",
            "mouse_down", "key_press", "send_input", "shell",
        }
        service_attrs = set(dir(self.service))
        collisions = forbidden_methods.intersection(service_attrs)
        self.assertEqual(len(collisions), 0, f"ToolService must not contain execution methods: {collisions}")

    def test_13_ast_static_check_zero_execution_imports_in_tools_package(self):
        """Verify via AST that tools package NEVER imports execution controllers or Win32 APIs."""
        tools_dir = Path("src/orbit/runtime/tools")
        self.assertTrue(tools_dir.exists(), "src/orbit/runtime/tools must exist")

        forbidden_imports = {
            "PrimitiveExecutionController",
            "ctypes.windll",
            "ctypes.cdll",
            "SendInput",
            "win32api",
            "win32gui",
            "win32con",
            "PointerCapability",
            "KeyboardCapability",
            "WorkspaceCapability",
            "pyautogui",
            "subprocess",
            "os.system",
        }

        for py_file in tools_dir.glob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                code = f.read()

            tree = ast.parse(code, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_imports:
                            self.assertNotIn(
                                forbidden, alias.name,
                                f"Forbidden execution import '{forbidden}' found in {py_file}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for alias in node.names:
                        full = f"{mod}.{alias.name}" if mod else alias.name
                        for forbidden in forbidden_imports:
                            self.assertNotIn(
                                forbidden, full,
                                f"Forbidden execution import '{forbidden}' found in {py_file}"
                            )


if __name__ == "__main__":
    unittest.main()
