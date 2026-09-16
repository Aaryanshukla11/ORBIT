"""AI-Native Agent Runtime Subsystem.

Exports the core AI-native agent components:
1. Agent State Manager (Persistent task memory & snapshot history)
2. Agent Action Protocol (Strict JSON action contracts, validation, & outcome contracts)
3. Perception Router (4-tier query hierarchy: Win32 -> UIA -> OCR -> Vision Model)
4. Agent State Transition Verifier (Semantic expectation verification)
5. Agent Memory + Progress Graph (Dynamic subgoal tracking & loop prevention)
"""

from __future__ import annotations

from orbit.runtime.agent.contracts import (
    AbortTaskParams,
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    ActionExecutionResult,
    ActionOutcomeContract,
    ActionType,
    ActionValidationFailureCode,
    ActionValidationResult,
    AgentAction,
    AgentActionValidator,
    ClickParams,
    CompleteGoalParams,
    DoubleClickParams,
    DragParams,
    DrawStrokesParams,
    ExpectedState,
    FocusWindowParams,
    LaunchApplicationParams,
    OutcomeStatus,
    ResolvedAction,
    RightClickParams,
    ScrollParams,
    SelectOptionParams,
    SemanticTarget,
    SendHotkeyParams,
    TypeTextParams,
    VerificationStrategy,
    WaitParams,
)
from orbit.runtime.agent.perception_router import (
    PerceptionLayer,
    PerceptionQueryResult,
    PerceptionRouter,
)
from orbit.runtime.agent.progress_graph import (
    ProgressGraph,
    ProgressNode,
    ProgressSnapshot,
    SubObjective,
    SubgoalNode,
    SubgoalStatus,
)
from orbit.runtime.agent.state import (
    AgentStateManager,
    AgentStepRecord,
    DesktopStateSnapshot,
    TaskMemory,
)
from orbit.runtime.agent.verifier import AgentStateTransitionVerifier

__all__ = [
    # 1. State Manager & Memory
    "AgentStateManager",
    "AgentStepRecord",
    "DesktopStateSnapshot",
    "TaskMemory",
    # 2. Action Protocol & Contracts
    "AbstractAction",
    "AbstractActionType",
    "ActionExecutionOutcome",
    "ActionExecutionResult",
    "ActionOutcomeContract",
    "ActionType",
    "ActionValidationFailureCode",
    "ActionValidationResult",
    "AgentAction",
    "AgentActionValidator",
    "ExpectedState",
    "OutcomeStatus",
    "ResolvedAction",
    "SemanticTarget",
    "VerificationStrategy",
    # Parameter Models
    "AbortTaskParams",
    "ClickParams",
    "CompleteGoalParams",
    "DoubleClickParams",
    "DragParams",
    "DrawStrokesParams",
    "FocusWindowParams",
    "LaunchApplicationParams",
    "RightClickParams",
    "ScrollParams",
    "SelectOptionParams",
    "SendHotkeyParams",
    "TypeTextParams",
    "WaitParams",
    # 3. Perception Router
    "PerceptionLayer",
    "PerceptionQueryResult",
    "PerceptionRouter",
    # 4. State Transition Verifier
    "AgentStateTransitionVerifier",
    # 5. Progress Graph
    "ProgressGraph",
    "ProgressNode",
    "ProgressSnapshot",
    "SubObjective",
    "SubgoalNode",
    "SubgoalStatus",
]
