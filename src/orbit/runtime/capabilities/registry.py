"""Capability Registry managing available agent capabilities and their boundaries."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from orbit.runtime.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilityLimitation,
)

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Central repository of registered agent capabilities and their operational limitations."""

    def __init__(self, register_defaults: bool = True) -> None:
        self._capabilities: Dict[str, Capability] = {}
        if register_defaults:
            self._register_default_capabilities()

    def register(self, capability: Capability) -> None:
        """Register a new or updated capability."""
        self._capabilities[capability.capability_id] = capability
        logger.debug("Registered capability: %s [%s]", capability.capability_id, capability.category.value)

    def get(self, capability_id: str) -> Optional[Capability]:
        """Retrieve capability by identifier."""
        return self._capabilities.get(capability_id)

    def list_all(self) -> List[Capability]:
        """Return all registered capabilities."""
        return list(self._capabilities.values())

    def list_available(self) -> List[Capability]:
        """Return currently available (operational) capabilities."""
        return [c for c in self._capabilities.values() if c.is_available]

    def find_by_category(self, category: CapabilityCategory) -> List[Capability]:
        """List capabilities within a category."""
        return [c for c in self._capabilities.values() if c.category == category]

    def find_by_goal_type(self, goal_type: str) -> List[Capability]:
        """Find capabilities declaring support for a specific goal type."""
        gt_l = goal_type.strip().lower()
        return [
            c for c in self._capabilities.values()
            if any(gt.lower() == gt_l or gt.lower() in gt_l for gt in c.supported_goal_types)
        ]

    def _register_default_capabilities(self) -> None:
        """Register the built-in standard capabilities of ORBIT."""

        # 1. Launch Application
        self.register(
            Capability(
                capability_id="LAUNCH_APPLICATION",
                name="Launch Desktop Application",
                description="Launch Windows desktop applications via ShellExecute, UWP protocol, or Start menu",
                category=CapabilityCategory.DESKTOP_CONTROL,
                supported_goal_types=["open", "launch", "start", "run"],
                supported_subtypes=["notepad", "calc", "calculator", "paint", "mspaint", "chrome", "browser", "explorer"],
                limitations=[
                    CapabilityLimitation(
                        description="Cannot launch non-existent, uninstalled, or restricted administrative executables without elevation",
                        unsupported_patterns=["uninstall", "format c:", "del /s", "reboot"],
                        severity="HARD_LIMIT",
                    )
                ],
                reliability_score=0.98,
                execution_cost=1.2,
                verification_methods=["WINDOW_FOCUS_OR_STATE"],
                is_available=True,
            )
        )

        # 2. Focus Window
        self.register(
            Capability(
                capability_id="FOCUS_WINDOW",
                name="Focus Window",
                description="Bring target HWND or window title to the foreground and attach input thread",
                category=CapabilityCategory.DESKTOP_CONTROL,
                supported_goal_types=["focus", "switch_to", "activate"],
                limitations=[],
                reliability_score=0.96,
                execution_cost=0.5,
                verification_methods=["WINDOW_FOCUS_OR_STATE"],
                is_available=True,
            )
        )

        # 3. Type Text
        self.register(
            Capability(
                capability_id="TYPE_TEXT",
                name="Type Text into Focused Control",
                description="Input ASCII and Unicode text into active document or text box via keystroke stream or clipboard",
                category=CapabilityCategory.INPUT,
                supported_goal_types=["type", "write", "input", "enter_text"],
                limitations=[
                    CapabilityLimitation(
                        description="Cannot type into disabled or read-only controls",
                        unsupported_patterns=["read only", "disabled input"],
                        severity="HARD_LIMIT",
                    )
                ],
                reliability_score=0.95,
                execution_cost=0.8,
                verification_methods=["UIA_STATE", "OCR_EXACT", "WIN32_TEXT"],
                is_available=True,
            )
        )

        # 4. Click Element
        self.register(
            Capability(
                capability_id="CLICK_ELEMENT",
                name="Click UI Element",
                description="Move cursor to grounded UI element and dispatch mouse click",
                category=CapabilityCategory.INPUT,
                supported_goal_types=["click", "press", "select"],
                limitations=[],
                reliability_score=0.92,
                execution_cost=0.6,
                verification_methods=["UIA_STATE", "PIXEL_DIFF"],
                is_available=True,
            )
        )

        # 5. Draw Basic Geometry
        self.register(
            Capability(
                capability_id="DRAW_BASIC_GEOMETRY",
                name="Draw Basic Geometric Shapes",
                description="Render clean geometric primitives (squares, rectangles, circles, cubes, stars, lines) via discrete coordinate trajectories",
                category=CapabilityCategory.CREATIVE_VISUAL,
                supported_goal_types=["draw", "sketch_geometry", "render_shape"],
                supported_subtypes=[
                    "cube",
                    "square",
                    "circle",
                    "rectangle",
                    "triangle",
                    "cube_3d",
                    "star",
                    "line",
                    "polygon",
                    "oval",
                    "box",
                ],
                limitations=[
                    CapabilityLimitation(
                        description=(
                            "Does NOT reliably support realistic portraits, human faces, character illustrations, "
                            "figures, organic shapes, animals, or complex artistic scenes."
                        ),
                        unsupported_patterns=[
                            "portrait",
                            "face",
                            "boy",
                            "girl",
                            "man",
                            "woman",
                            "person",
                            "human",
                            "dog",
                            "cat",
                            "animal",
                            "landscape",
                            "scenery",
                            "painting",
                            "realistic",
                            "photograph",
                        ],
                        severity="HARD_LIMIT",
                    )
                ],
                reliability_score=0.92,
                execution_cost=1.5,
                verification_methods=["PIXEL_DIFF", "GEOMETRIC_CONTOUR"],
                is_available=True,
            )
        )

        # 6. Draw Freeform Strokes
        self.register(
            Capability(
                capability_id="DRAW_FREEFORM_STROKES",
                name="Draw Freeform Gestural Strokes",
                description="Dispatch continuous mouse-down trajectory points for rough sketching or scribbling",
                category=CapabilityCategory.CREATIVE_VISUAL,
                supported_goal_types=["draw_freeform", "scribble", "doodle"],
                supported_subtypes=["doodle", "scribble", "rough_sketch", "signature"],
                limitations=[
                    CapabilityLimitation(
                        description=(
                            "Does NOT reliably produce portrait-quality facial features, detailed anatomies, "
                            "or recognizable human likenesses."
                        ),
                        unsupported_patterns=[
                            "portrait",
                            "photorealistic",
                            "boy portrait",
                            "girl portrait",
                            "human likeness",
                        ],
                        severity="HARD_LIMIT",
                    )
                ],
                reliability_score=0.75,
                execution_cost=2.0,
                verification_methods=["PIXEL_DIFF"],
                is_available=True,
            )
        )

        # 7. Image Generate and Insert
        self.register(
            Capability(
                capability_id="IMAGE_GENERATE_AND_INSERT",
                name="Generate Image and Insert into Canvas",
                description="Generate visual artwork (portraits, complex scenes) via image generation model and paste into Paint/document",
                category=CapabilityCategory.CREATIVE_VISUAL,
                supported_goal_types=["draw", "create_image", "insert_artwork", "generate_visual"],
                supported_subtypes=[
                    "portrait",
                    "boy",
                    "girl",
                    "person",
                    "face",
                    "dog",
                    "cat",
                    "landscape",
                    "artwork",
                    "scenery",
                ],
                limitations=[],
                reliability_score=0.90,
                execution_cost=4.0,
                verification_methods=["SEMANTIC_VISION", "PIXEL_DIFF"],
                # Marked False by default until an image generation provider is wired in the runtime
                is_available=False,
            )
        )

        # 8. Clipboard Paste
        self.register(
            Capability(
                capability_id="CLIPBOARD_PASTE",
                name="Paste from Clipboard",
                description="Send Ctrl+V to paste current clipboard bitmap or text into active canvas or editor",
                category=CapabilityCategory.INPUT,
                supported_goal_types=["paste", "clipboard_insert"],
                limitations=[],
                reliability_score=0.95,
                execution_cost=0.5,
                verification_methods=["UIA_STATE", "PIXEL_DIFF"],
                is_available=True,
            )
        )
