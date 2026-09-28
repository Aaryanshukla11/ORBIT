"""ORBIT Tool Registry Subsystem.

Provides centralized registration, discovery, and schema exposition for all model-facing capabilities.

Architectural Invariants:
1. Registry != Execution Engine.
2. The registry ONLY stores, organizes, and exposes ToolSchema metadata.
3. Contains ZERO executable callbacks, physical action calls, or Win32 API invocations.
4. Pre-populated with ORBIT's canonical Tier 1-3 primitives and control signals.
5. Rejects duplicate registrations unless allow_override=True.
6. Does NOT mutate WorldModel or bypass AgentPlanner / PrimitiveValidator.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Union

from orbit.runtime.agent.contracts import (
    AbortTaskParams,
    AbstractActionType,
    ClickParams,
    CompleteGoalParams,
    DoubleClickParams,
    DragParams,
    DrawStrokesParams,
    FocusWindowParams,
    LaunchApplicationParams,
    RightClickParams,
    ScrollParams,
    SelectOptionParams,
    SendHotkeyParams,
    TypeTextParams,
    WaitParams,
)
from orbit.runtime.tools.schema import ToolCategory, ToolSchema

logger = logging.getLogger(__name__)

# Valid tool name identifier pattern (alphanumeric, underscores, lowercase preferred)
VALID_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$")


class DuplicateToolRegistrationError(ValueError):
    """Raised when registering a tool whose name conflicts with an existing registration."""
    pass


class InvalidToolNameError(ValueError):
    """Raised when a tool name violates naming structure invariants."""
    pass


class ToolRegistry:
    """Registry maintaining active ToolSchema descriptors for AI model consumption.

    Enforces:
    - Name format validation.
    - Duplicate registration prevention.
    - Normalized case-insensitive lookup.
    - Clean schema exports.
    """

    def __init__(self, auto_register_builtins: bool = True) -> None:
        self._tools: Dict[str, ToolSchema] = {}
        if auto_register_builtins:
            self.register_builtin_primitives()

    def _normalize_name(self, name: str) -> str:
        """Normalize tool name for lookup (lowercase, stripped)."""
        return name.strip().lower()

    def register(self, tool: ToolSchema, allow_override: bool = False) -> None:
        """Register a capability definition.

        Args:
            tool: ToolSchema descriptor to register.
            allow_override: If False (default), raises DuplicateToolRegistrationError on collision.
        """
        if not tool or not tool.name:
            raise InvalidToolNameError("Tool name must be a non-empty string.")

        if not VALID_TOOL_NAME_PATTERN.match(tool.name):
            raise InvalidToolNameError(
                f"Invalid tool name '{tool.name}'. Must start with a letter and contain only alphanumeric, '-', or '_'."
            )

        norm_name = self._normalize_name(tool.name)

        if norm_name in self._tools and not allow_override:
            raise DuplicateToolRegistrationError(
                f"Tool '{tool.name}' is already registered. Set allow_override=True to replace it."
            )

        self._tools[norm_name] = tool
        logger.debug("[TOOL REGISTRY] Registered tool '%s' (category=%s)", tool.name, tool.category.value)

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry by name."""
        norm_name = self._normalize_name(name)
        if norm_name in self._tools:
            del self._tools[norm_name]
            logger.debug("[TOOL REGISTRY] Unregistered tool '%s'", name)
            return True
        return False

    def get(self, name: str) -> Optional[ToolSchema]:
        """Retrieve a registered ToolSchema by name (case-insensitive)."""
        if not name:
            return None
        return self._tools.get(self._normalize_name(name))

    def has(self, name: str) -> bool:
        """Check if a tool exists in the registry."""
        if not name:
            return False
        return self._normalize_name(name) in self._tools

    def list_tools(self, category: Optional[Union[ToolCategory, str]] = None) -> List[ToolSchema]:
        """Return all registered ToolSchema instances, optionally filtered by category."""
        if category is None:
            return list(self._tools.values())

        cat_val = category.value if isinstance(category, ToolCategory) else str(category)
        return [t for t in self._tools.values() if t.category.value == cat_val]

    def list_schemas(
        self,
        format: str = "openai",
        category: Optional[Union[ToolCategory, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of JSON schemas for all registered capabilities in specified model format."""
        tools = self.list_tools(category=category)
        return [t.to_json_schema(format=format) for t in tools]

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()

    def count(self) -> int:
        """Return the count of registered capabilities."""
        return len(self._tools)

    def register_builtin_primitives(self) -> None:
        """Populate registry with standard ORBIT canonical primitive schemas."""
        builtins: List[ToolSchema] = [
            # ── Tier 1: Physical Computer Primitives ──
            ToolSchema.from_pydantic(
                name="click",
                description="Click a user interface element identified by its semantic target.",
                model=ClickParams,
                action_type=AbstractActionType.CLICK,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),
            ToolSchema.from_pydantic(
                name="double_click",
                description="Double click a UI element identified by its semantic target.",
                model=DoubleClickParams,
                action_type=AbstractActionType.DOUBLE_CLICK,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),
            ToolSchema.from_pydantic(
                name="right_click",
                description="Right click a UI element identified by its semantic target to open context menu.",
                model=RightClickParams,
                action_type=AbstractActionType.RIGHT_CLICK,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),
            ToolSchema.from_pydantic(
                name="type_text",
                description="Type textual keyboard input into an editable semantic target.",
                model=TypeTextParams,
                action_type=AbstractActionType.TYPE_TEXT,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),
            ToolSchema.from_pydantic(
                name="send_hotkey",
                description="Send a keyboard shortcut or key combination (e.g. 'ctrl+s', 'alt+f4', 'enter').",
                model=SendHotkeyParams,
                action_type=AbstractActionType.SEND_HOTKEY,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=False,
            ),
            ToolSchema.from_pydantic(
                name="launch_application",
                description="Launch a desktop application by executable or known name (e.g. 'notepad', 'calc', 'edge').",
                model=LaunchApplicationParams,
                action_type=AbstractActionType.LAUNCH_APPLICATION,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=False,
            ),
            ToolSchema.from_pydantic(
                name="focus_window",
                description="Bring an application window to the foreground by title or process name.",
                model=FocusWindowParams,
                action_type=AbstractActionType.FOCUS_WINDOW,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=False,
            ),
            ToolSchema.from_pydantic(
                name="scroll",
                description="Scroll the active document or container up, down, left, or right.",
                model=ScrollParams,
                action_type=AbstractActionType.SCROLL,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),
            ToolSchema.from_pydantic(
                name="drag",
                description="Drag from source semantic target to destination semantic target.",
                model=DragParams,
                action_type=AbstractActionType.DRAG,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),
            ToolSchema.from_pydantic(
                name="wait",
                description="Wait for a specified duration in seconds for UI animation or settlement.",
                model=WaitParams,
                action_type=AbstractActionType.WAIT,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=False,
            ),
            ToolSchema.from_pydantic(
                name="draw_strokes",
                description="Render geometric vector strokes or sketches onto the active canvas control.",
                model=DrawStrokesParams,
                action_type=AbstractActionType.DRAW_STROKES,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),
            ToolSchema.from_pydantic(
                name="select_option",
                description="Select an option from a combo box or dropdown menu by label.",
                model=SelectOptionParams,
                action_type=AbstractActionType.SELECT_OPTION,
                category=ToolCategory.COMPUTER_PRIMITIVE,
                include_target=True,
            ),

            # ── Tier 2: Observation Primitives ──
            ToolSchema(
                name="screenshot",
                description="Capture a multimodal screenshot of the active desktop.",
                action_type=AbstractActionType.SCREENSHOT,
                category=ToolCategory.OBSERVATION_PRIMITIVE,
                input_schema={"type": "object", "properties": {}},
            ),
            ToolSchema(
                name="read_ui_element",
                description="Inspect the accessibility properties and hierarchy of target UI element.",
                action_type=AbstractActionType.READ_UI_ELEMENT,
                category=ToolCategory.OBSERVATION_PRIMITIVE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "object",
                            "description": "Semantic target to inspect",
                            "properties": {
                                "name": {"type": "string"},
                                "role": {"type": "string"},
                            },
                        }
                    },
                },
            ),
            ToolSchema(
                name="read_ocr_text",
                description="Perform on-screen Optical Character Recognition to extract visible text tokens.",
                action_type=AbstractActionType.READ_OCR_TEXT,
                category=ToolCategory.OBSERVATION_PRIMITIVE,
                input_schema={"type": "object", "properties": {}},
            ),

            # ── Tier 3: Environment Interfaces ──
            ToolSchema(
                name="file_read",
                description="Read contents from a file path on disk.",
                action_type=AbstractActionType.FILE_READ,
                category=ToolCategory.ENVIRONMENT_INTERFACE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or relative file path to read"}
                    },
                    "required": ["path"],
                },
                required_parameters=["path"],
            ),
            ToolSchema(
                name="file_write",
                description="Write content to a file on disk.",
                action_type=AbstractActionType.FILE_WRITE,
                category=ToolCategory.ENVIRONMENT_INTERFACE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to write"},
                        "content": {"type": "string", "description": "Text content to persist"},
                    },
                    "required": ["path", "content"],
                },
                required_parameters=["path", "content"],
                is_destructive=True,
            ),
            ToolSchema(
                name="browser_navigate",
                description="Navigate browser to target URL.",
                action_type=AbstractActionType.BROWSER_NAVIGATE,
                category=ToolCategory.ENVIRONMENT_INTERFACE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target website URL"}
                    },
                    "required": ["url"],
                },
                required_parameters=["url"],
            ),
            ToolSchema(
                name="spreadsheet_read",
                description="Read data from a spreadsheet document.",
                action_type=AbstractActionType.SPREADSHEET_READ,
                category=ToolCategory.ENVIRONMENT_INTERFACE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Spreadsheet file path"},
                        "sheet_name": {"type": "string", "description": "Optional worksheet name"},
                    },
                    "required": ["path"],
                },
                required_parameters=["path"],
            ),
            ToolSchema(
                name="spreadsheet_write",
                description="Write data or formulas into a spreadsheet document.",
                action_type=AbstractActionType.SPREADSHEET_WRITE,
                category=ToolCategory.ENVIRONMENT_INTERFACE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Target spreadsheet file path"},
                        "cells": {"type": "object", "description": "Mapping of cell coordinates to values/formulas"},
                    },
                    "required": ["path"],
                },
                required_parameters=["path"],
                is_destructive=True,
            ),

            # ── Control Signals ──
            ToolSchema.from_pydantic(
                name="complete_goal",
                description="Signal that the user's objective has been fully achieved with verified evidence.",
                model=CompleteGoalParams,
                action_type=AbstractActionType.COMPLETE_GOAL,
                category=ToolCategory.CONTROL_SIGNAL,
                include_target=False,
            ),
            ToolSchema.from_pydantic(
                name="abort_task",
                description="Signal that the user's objective cannot be achieved with diagnostic rationale.",
                model=AbortTaskParams,
                action_type=AbstractActionType.ABORT_TASK,
                category=ToolCategory.CONTROL_SIGNAL,
                include_target=False,
            ),
        ]

        for tool in builtins:
            self.register(tool, allow_override=True)

    def register_from_environment_providers(self, provider_registry: Any) -> int:
        """Register or enrich capability schemas from an EnvironmentProviderRegistry.

        Exposes verified operational environment provider capabilities without taking
        ownership of their execution.
        """
        if not provider_registry or not hasattr(provider_registry, "get_all_registered_providers"):
            return 0

        registered_count = 0
        from orbit.runtime.agent.contracts import TIER3_ENVIRONMENT_INTERFACES

        for primitive in TIER3_ENVIRONMENT_INTERFACES:
            providers = provider_registry.get_all_registered_providers(primitive)
            if not providers:
                continue

            tool_name = primitive.value.lower()
            existing = self.get(tool_name)
            desc = existing.description if existing else f"Environment primitive {primitive.value}"
            features: Set[str] = set()
            for p in providers:
                features.update(getattr(p, "supported_features", []))

            enriched_desc = f"{desc} (Supported features: {', '.join(sorted(features))})" if features else desc

            schema = ToolSchema(
                name=tool_name,
                description=enriched_desc,
                action_type=primitive,
                category=ToolCategory.ENVIRONMENT_INTERFACE,
                input_schema=existing.input_schema if existing else {"type": "object", "properties": {}},
                required_parameters=existing.required_parameters if existing else [],
            )
            self.register(schema, allow_override=True)
            registered_count += 1

        return registered_count
