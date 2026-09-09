"""Capability Composition Engine combining atomic capabilities into composite workflows."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from orbit.runtime.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilitySource,
    GoalRequirement,
    GoalRequirementSet,
    StrategyStage,
)

logger = logging.getLogger(__name__)


class CompositeCapability(Capability):
    """A multi-capability operational workflow composed of dependent primitive capabilities."""

    composed_from: List[str] = []
    composition_stages: List[StrategyStage] = []
    composition_rule: str = ""

    def is_viable_with(self, available_capabilities: Set[str]) -> bool:
        """Evaluate whether all required constituent sub-capabilities are currently operational."""
        # For composite dependencies with alternative providers (e.g. 'ENV_MODEL_IMAGE_GEN|IMAGE_GENERATE_AND_INSERT')
        for dep in self.composed_from:
            if "|" in dep:
                options = dep.split("|")
                if not any(opt.strip() in available_capabilities for opt in options):
                    return False
            else:
                if dep not in available_capabilities:
                    return False
        return True

    def get_missing_constituents(self, available_capabilities: Set[str]) -> List[str]:
        """Return constituent capability IDs that are absent."""
        missing = []
        for dep in self.composed_from:
            if "|" in dep:
                options = dep.split("|")
                if not any(opt.strip() in available_capabilities for opt in options):
                    missing.append(options[0].strip())
            else:
                if dep not in available_capabilities:
                    missing.append(dep)
        return missing


class CapabilityCompositionEngine:
    """Discovers, validates, and manages multi-capability composite workflows."""

    def __init__(self) -> None:
        self._composite_templates: List[CompositeCapability] = []
        self._register_default_composites()

    def register_composite(self, composite: CompositeCapability) -> None:
        """Register a new composite workflow definition."""
        self._composite_templates.append(composite)

    def list_composites(self) -> List[CompositeCapability]:
        """Return all known composite capability templates."""
        return list(self._composite_templates)

    def find_compositions_for_requirements(
        self,
        requirements: GoalRequirementSet,
        available_cap_ids: Set[str],
    ) -> List[CompositeCapability]:
        """Identify which composite workflows can satisfy the requested requirements."""
        matches: List[CompositeCapability] = []

        for comp in self._composite_templates:
            # Check domain matching
            if comp.metadata.get("domain") and comp.metadata.get("domain") != requirements.target_domain:
                continue

            # Check fidelity matching
            target_fid = requirements.required_fidelity
            comp_fid = comp.metadata.get("fidelity_level", "STANDARD")
            if target_fid == "HIGH_FIDELITY_SEMANTIC" and comp_fid == "PRIMITIVE":
                continue

            matches.append(comp)

        return matches

    def _register_default_composites(self) -> None:
        """Register built-in composite workflows."""

        # 1. High-Fidelity Generative Artwork & Canvas Insertion
        self.register_composite(
            CompositeCapability(
                capability_id="COMPOSITE_IMAGE_GEN_AND_INSERT",
                name="Generative Image Synthesis & Canvas Insertion",
                description="Synthesize high-fidelity visual artwork via generative model and insert into application canvas via clipboard",
                category=CapabilityCategory.CREATIVE_VISUAL,
                source=CapabilitySource.COMPOSITE,
                composed_from=["IMAGE_GENERATE_AND_INSERT|ENV_MODEL_IMAGE_GEN", "CLIPBOARD_PASTE"],
                composition_stages=[
                    StrategyStage(
                        stage_index=0,
                        name="GENERATE_SEMANTIC_IMAGE",
                        capability_id="IMAGE_GENERATE_AND_INSERT",
                        description="Query generative model to synthesize pixel representation of requested semantic subject",
                        expected_outcome="bitmap_generated_in_memory",
                    ),
                    StrategyStage(
                        stage_index=1,
                        name="STAGE_TO_CLIPBOARD",
                        capability_id="CLIPBOARD_PASTE",
                        description="Place synthesized bitmap onto system clipboard buffer",
                        expected_outcome="clipboard_has_bitmap",
                    ),
                    StrategyStage(
                        stage_index=2,
                        name="FOCUS_TARGET_CANVAS",
                        capability_id="FOCUS_WINDOW",
                        description="Bring Paint drawing canvas to foreground",
                        expected_outcome="paint_canvas_focused",
                    ),
                    StrategyStage(
                        stage_index=3,
                        name="PASTE_AND_ANCHOR",
                        capability_id="CLIPBOARD_PASTE",
                        description="Send Ctrl+V to render clipboard bitmap into active canvas document",
                        expected_outcome="canvas_contains_pasted_artwork",
                    ),
                ],
                supported_goal_types=["draw", "create_image", "portrait", "sketch_artwork"],
                supported_subtypes=["portrait", "boy", "girl", "person", "face", "scene", "animal", "landscape"],
                reliability_score=0.92,
                execution_cost=3.5,
                metadata={"domain": "creative_drawing", "fidelity_level": "HIGH_FIDELITY_SEMANTIC"},
                is_available=True,
            )
        )

        # 2. Browser-Assisted Web Generation & Import
        self.register_composite(
            CompositeCapability(
                capability_id="COMPOSITE_BROWSER_WEB_IMPORT",
                name="Browser-Assisted Web Generation & Import",
                description="Launch web browser, navigate to generative tool, and import resulting image into canvas",
                category=CapabilityCategory.CREATIVE_VISUAL,
                source=CapabilitySource.COMPOSITE,
                composed_from=["ENV_APP_CHROME|ENV_APP_EDGE", "LAUNCH_APPLICATION", "FOCUS_WINDOW", "CLIPBOARD_PASTE"],
                composition_stages=[
                    StrategyStage(
                        stage_index=0,
                        name="LAUNCH_BROWSER_TOOL",
                        capability_id="LAUNCH_APPLICATION",
                        description="Open web browser with image synthesis tool",
                        expected_outcome="browser_opened_to_tool",
                    ),
                    StrategyStage(
                        stage_index=1,
                        name="COPY_WEB_RESULT",
                        capability_id="CLIPBOARD_PASTE",
                        description="Copy generated web visual content to clipboard",
                        expected_outcome="clipboard_has_web_image",
                    ),
                    StrategyStage(
                        stage_index=2,
                        name="INSERT_INTO_PAINT",
                        capability_id="CLIPBOARD_PASTE",
                        description="Paste visual content into Paint document",
                        expected_outcome="canvas_contains_image",
                    ),
                ],
                supported_goal_types=["draw", "portrait", "search_image"],
                reliability_score=0.85,
                execution_cost=5.0,
                metadata={"domain": "creative_drawing", "fidelity_level": "HIGH_FIDELITY_SEMANTIC"},
                is_available=True,
            )
        )

        # 3. Geometric Vector Primitive Drawing
        self.register_composite(
            CompositeCapability(
                capability_id="COMPOSITE_GEOMETRIC_DRAWING",
                name="Geometric Coordinate Trajectory Drawing",
                description="Launch host drawing application, focus canvas surface, and dispatch discrete geometric coordinates",
                category=CapabilityCategory.CREATIVE_VISUAL,
                source=CapabilitySource.COMPOSITE,
                composed_from=["LAUNCH_APPLICATION", "FOCUS_WINDOW", "DRAW_BASIC_GEOMETRY"],
                composition_stages=[
                    StrategyStage(
                        stage_index=0,
                        name="LAUNCH_PAINT",
                        capability_id="LAUNCH_APPLICATION",
                        description="Launch Microsoft Paint process",
                        expected_outcome="paint_running",
                    ),
                    StrategyStage(
                        stage_index=1,
                        name="FOCUS_CANVAS",
                        capability_id="FOCUS_WINDOW",
                        description="Bring Paint drawing canvas to foreground",
                        expected_outcome="canvas_ready_for_strokes",
                    ),
                    StrategyStage(
                        stage_index=2,
                        name="DRAW_VECTOR_CONTOUR",
                        capability_id="DRAW_BASIC_GEOMETRY",
                        description="Dispatch simulated mouse waypoints for geometric shape",
                        expected_outcome="canvas_modified_with_shape",
                    ),
                ],
                supported_goal_types=["draw", "render_shape"],
                supported_subtypes=["cube", "square", "circle", "rectangle", "triangle", "star", "box"],
                reliability_score=0.95,
                execution_cost=1.5,
                metadata={"domain": "creative_drawing", "fidelity_level": "PRIMITIVE"},
                is_available=True,
            )
        )

        # 4. Deterministic Text Entry & Document Creation
        self.register_composite(
            CompositeCapability(
                capability_id="COMPOSITE_TEXT_DOCUMENT_CREATION",
                name="Text Document Creation & Input",
                description="Launch editor, focus input buffer, and input exact character stream",
                category=CapabilityCategory.DOCUMENT,
                source=CapabilitySource.COMPOSITE,
                composed_from=["LAUNCH_APPLICATION", "FOCUS_WINDOW", "TYPE_TEXT"],
                composition_stages=[
                    StrategyStage(
                        stage_index=0,
                        name="LAUNCH_EDITOR",
                        capability_id="LAUNCH_APPLICATION",
                        description="Launch text editor",
                        expected_outcome="editor_running",
                    ),
                    StrategyStage(
                        stage_index=1,
                        name="FOCUS_EDIT_CONTROL",
                        capability_id="FOCUS_WINDOW",
                        description="Focus document edit buffer",
                        expected_outcome="editor_focused",
                    ),
                    StrategyStage(
                        stage_index=2,
                        name="INPUT_TEXT_STREAM",
                        capability_id="TYPE_TEXT",
                        description="Type literal string into document",
                        expected_outcome="text_entered_in_buffer",
                    ),
                ],
                supported_goal_types=["type", "write", "create_document"],
                reliability_score=0.96,
                execution_cost=1.0,
                metadata={"domain": "document_editing", "fidelity_level": "STANDARD"},
                is_available=True,
            )
        )
