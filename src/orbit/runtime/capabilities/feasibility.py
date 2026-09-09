"""Feasibility Analyzer evaluating whether a user objective can be reliably executed."""

from __future__ import annotations

import logging
from typing import List, Optional, Set

from orbit.runtime.capabilities.composition import CapabilityCompositionEngine
from orbit.runtime.capabilities.environment_discovery import EnvironmentCapabilityDiscovery
from orbit.runtime.capabilities.matcher import CapabilityMatcher
from orbit.runtime.capabilities.models import (
    CapabilityGapReport,
    FeasibilityAssessment,
    FeasibilityStatus,
    GoalRequirementSet,
)
from orbit.runtime.capabilities.registry import CapabilityRegistry
from orbit.runtime.capabilities.requirements import GoalRequirementExtractor
from orbit.runtime.capabilities.strategy_selector import StrategySelector
from orbit.runtime.cognitive.models import StructuredObjective

logger = logging.getLogger(__name__)


class FeasibilityAnalyzer:
    """Evaluates task feasibility to prevent fake execution of unachievable goals."""

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        matcher: Optional[CapabilityMatcher] = None,
        strategy_selector: Optional[StrategySelector] = None,
        environment_discovery: Optional[EnvironmentCapabilityDiscovery] = None,
        composition_engine: Optional[CapabilityCompositionEngine] = None,
        requirement_extractor: Optional[GoalRequirementExtractor] = None,
    ) -> None:
        self._registry = registry or CapabilityRegistry()
        self._environment_discovery = environment_discovery or EnvironmentCapabilityDiscovery()
        self._composition_engine = composition_engine or CapabilityCompositionEngine()
        self._requirement_extractor = requirement_extractor or GoalRequirementExtractor()
        self._matcher = matcher or CapabilityMatcher(registry=self._registry)
        self._strategy_selector = strategy_selector or StrategySelector(
            registry=self._registry,
            matcher=self._matcher,
            environment_discovery=self._environment_discovery,
            composition_engine=self._composition_engine,
            requirement_extractor=self._requirement_extractor,
        )

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def strategy_selector(self) -> StrategySelector:
        return self._strategy_selector

    @property
    def requirement_extractor(self) -> GoalRequirementExtractor:
        return self._requirement_extractor

    @property
    def environment_discovery(self) -> EnvironmentCapabilityDiscovery:
        return self._environment_discovery

    def evaluate_feasibility(self, objective: StructuredObjective) -> FeasibilityAssessment:
        """Perform authoritative capability composition and feasibility analysis on a StructuredObjective."""
        prompt = getattr(objective, "raw_prompt", str(objective.user_goal or ""))

        # 1. Extract decoupled Goal Requirements (WHAT is needed)
        req_set: GoalRequirementSet = self._requirement_extractor.extract_requirements(objective)

        # 2. Match baseline capabilities
        match_report = self._matcher.match_objective(objective)

        # 3. Formulate and rank multiple candidate strategies
        strategy_result = self._strategy_selector.select_strategy(
            objective=objective,
            match_report=match_report,
            requirements=req_set,
        )

        # 4. If a viable strategy was selected
        if strategy_result.is_executable and strategy_result.selected_strategy is not None:
            strat = strategy_result.selected_strategy
            return FeasibilityAssessment(
                is_feasible=True,
                status=FeasibilityStatus.FEASIBLE,
                confidence=strat.estimated_success_probability,
                matched_strategy=strat,
                available_capabilities=[c.capability_id for c in match_report.available_matched_capabilities],
                missing_capabilities=match_report.missing_capability_ids,
                triggered_limitations=[l.description for l in match_report.triggered_limitations],
                explanation=(
                    f"Objective '{prompt}' is FEASIBLE using strategy '{strat.name}' "
                    f"(estimated success probability: {strat.estimated_success_probability*100:.1f}%, "
                    f"semantic coverage: {strat.semantic_goal_coverage*100:.1f}%)."
                ),
                suggested_alternatives=[],
                capability_gap=None,
            )

        # 5. Infeasible: Compile structured Capability Gap Analysis
        all_missing_caps: Set[str] = set()
        for cand in strategy_result.candidate_strategies:
            all_missing_caps.update(cand.missing_capabilities)
        for mc in match_report.missing_capability_ids:
            all_missing_caps.add(mc)

        unmet_reqs = [r.semantic_description for r in req_set.get_mandatory_requirements()]
        lims = [l.description for l in match_report.triggered_limitations]

        alternatives: List[str] = []
        recommendations: List[str] = []

        if "IMAGE_GENERATE_AND_INSERT" in all_missing_caps or req_set.required_fidelity == "HIGH_FIDELITY_SEMANTIC":
            alternatives.append("Enable or configure an active generative image model provider (e.g. OpenAI/Ollama/Cloud vision-gen)")
            alternatives.append("Request basic geometric shapes instead (e.g. cube, circle, square, triangle, star)")
            recommendations.append("Install an image-generation model in ModelManager or provide an image generation API key.")
        else:
            alternatives.append("Verify required application is installed on the host machine")
            recommendations.append("Ensure target software is installed and accessible in standard Windows directories.")

        gap_report = CapabilityGapReport(
            requested_goal=prompt,
            attempted_strategies=strategy_result.candidate_strategies,
            missing_capabilities=sorted(list(all_missing_caps)),
            unmet_requirements=unmet_reqs,
            reason=strategy_result.selection_reasoning,
            recommended_prerequisites=recommendations,
            gap_severity="BLOCKING",
        )

        explanation = (
            f"Goal '{prompt}' is NOT FEASIBLY EXECUTABLE with current capabilities. "
            f"{strategy_result.selection_reasoning}"
        )
        if lims:
            explanation += f" Triggered limitation boundaries: {'; '.join(lims)}."

        logger.warning(
            "[CAPABILITY GAP DETECTED] Infeasible objective: '%s'. Missing: %s. Reason: %s",
            prompt,
            list(all_missing_caps),
            explanation,
        )

        return FeasibilityAssessment(
            is_feasible=False,
            status=FeasibilityStatus.INSUFFICIENT_CAPABILITY,
            confidence=1.0,
            matched_strategy=None,
            available_capabilities=[c.capability_id for c in match_report.available_matched_capabilities],
            missing_capabilities=sorted(list(all_missing_caps)),
            triggered_limitations=lims,
            explanation=explanation,
            suggested_alternatives=alternatives,
            capability_gap=gap_report,
        )
