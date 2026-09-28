"""ORBIT Tool Service Subsystem.

Provides the model-facing structured capability request resolution, validation,
and translation service between LLM tool calling and ORBIT's cognitive architecture.

Architectural Invariants:
1. ToolService is NOT a planner and NOT an execution engine.
2. ToolService MUST NEVER directly execute physical actions, Windows APIs, or shell commands.
3. Every validated tool call translates strictly into an ORBIT canonical AbstractAction.
4. All executable intents must pass through AgentPlanner -> PlanDirective -> PrimitiveComposer -> PrimitiveValidator -> PrimitiveExecutionController.
5. Fails closed on unknown tools, invalid parameters, prohibited coordinates, or malformed requests.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionOutcomeContract,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.cognitive.models import (
    CurrentStateObservation,
    StructuredObjective,
    SubObjective,
)
from orbit.runtime.cognitive.plan_directive import PlanDirective
from orbit.runtime.cognitive.semantic_feasibility import (
    CandidatePlan,
    SemanticFeasibilityReport,
)
from orbit.runtime.tools.registry import ToolRegistry
from orbit.runtime.tools.schema import ToolSchema, ToolValidationResult
from orbit.runtime.world_model.model import AgentWorldModel

logger = logging.getLogger(__name__)


class StructuredToolRequest(BaseModel):
    """An incoming tool invocation request parsed from model output."""

    tool_name: str = Field(..., description="Name of the requested capability")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Structured parameters payload")
    call_id: Optional[str] = Field(default=None, description="Optional tool call ID from model provider")
    rationale: Optional[str] = Field(default=None, description="Model rationale for invoking tool")


class ToolService:
    """Production service managing model-facing tool schemas and parameter validation.

    Translates valid model tool invocations into canonical AbstractActions for AgentPlanner.
    Guarantees zero physical execution within the tool layer.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        auto_register_builtins: bool = True,
    ) -> None:
        self._registry = registry or ToolRegistry(auto_register_builtins=auto_register_builtins)

    @property
    def registry(self) -> ToolRegistry:
        """Access underlying ToolRegistry."""
        return self._registry

    def get_available_schemas(
        self,
        format: str = "openai",
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve model-consumable JSON schemas for all registered capabilities."""
        return self._registry.list_schemas(format=format, category=category)

    def resolve_tool(self, name: str) -> Optional[ToolSchema]:
        """Look up tool descriptor by name."""
        return self._registry.get(name)

    def validate_request(
        self,
        name: str,
        parameters: Dict[str, Any],
    ) -> ToolValidationResult:
        """Strictly validate a tool invocation request.

        Fails closed if:
        - Tool is not registered.
        - Parameters are malformed or non-dict.
        - Physical coordinates are present.
        - Required parameters are missing.
        - Parameters violate type/enum constraints.
        - Prohibited or dangerous code execution strings are detected.
        """
        tool = self.resolve_tool(name)
        if tool is None:
            return ToolValidationResult(
                is_valid=False,
                errors=[f"Unknown tool: '{name}'. Tool is not registered in ORBIT capability catalog."],
                action_type=None,
            )

        return tool.validate_parameters(parameters)

    def create_action_from_tool_call(
        self,
        name: str,
        parameters: Dict[str, Any],
        semantic_target: Optional[SemanticTarget] = None,
        expected_effect: str = "",
        rationale: str = "",
    ) -> Tuple[Optional[AbstractAction], Optional[str]]:
        """Validate tool request and construct a canonical ORBIT AbstractAction.

        Does NOT execute the action. Returns (AbstractAction, None) on success,
        or (None, error_message) on failure.
        """
        val_result = self.validate_request(name, parameters)
        if not val_result.is_valid:
            err_msg = "; ".join(val_result.errors)
            logger.warning("[TOOL SERVICE] Tool call validation failed for '%s': %s", name, err_msg)
            return None, err_msg

        tool = self.resolve_tool(name)
        if tool is None or tool.action_type is None:
            return None, f"Tool '{name}' has no bound canonical primitive type."

        # Extract or resolve semantic target
        target = semantic_target
        clean_params = dict(val_result.validated_parameters)

        if target is None and "target" in clean_params:
            target_data = clean_params.pop("target")
            if isinstance(target_data, dict):
                try:
                    target = SemanticTarget(**target_data)
                except Exception as ex:
                    return None, f"Invalid semantic target specification: {ex}"
            elif isinstance(target_data, SemanticTarget):
                target = target_data

        # Determine default outcome contract based on primitive type
        contract = ActionOutcomeContract(
            expected_state_transition=expected_effect or f"Executed tool '{tool.name}' ({tool.action_type.value})",
            verification_strategy=VerificationStrategy.AUTO_ROUTED,
            target_name=target.name if target else None,
            target_role=target.role if target else None,
        )

        action = AbstractAction(
            action_id=f"act_{uuid4().hex[:8]}",
            action_type=tool.action_type,
            target=target,
            parameters=clean_params,
            outcome_contract=contract,
            expected_effect=expected_effect or f"State transition from {tool.name}",
            rationale=rationale or f"Invoked tool capability '{tool.name}'",
        )

        logger.debug(
            "[TOOL SERVICE] Created canonical AbstractAction '%s' (%s) from tool '%s'",
            action.action_id, action.action_type.value, tool.name
        )
        return action, None

    def route_tool_call_to_candidate_plan(
        self,
        name: str,
        parameters: Dict[str, Any],
        subgoal_id: str,
        semantic_target: Optional[SemanticTarget] = None,
        rationale: str = "",
    ) -> Tuple[Optional[CandidatePlan], Optional[str]]:
        """Translate a validated tool call into a CandidatePlan for AgentPlanner evaluation.

        Allows the model's suggested tool call to be scored by SemanticFeasibilityEvaluator
        before PlanDirective formulation.
        """
        action, err = self.create_action_from_tool_call(
            name=name,
            parameters=parameters,
            semantic_target=semantic_target,
            rationale=rationale,
        )
        if err or not action:
            return None, err

        candidate = CandidatePlan(
            subgoal_id=subgoal_id,
            intent_strategy="TOOL_CAPABILITY",
            proposed_primitives=[action.action_type],
            targets=[action.target] if action.target else [],
            expected_outcome=action.outcome_contract or ActionOutcomeContract(
                expected_state_transition=f"Invoked tool capability {name}",
                verification_strategy=VerificationStrategy.AUTO_ROUTED,
            ),
            estimated_complexity=1,
            creative_payload=action.parameters,
            rationale=action.rationale or f"Candidate plan from tool {name}",
        )
        return candidate, None

    def submit_to_planner(
        self,
        name: str,
        parameters: Dict[str, Any],
        planner: Any,
        objective: StructuredObjective,
        subgoal: SubObjective,
        world_model: AgentWorldModel,
        observation: Optional[CurrentStateObservation] = None,
        semantic_target: Optional[SemanticTarget] = None,
    ) -> Tuple[Optional[PlanDirective], Optional[SemanticFeasibilityReport], Optional[str]]:
        """Submit a validated tool call to AgentPlanner for semantic feasibility and directive emission.

        Enforces:
        Model Tool Call -> ToolService -> AbstractAction -> AgentPlanner -> SemanticFeasibility -> PlanDirective.
        Guarantees that ToolService never bypasses AgentPlanner or executes physical actions.
        """
        action, err = self.create_action_from_tool_call(
            name=name,
            parameters=parameters,
            semantic_target=semantic_target,
        )
        if err or not action:
            return None, None, err

        if not hasattr(planner, "plan_from_action"):
            return None, None, "Planner does not support plan_from_action interface."

        directive, report = planner.plan_from_action(
            action=action,
            objective=objective,
            subgoal=subgoal,
            world_model=world_model,
            observation=observation,
        )
        return directive, report, None
