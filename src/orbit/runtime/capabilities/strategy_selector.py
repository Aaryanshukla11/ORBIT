"""Strategy Selector generating, evaluating, and ranking candidate execution strategies."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from orbit.runtime.capabilities.composition import CapabilityCompositionEngine, CompositeCapability
from orbit.runtime.capabilities.environment_discovery import EnvironmentCapabilityDiscovery
from orbit.runtime.capabilities.matcher import CapabilityMatchReport, CapabilityMatcher
from orbit.runtime.capabilities.models import (
    CapabilityGapReport,
    GoalRequirementSet,
    StrategyOption,
    StrategySelectionResult,
    StrategyStage,
)
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
from orbit.runtime.cognitive.models import StructuredObjective

logger = logging.getLogger(__name__)


class StrategySelector:
    """Evaluates multiple candidate execution strategies and ranks them by feasibility and semantic coverage."""

    MINIMUM_EXECUTABLE_PROBABILITY = 0.50
    MINIMUM_SEMANTIC_COVERAGE = 0.60

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        matcher: Optional[CapabilityMatcher] = None,
        environment_discovery: Optional[EnvironmentCapabilityDiscovery] = None,
        composition_engine: Optional[CapabilityCompositionEngine] = None,
        requirement_extractor: Optional[GoalRequirementExtractor] = None,
    ) -> None:
        self._registry = registry or CapabilityRegistry()
        self._matcher = matcher or CapabilityMatcher(registry=self._registry)
        self._environment_discovery = environment_discovery or EnvironmentCapabilityDiscovery()
        self._composition_engine = composition_engine or CapabilityCompositionEngine()
        self._requirement_extractor = requirement_extractor or GoalRequirementExtractor()

    def select_strategy(
        self,
        objective: StructuredObjective,
        match_report: Optional[CapabilityMatchReport] = None,
        requirements: Optional[GoalRequirementSet] = None,
    ) -> StrategySelectionResult:
        """Formulate, score, and select the optimal execution strategy for an objective."""
        req_set = requirements or self._requirement_extractor.extract_requirements(objective)
        prompt = getattr(objective, "raw_prompt", str(objective.user_goal or "")).strip()
        p_lower = prompt.lower()
        action_type = str(objective.parameters.get("action_type", "")).lower()

        # Discover dynamic environment capabilities without hallucinating
        env_caps = self._environment_discovery.discover_capabilities()
        for ec in env_caps:
            if not self._registry.get(ec.capability_id):
                self._registry.register(ec)

        available_cap_ids: Set[str] = {c.capability_id for c in self._registry.list_available()}

        candidates: List[StrategyOption] = []

        # -------------------------------------------------------------
        # Domain 1: Creative / Visual Content Strategies
        # -------------------------------------------------------------
        if req_set.target_domain == "creative_drawing" or action_type == "draw" or "draw" in p_lower:
            is_high_fidelity = req_set.required_fidelity == "HIGH_FIDELITY_SEMANTIC"

            # Strategy 1: Primitive Geometric Vector Drawing
            geom_cap = self._registry.get("DRAW_BASIC_GEOMETRY")
            is_geom_avail = bool(geom_cap and geom_cap.is_available)
            geom_coverage = 0.05 if is_high_fidelity else 0.95
            geom_prob = (geom_cap.reliability_score if geom_cap else 0.90) * geom_coverage if is_geom_avail else 0.0

            geom_rejection = (
                "Semantic adequacy failure: Primitive geometric strokes cannot reliably satisfy "
                f"high-fidelity semantic request ('{prompt}')."
                if is_high_fidelity else None
            )

            candidates.append(
                StrategyOption(
                    strategy_id="STRAT_GEOMETRIC_PRIMITIVES",
                    name="Geometric Primitive Vector Drawing",
                    description="Draw geometric coordinate trajectories directly on application canvas",
                    required_capabilities=["DRAW_BASIC_GEOMETRY", "FOCUS_WINDOW"],
                    stages=[
                        StrategyStage(
                            stage_index=0,
                            name="FOCUS_CANVAS",
                            capability_id="FOCUS_WINDOW",
                            description="Focus drawing canvas",
                            expected_outcome="canvas_active",
                        ),
                        StrategyStage(
                            stage_index=1,
                            name="DRAW_STROKES",
                            capability_id="DRAW_BASIC_GEOMETRY",
                            description="Dispatch simulated geometric coordinates",
                            expected_outcome="geometric_contour_rendered",
                        ),
                    ],
                    estimated_success_probability=geom_prob,
                    semantic_goal_coverage=geom_coverage,
                    risk_level="HIGH" if is_high_fidelity else "LOW",
                    is_available=is_geom_avail,
                    rejection_reason=geom_rejection,
                    rationale="Reliable for basic geometric shapes (cube, circle, square); disqualified for portraits.",
                )
            )

            # Strategy 2: Composite Generative Image Synthesis & Canvas Insertion
            img_gen_avail = "ENV_MODEL_IMAGE_GEN" in available_cap_ids or "IMAGE_GENERATE_AND_INSERT" in available_cap_ids
            paste_avail = "CLIPBOARD_PASTE" in available_cap_ids
            strat2_avail = img_gen_avail and paste_avail
            strat2_missing = []
            if not img_gen_avail:
                strat2_missing.append("IMAGE_GENERATE_AND_INSERT")
            if not paste_avail:
                strat2_missing.append("CLIPBOARD_PASTE")

            strat2_coverage = 0.95
            strat2_prob = 0.92 if strat2_avail else 0.0
            strat2_rejection = (
                f"Missing required capabilities: {', '.join(strat2_missing)}"
                if not strat2_avail else None
            )

            candidates.append(
                StrategyOption(
                    strategy_id="STRAT_IMAGE_GEN_AND_INSERT",
                    name="Generative AI Image Synthesis & Clipboard Insertion",
                    description="Synthesize semantic image using generative AI provider and paste into target canvas",
                    required_capabilities=["IMAGE_GENERATE_AND_INSERT", "CLIPBOARD_PASTE", "FOCUS_WINDOW"],
                    stages=[
                        StrategyStage(
                            stage_index=0,
                            name="SYNTHESIZE_IMAGE",
                            capability_id="IMAGE_GENERATE_AND_INSERT",
                            description="Generate high-resolution portrait or artwork bitmap via model",
                            expected_outcome="bitmap_generated",
                        ),
                        StrategyStage(
                            stage_index=1,
                            name="FOCUS_CANVAS",
                            capability_id="FOCUS_WINDOW",
                            description="Focus canvas surface",
                            expected_outcome="canvas_active",
                        ),
                        StrategyStage(
                            stage_index=2,
                            name="PASTE_ARTWORK",
                            capability_id="CLIPBOARD_PASTE",
                            description="Insert generated bitmap via clipboard",
                            expected_outcome="canvas_contains_artwork",
                        ),
                    ],
                    estimated_success_probability=strat2_prob,
                    semantic_goal_coverage=strat2_coverage,
                    risk_level="LOW",
                    dependencies=["active_generative_image_model", "clipboard"],
                    missing_capabilities=strat2_missing,
                    rejection_reason=strat2_rejection,
                    is_available=strat2_avail,
                    rationale="High semantic fidelity for portraits and complex scenes when generative model is configured.",
                )
            )

            # Strategy 3: Browser-Assisted Web Generation & Canvas Import
            has_browser = any(b in available_cap_ids for b in ("ENV_APP_CHROME", "ENV_APP_EDGE", "ENV_APP_FIREFOX"))
            browser_avail = has_browser and paste_avail
            browser_missing = []
            if not has_browser:
                browser_missing.append("WEB_BROWSER")
            browser_missing.append("WEB_GENERATIVE_TOOL_SESSION")

            candidates.append(
                StrategyOption(
                    strategy_id="STRAT_BROWSER_WEB_IMPORT",
                    name="Browser-Assisted Web Generation & Import",
                    description="Launch local browser, navigate to web creative tool, and paste result into Paint",
                    required_capabilities=["LAUNCH_APPLICATION", "FOCUS_WINDOW", "CLIPBOARD_PASTE"],
                    stages=[
                        StrategyStage(
                            stage_index=0,
                            name="OPEN_BROWSER",
                            capability_id="LAUNCH_APPLICATION",
                            description="Launch web browser",
                            expected_outcome="browser_open",
                        ),
                        StrategyStage(
                            stage_index=1,
                            name="COPY_WEB_ART",
                            capability_id="CLIPBOARD_PASTE",
                            description="Transfer generated web artwork to clipboard",
                            expected_outcome="clipboard_filled",
                        ),
                    ],
                    estimated_success_probability=0.0,  # Web tool session not wired
                    semantic_goal_coverage=0.88,
                    risk_level="MEDIUM",
                    dependencies=["installed_browser", "web_ai_service_session"],
                    missing_capabilities=browser_missing,
                    rejection_reason=f"Prerequisites unavailable: {', '.join(browser_missing)}",
                    is_available=False,
                    rationale="Alternative workflow leveraging browser tools if direct model API is unavailable.",
                )
            )

            # Strategy 4: Local Dedicated Creative Application (Photoshop/GIMP/Blender)
            has_adv_app = any(app in available_cap_ids for app in ("ENV_APP_GIMP", "ENV_APP_PHOTOSHOP", "ENV_APP_BLENDER"))
            candidates.append(
                StrategyOption(
                    strategy_id="STRAT_LOCAL_CREATIVE_APP",
                    name="Secondary Installed Creative Application Workflow",
                    description="Delegate complex art synthesis to specialized local graphics suite",
                    required_capabilities=["LAUNCH_APPLICATION", "FOCUS_WINDOW"],
                    stages=[],
                    estimated_success_probability=0.0,
                    semantic_goal_coverage=0.85,
                    risk_level="MEDIUM",
                    dependencies=["installed_gimp_or_photoshop"],
                    missing_capabilities=["ADVANCED_CREATIVE_SUITE_INSTALLED"] if not has_adv_app else [],
                    rejection_reason="No specialized graphics application (Photoshop/GIMP) is verified installed on this host." if not has_adv_app else None,
                    is_available=has_adv_app,
                    rationale="Explores third-party creative desktop software installed on machine.",
                )
            )

        # -------------------------------------------------------------
        # Domain 2: Document / Text Editing Strategies
        # -------------------------------------------------------------
        elif req_set.target_domain == "document_editing" or action_type == "type" or "type" in p_lower:
            req_caps = ["LAUNCH_APPLICATION", "FOCUS_WINDOW", "TYPE_TEXT"]
            all_avail = all(rc in available_cap_ids for rc in req_caps)
            missing = [rc for rc in req_caps if rc not in available_cap_ids]

            candidates.append(
                StrategyOption(
                    strategy_id="STRAT_DETERMINISTIC_TEXT_WORKFLOW",
                    name="Deterministic Document Typing & Verification",
                    description="Sequence host application launch, edit control focus, and character input stream",
                    required_capabilities=req_caps,
                    stages=[
                        StrategyStage(
                            stage_index=0,
                            name="LAUNCH_APPLICATION",
                            capability_id="LAUNCH_APPLICATION",
                            description="Launch editor process",
                            expected_outcome="editor_running",
                        ),
                        StrategyStage(
                            stage_index=1,
                            name="FOCUS_WINDOW",
                            capability_id="FOCUS_WINDOW",
                            description="Bring editor to foreground",
                            expected_outcome="editor_focused",
                        ),
                        StrategyStage(
                            stage_index=2,
                            name="TYPE_TEXT",
                            capability_id="TYPE_TEXT",
                            description="Input character sequence into buffer",
                            expected_outcome="text_entered",
                        ),
                    ],
                    estimated_success_probability=0.96 if all_avail else 0.0,
                    semantic_goal_coverage=1.0,
                    risk_level="LOW",
                    missing_capabilities=missing,
                    is_available=all_avail,
                    rationale="Standard deterministic desktop document entry.",
                )
            )

        # -------------------------------------------------------------
        # Domain 3: General Desktop Action Strategies
        # -------------------------------------------------------------
        else:
            req_caps = ["LAUNCH_APPLICATION", "FOCUS_WINDOW"]
            all_avail = all(rc in available_cap_ids for rc in req_caps)
            missing = [rc for rc in req_caps if rc not in available_cap_ids]

            candidates.append(
                StrategyOption(
                    strategy_id="STRAT_GENERAL_DESKTOP_FLOW",
                    name="General Desktop Interaction",
                    description="Launch requested target application and focus foreground",
                    required_capabilities=req_caps,
                    stages=[
                        StrategyStage(
                            stage_index=0,
                            name="LAUNCH_APPLICATION",
                            capability_id="LAUNCH_APPLICATION",
                            description="Launch target application",
                            expected_outcome="app_running",
                        ),
                        StrategyStage(
                            stage_index=1,
                            name="FOCUS_WINDOW",
                            capability_id="FOCUS_WINDOW",
                            description="Bring application to foreground",
                            expected_outcome="app_focused",
                        ),
                    ],
                    estimated_success_probability=0.95 if all_avail else 0.0,
                    semantic_goal_coverage=1.0,
                    risk_level="LOW",
                    missing_capabilities=missing,
                    is_available=all_avail,
                    rationale="Standard application lifecycle execution.",
                )
            )

        # Rank candidate strategies: sort by executable viability, then probability, then coverage
        viable_candidates = [
            c for c in candidates
            if c.is_available
            and c.estimated_success_probability >= self.MINIMUM_EXECUTABLE_PROBABILITY
            and c.semantic_goal_coverage >= self.MINIMUM_SEMANTIC_COVERAGE
        ]

        # Sort viable candidates descending by estimated_success_probability
        viable_candidates.sort(key=lambda s: s.estimated_success_probability, reverse=True)

        # Sort all candidates for reporting
        candidates.sort(key=lambda s: (s.is_available, s.semantic_goal_coverage, s.estimated_success_probability), reverse=True)

        if viable_candidates:
            best = viable_candidates[0]
            reasoning = (
                f"Selected optimal strategy '{best.name}' "
                f"(probability: {best.estimated_success_probability*100:.1f}%, "
                f"semantic coverage: {best.semantic_goal_coverage*100:.1f}%)."
            )
            return StrategySelectionResult(
                selected_strategy=best,
                candidate_strategies=candidates,
                is_executable=True,
                selection_reasoning=reasoning,
            )

        # No strategy qualified: Compile capability gap diagnostics
        reasons = []
        for c in candidates:
            if c.rejection_reason:
                reasons.append(f"[{c.name}]: {c.rejection_reason}")
            elif not c.is_available:
                reasons.append(f"[{c.name}]: Missing required capabilities ({', '.join(c.missing_capabilities)})")

        reasoning = (
            f"No viable strategy could achieve '{prompt}'. "
            f"Evaluated {len(candidates)} candidate strategies, but none satisfied both feasibility "
            f"and semantic coverage thresholds. Breakdown: {' | '.join(reasons)}"
        )

        return StrategySelectionResult(
            selected_strategy=None,
            candidate_strategies=candidates,
            is_executable=False,
            selection_reasoning=reasoning,
        )
