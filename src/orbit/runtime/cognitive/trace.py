"""Production Diagnostic Trace & Cycle Telemetry Logger (Step 5).

Generates structured, human-auditable execution trace blocks for every agent cycle.
Does NOT store or log private model chain-of-thought.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CycleExecutionTrace(BaseModel):
    """Auditable telemetry record representing a complete single cycle of closed-loop execution."""

    trace_id: str = Field(default_factory=lambda: f"trc_{uuid4().hex[:8]}")
    cycle_number: int = 0
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 1. Observation
    observation_id: str = ""
    freshness_validated: bool = True
    foreground_window: Optional[str] = None
    visible_windows: List[str] = Field(default_factory=list)
    ocr_summary: str = ""
    ui_elements_count: int = 0
    screenshot_available: bool = False

    # 2. Model Routing
    model_id: str = "UNKNOWN"
    model_provider: str = "UNKNOWN"
    local_or_cloud: str = "LOCAL"
    capabilities: List[str] = Field(default_factory=list)
    vision_capable: bool = False
    screenshot_attached: bool = False
    model_latency_ms: Optional[float] = None
    raw_model_response: Optional[str] = None

    # 3. Decision
    decision_summary: str = ""
    decision_confidence: float = 0.0
    goal_progress: str = "IN_PROGRESS"
    next_action_type: Optional[str] = None
    next_action_params: Dict[str, Any] = Field(default_factory=dict)

    # 4. Target Grounding
    semantic_target_name: Optional[str] = None
    semantic_target_role: Optional[str] = None
    target_evidence_source: str = "NONE"
    grounding_confidence: float = 0.0
    grounding_resolved: bool = False
    resolved_coordinates: Optional[Tuple[int, int]] = None

    # 5. Execution
    dispatch_attempted: bool = False
    dispatch_success: bool = False
    dispatch_error: Optional[str] = None

    # 6. Post-Action Observation
    post_observation_id: str = ""
    post_freshness_validated: bool = False

    # 7. Verification
    expected_effect: str = ""
    observed_effect: str = ""
    expected_effect_observed: bool = False
    verification_strategy: str = "STATE_DELTA"
    verification_reason: str = ""

    # 8. Goal Evaluation
    goal_satisfied: bool = False
    goal_supporting_evidence: List[str] = Field(default_factory=list)
    goal_verifier_evaluated: bool = False

    # 9. Progress & Budget
    meaningful_state_change: bool = False
    repeated_actions_count: int = 0
    recovery_count: int = 0
    remaining_action_budget: int = 0


def format_cycle_trace_block(trace: CycleExecutionTrace) -> str:
    """Format a single cycle execution trace into the canonical human-readable diagnostic block."""
    vis_wins_str = ", ".join(str(w) for w in trace.visible_windows[:5]) if trace.visible_windows else "None"
    if len(trace.visible_windows) > 5:
        vis_wins_str += f" (+{len(trace.visible_windows) - 5} more)"

    ocr_sum = str(trace.ocr_summary)[:100] + "..." if len(str(trace.ocr_summary)) > 100 else (str(trace.ocr_summary) or "None")
    coords_str = f"({trace.resolved_coordinates[0]}, {trace.resolved_coordinates[1]})" if trace.resolved_coordinates else "None"
    evidence_str = ", ".join(str(e) for e in trace.goal_supporting_evidence) if trace.goal_supporting_evidence else "None"

    latency_str = f"{trace.model_latency_ms:.1f}" if isinstance(trace.model_latency_ms, (int, float)) else "N/A"
    conf_str = f"{trace.decision_confidence:.2f}" if isinstance(trace.decision_confidence, (int, float)) else str(trace.decision_confidence)
    ground_conf_str = f"{trace.grounding_confidence:.2f}" if isinstance(trace.grounding_confidence, (int, float)) else str(trace.grounding_confidence)

    lines = [
        "================================================",
        f"CYCLE {trace.cycle_number}",
        "================================================",
        "OBSERVATION",
        f"- observation_id: {trace.observation_id}",
        f"- timestamp: {trace.timestamp_utc.isoformat() if hasattr(trace.timestamp_utc, 'isoformat') else str(trace.timestamp_utc)}",
        f"- freshness: {'VALID' if trace.freshness_validated else 'STALE / RECAPTURED'}",
        f"- foreground_window: {trace.foreground_window or 'None'}",
        f"- visible_windows: {vis_wins_str}",
        f"- OCR summary: {ocr_sum}",
        f"- UI elements count: {trace.ui_elements_count}",
        f"- screenshot available: {trace.screenshot_available}",
        "",
        "MODEL ROUTING",
        f"- model: {trace.model_id}",
        f"- provider: {trace.model_provider}",
        f"- local/cloud: {trace.local_or_cloud}",
        f"- capabilities: {', '.join(str(c) for c in trace.capabilities) if trace.capabilities else 'TEXT'}",
        f"- vision capable: {trace.vision_capable}",
        f"- screenshot attached: {trace.screenshot_attached}",
        f"- latency_ms: {latency_str}",
        "",
        "DECISION",
        f"- decision_summary: {trace.decision_summary}",
        f"- confidence: {conf_str}",
        f"- goal_progress: {trace.goal_progress}",
        f"- next_action: {trace.next_action_type or 'None'}",
        *( [f"- raw_model_response: {trace.raw_model_response.strip()}"] if trace.raw_model_response else [] ),
        "",
        "GROUNDING",
        f"- semantic target: {trace.semantic_target_name or 'None'} (role: {trace.semantic_target_role or 'None'})",
        f"- target evidence source: {trace.target_evidence_source}",
        f"- grounding confidence: {ground_conf_str}",
        f"- resolved: {trace.grounding_resolved} {coords_str}",
        "",
        "EXECUTION",
        f"- dispatch attempted: {trace.dispatch_attempted}",
        f"- dispatch success: {trace.dispatch_success}",
        *( [f"- dispatch error: {trace.dispatch_error}"] if trace.dispatch_error else [] ),
        "",
        "POST-ACTION OBSERVATION",
        f"- observation_id: {trace.post_observation_id or 'None'}",
        f"- freshness validated: {trace.post_freshness_validated}",
        "",
        "VERIFICATION",
        f"- expected effect: {trace.expected_effect or 'None'}",
        f"- observed effect: {trace.observed_effect or 'None'}",
        f"- expected_effect_observed: {trace.expected_effect_observed}",
        f"- verification strategy: {trace.verification_strategy}",
        f"- verification reason: {trace.verification_reason or 'None'}",
        "",
        "GOAL EVALUATION",
        f"- goal_satisfied: {trace.goal_satisfied}",
        f"- supporting evidence: {evidence_str}",
        "",
        "PROGRESS",
        f"- meaningful state change: {trace.meaningful_state_change}",
        f"- repeated actions: {trace.repeated_actions_count}",
        f"- recovery count: {trace.recovery_count}",
        f"- remaining budget: {trace.remaining_action_budget}",
        "================================================",
    ]
    return "\n".join(lines)
