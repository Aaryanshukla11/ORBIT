"""Capability Executor Registry (M1.9 Component 2).

Maintains the authoritative runtime mapping from Capability ID to concrete CapabilityExecutor.
Enforces the fundamental architectural invariant:
Capability definition != Executable capability.
A capability is ONLY executable when an operational executor and all required adapters exist.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orbit.runtime.capabilities.execution.contracts import CapabilityExecutor
from orbit.runtime.capabilities.execution.executors.app_launch_executor import ApplicationLaunchExecutor
from orbit.runtime.capabilities.execution.executors.clipboard_paste_executor import ClipboardPasteExecutor
from orbit.runtime.capabilities.execution.executors.composite_executor import CompositeCapabilityExecutor
from orbit.runtime.capabilities.execution.executors.drawing_executor import DrawingExecutor
from orbit.runtime.capabilities.execution.executors.geometry_drawing_executor import GeometryDrawingExecutor
from orbit.runtime.capabilities.execution.executors.semantic_click_executor import SemanticClickExecutor
from orbit.runtime.capabilities.execution.executors.text_input_executor import TextInputExecutor
from orbit.runtime.capabilities.execution.executors.window_focus_executor import WindowFocusExecutor
from orbit.runtime.capabilities.execution.image_gen_provider import ImageGenerationProvider
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.targeting.locator import TargetLocator

logger = logging.getLogger(__name__)


class CapabilityExecutorRegistry:
    """Authoritative registry mapping Capability IDs to concrete CapabilityExecutor instances."""

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        register_defaults: bool = False,
    ) -> None:
        self._capability_registry = capability_registry or CapabilityRegistry()
        self._executors: Dict[str, CapabilityExecutor] = {}

    def register_executor(self, executor: CapabilityExecutor) -> None:
        """Register a concrete capability executor instance."""
        cid = executor.capability_id.upper()
        self._executors[cid] = executor
        logger.debug("[CapabilityExecutorRegistry] Registered executor for '%s' (available=%s)", cid, executor.is_available())

    def get_executor(self, capability_id: str) -> Optional[CapabilityExecutor]:
        """Retrieve the concrete executor for a capability ID if registered."""
        return self._executors.get(capability_id.upper())

    def is_executable(self, capability_id: str) -> bool:
        """Check if a capability is genuinely executable right now.

        Requires:
          1. Capability definition exists in CapabilityRegistry.
          2. Capability is marked available in metadata.
          3. A concrete CapabilityExecutor is registered in this executor registry.
          4. The executor reports is_available() == True (all required physical adapters present).
        """
        cid = capability_id.upper()
        cap_def = self._capability_registry.get(cid)
        if cap_def is None or not cap_def.is_available:
            return False

        executor = self.get_executor(cid)
        if executor is None:
            return False

        return executor.is_available()

    def list_executable_capabilities(self) -> List[str]:
        """Return list of capability IDs that are fully operational and executable right now."""
        return [cid for cid in self._executors.keys() if self.is_executable(cid)]

    @classmethod
    def create_default(
        cls,
        workspace: Optional[Any] = None,
        pointer: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        target_locator: Optional[TargetLocator] = None,
        image_gen_provider: Optional[ImageGenerationProvider] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
    ) -> CapabilityExecutorRegistry:
        """Factory creating an executor registry wired with standard production adapters."""
        reg = cls(capability_registry=capability_registry)

        # 1. LAUNCH_APPLICATION
        reg.register_executor(ApplicationLaunchExecutor(workspace=workspace))

        # 2. FOCUS_WINDOW
        reg.register_executor(WindowFocusExecutor(workspace=workspace))

        # 3. CLICK (Canonical) & CLICK_ELEMENT (Legacy)
        reg.register_executor(SemanticClickExecutor(pointer=pointer, target_locator=target_locator, capability_id="CLICK"))
        reg.register_executor(SemanticClickExecutor(pointer=pointer, target_locator=target_locator, capability_id="CLICK_ELEMENT"))

        # 4. TYPE_TEXT
        reg.register_executor(TextInputExecutor(keyboard=keyboard))

        # 5. DRAW_STROKES (Canonical) & DRAW_BASIC_GEOMETRY
        reg.register_executor(DrawingExecutor(pointer=pointer))
        reg.register_executor(GeometryDrawingExecutor(pointer=pointer))

        # 6. CLIPBOARD_PASTE
        reg.register_executor(ClipboardPasteExecutor(keyboard=keyboard))

        # 7. IMAGE_GENERATE_AND_INSERT
        reg.register_executor(
            CompositeCapabilityExecutor(
                image_gen_provider=image_gen_provider,
                keyboard=keyboard,
                workspace=workspace,
            )
        )

        return reg
