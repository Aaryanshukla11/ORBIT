"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/agent/loop.py (LoopGuard) & watchdog/service.py
ORBIT Destination:    src/orbit/runtime/cognitive/failure_analyst.py
Integration Paradigm: Transduced Cognitive Diagnosis (Brain-Body Separation)

Adaptations Applied:
- Transduced LoopGuard state-hashing, UI stagnation, and cycle detection (A -> B -> A).
- Stripped prompt nudge strings and conversation history injections.
- Enforced strict invariant: LoopGuard is purely diagnostic (Guardrail 9). It produces FailureReport only.
- Strategy selection and recovery planning remain 100% exclusively owned by AgentPlanner.replan().
======================================
"""

from __future__ import annotations

from collections import Counter, deque
import hashlib
import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionExecutionOutcome,
    OutcomeStatus,
)
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective
from orbit.runtime.world_model import AgentWorldModel

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Diagnostic categorization of action and cycle failures."""

    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_OBSCURED = "TARGET_OBSCURED"
    TARGET_UNRESPONSIVE = "TARGET_UNRESPONSIVE"
    WINDOW_NOT_FOCUSED = "WINDOW_NOT_FOCUSED"
    APPLICATION_CRASHED = "APPLICATION_CRASHED"
    TEXT_ENTRY_MISMATCH = "TEXT_ENTRY_MISMATCH"
    POSTCONDITION_UNSATISFIED = "POSTCONDITION_UNSATISFIED"
    TIMEOUT = "TIMEOUT"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    STALLED_LOOP_DETECTED = "STALLED_LOOP_DETECTED"
    REPETITIVE_ACTION_DETECTED = "REPETITIVE_ACTION_DETECTED"
    FAILED_ACTION_RETRY = "FAILED_ACTION_RETRY"
    STATE_CYCLE_DETECTED = "STATE_CYCLE_DETECTED"
    DEAD_WINDOW_HANDLE = "DEAD_WINDOW_HANDLE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class FailureReport(BaseModel):
    """Structured, non-executable diagnostic analysis of an action failure."""

    report_id: str = Field(default_factory=lambda: f"fail_{uuid4().hex[:8]}")
    action_id: str
    action_type: AbstractActionType
    category: FailureCategory
    diagnosis: str = Field(..., description="Root-cause diagnostic explanation")
    evidence_observed: List[str] = Field(default_factory=list, description="Observations and sensory cues establishing failure")
    suggested_remediation_direction: str = Field(
        default="",
        description="High-level diagnostic guidance for AgentPlanner (NEVER executable actions)",
    )
    is_transient: bool = Field(default=True, description="Whether this failure is likely transient and recoverable via alternate strategy")


class LoopGuardDiagnosticEngine:
    """Purely diagnostic cycle, stagnation, and repetition analyzer for ORBIT.

    Invariants:
    1. Diagnosis Only (Guardrail 9): Emits FailureReport only.
    2. Zero Recovery Strategy Selection: Never dictates the specific recovery action.
    3. Zero Direct Execution: Never executes commands or alters environment.
    """

    def __init__(self, window: int = 10, max_stagnant_steps: int = 3) -> None:
        self._action_history: deque[str] = deque(maxlen=window)
        self._last_state_hash: Optional[str] = None
        self._stagnant_count: int = 0
        self._max_stagnant_steps = max_stagnant_steps
        self._visited_states: Dict[str, int] = {}  # state_fingerprint -> visit_count
        self._last_action_hash: Optional[str] = None
        self._last_action_failed: bool = False

    def compute_state_fingerprint(self, obs: CurrentStateObservation) -> str:
        """Computes deterministic SHA256 digest of active desktop observation state."""
        hwnd = getattr(obs, "active_hwnd", 0) or 0
        title = (obs.active_window_title or "").strip().lower()
        elements = getattr(obs, "interactive_elements", []) or []
        elem_digest = ",".join(
            sorted(f"{e.get('control_type')}:{e.get('name')}" for e in elements if isinstance(e, dict))
        )
        ocr_tokens = getattr(obs, "ocr_tokens", []) or []
        ocr_digest = ",".join(str(t) for t in ocr_tokens[:20])

        raw_key = f"HWND:{hwnd}|TITLE:{title}|ELEMS:{elem_digest}|OCR:{ocr_digest}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def compute_action_hash(self, action: AbstractAction) -> str:
        """Computes deterministic hash of action type and relevant parameters."""
        filtered_params = {
            k: v for k, v in (action.parameters or {}).items()
            if k not in ("thought", "action_id", "timestamp")
        }
        target_name = action.target.name if action.target else ""
        raw_key = f"{action.action_type}:{target_name}:{json.dumps(filtered_params, sort_keys=True, default=str)}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def record_and_diagnose(
        self,
        action: AbstractAction,
        post_obs: CurrentStateObservation,
        exec_outcome: ActionExecutionOutcome,
    ) -> Optional[FailureReport]:
        """Consumes fresh post-action observation and analyzes for loops, stagnation, or cycles."""
        act_hash = self.compute_action_hash(action)
        state_hash = self.compute_state_fingerprint(post_obs)
        is_success = bool(
            getattr(exec_outcome, "outcome_status", None) == OutcomeStatus.EFFECT_VERIFIED
            or (getattr(exec_outcome, "expected_effect_observed", False) and getattr(exec_outcome, "dispatch_success", False))
        )

        # 1. Dead window handle detection
        # 1. Dead window handle detection via live observation
        target_hwnd = action.parameters.get("hwnd") or getattr(post_obs, "active_hwnd", 0)
        if target_hwnd:
            try:
                target_hwnd_int = int(target_hwnd)
                visible_hwnds = {int(w.get("hwnd")) for w in post_obs.visible_windows if isinstance(w, dict) and w.get("hwnd") is not None}
                if post_obs.active_window_hwnd is not None:
                    visible_hwnds.add(int(post_obs.active_window_hwnd))
                if visible_hwnds and target_hwnd_int not in visible_hwnds:
                    return FailureReport(
                        action_id=action.action_id,
                        action_type=action.action_type,
                        category=FailureCategory.DEAD_WINDOW_HANDLE,
                        diagnosis=f"Target window handle HWND:{target_hwnd} is dead or not present in live observation.",
                        evidence_observed=[f"HWND:{target_hwnd} not found in visible windows or active window"],
                        suggested_remediation_direction="Re-launch application or switch to active visible window",
                        is_transient=False,
                    )
            except Exception:
                pass

        # 2. UI Stagnation detection across consecutive steps (Priority over action-level retries)
        if self._last_state_hash is not None and state_hash == self._last_state_hash:
            if not is_success:
                self._stagnant_count += 1
            if self._stagnant_count >= self._max_stagnant_steps:
                return FailureReport(
                    action_id=action.action_id,
                    action_type=action.action_type,
                    category=FailureCategory.STALLED_LOOP_DETECTED,
                    diagnosis=f"Desktop state remained completely unchanged across {self._stagnant_count} consecutive steps.",
                    evidence_observed=[f"State fingerprint {state_hash[:8]} frozen for {self._stagnant_count} steps"],
                    suggested_remediation_direction="State is stalled; trigger full goal replan with alternative modality",
                    is_transient=False,
                )
        else:
            self._stagnant_count = 1 if not is_success else 0

        # 3. State cycle detection (A -> B -> A)
        visit_count = self._visited_states.get(state_hash, 0) + 1
        self._visited_states[state_hash] = visit_count
        if visit_count >= 3 and state_hash != self._last_state_hash:
            return FailureReport(
                action_id=action.action_id,
                action_type=action.action_type,
                category=FailureCategory.STATE_CYCLE_DETECTED,
                diagnosis=f"Agent returned to an identical UI state {visit_count} times, indicating a cyclic loop.",
                evidence_observed=[f"State fingerprint {state_hash[:8]} visited {visit_count} times"],
                suggested_remediation_direction="Break cycle by selecting an unvisited transition or backtracking",
                is_transient=False,
            )

        # 4. Failed action retry detection
        if self._last_action_failed and self._last_action_hash == act_hash and self._stagnant_count < self._max_stagnant_steps:
            return FailureReport(
                action_id=action.action_id,
                action_type=action.action_type,
                category=FailureCategory.FAILED_ACTION_RETRY,
                diagnosis="The exact same failed action was repeated without strategy adaptation.",
                evidence_observed=[f"Action hash {act_hash[:8]} failed repeatedly"],
                suggested_remediation_direction="Replan with a distinct alternative strategy directive",
                is_transient=False,
            )

        # 5. Action repetition tracking in sliding window
        self._action_history.append(act_hash)
        repeat_count = self._action_history.count(act_hash)
        if repeat_count >= 3:
            return FailureReport(
                action_id=action.action_id,
                action_type=action.action_type,
                category=FailureCategory.REPETITIVE_ACTION_DETECTED,
                diagnosis=f"Action was dispatched {repeat_count} times in the recent sliding window.",
                evidence_observed=[f"Action hash {act_hash[:8]} dispatched {repeat_count} times"],
                suggested_remediation_direction="Diversify action pathway; avoid repetitive execution",
                is_transient=False,
            )

        # Update tracking state
        self._last_state_hash = state_hash
        self._last_action_hash = act_hash
        self._last_action_failed = not is_success
        return None



class CognitiveFailureAnalyst:
    """Diagnoses action and milestone failures without planning or executing recoveries.

    Safety Invariant:
    Produces ONLY FailureReport. Never emits actions, executes commands, or alters environment.
    """

    def analyze_failure(
        self,
        action: AbstractAction,
        pre_obs: CurrentStateObservation,
        post_obs: CurrentStateObservation,
        exec_outcome: ActionExecutionOutcome,
        world_model: Optional[AgentWorldModel] = None,
    ) -> FailureReport:
        """Produce a structured diagnosis from pre/post observations and execution outcome."""
        act_type = action.action_type
        err_msg = exec_outcome.error_message or ""
        reason = exec_outcome.verification_reason or ""
        evidence: List[str] = []

        # 0. COM / RPC disconnect or dead window check
        if any(kw in err_msg for kw in ("RPC_E_DISCONNECTED", "ELEMENTNOTAVAILABLE", "0x80010108", "0x800401FD")):
            evidence.append(f"COM Automation disconnect or dead window: {err_msg}")
            return FailureReport(
                action_id=action.action_id,
                action_type=act_type,
                category=FailureCategory.DEAD_WINDOW_HANDLE,
                diagnosis="UIA / COM connection to target window disconnected or element became unavailable.",
                evidence_observed=evidence,
                suggested_remediation_direction="Re-query UI element tree or switch to physical coordinate / hotkey fallback",
                is_transient=False,
            )

        # 1. Window action failure
        if act_type in (AbstractActionType.LAUNCH_APPLICATION, AbstractActionType.FOCUS_WINDOW):
            app_name = str(
                action.parameters.get("application_name", action.parameters.get("app_name", action.target.name if action.target else ""))
            ).lower()
            if not post_obs.target_app_exists and not any(app_name in (w.get("title", "")).lower() for w in post_obs.visible_windows):
                evidence.append(f"Process/window for '{app_name}' not found in Win32 visible windows list")
                return FailureReport(
                    action_id=action.action_id,
                    action_type=act_type,
                    category=FailureCategory.TARGET_NOT_FOUND,
                    diagnosis=f"Application '{app_name}' failed to launch or open a visible window.",
                    evidence_observed=evidence,
                    suggested_remediation_direction="Verify application executable path or check system Start Menu",
                    is_transient=False,
                )
            elif not post_obs.target_app_is_active:
                evidence.append(f"Foreground window is '{post_obs.active_window_title}', expected '{app_name}'")
                return FailureReport(
                    action_id=action.action_id,
                    action_type=act_type,
                    category=FailureCategory.WINDOW_NOT_FOCUSED,
                    diagnosis=f"Application '{app_name}' is open but not in foreground focus.",
                    evidence_observed=evidence,
                    suggested_remediation_direction="Focus the existing application window via Win32 or click",
                    is_transient=True,
                )

        # 2. Text entry mismatch
        if act_type == AbstractActionType.TYPE_TEXT:
            expected_text = str(action.parameters.get("text", action.parameters.get("query", "")))
            evidence.append(f"Expected text '{expected_text}' not observed in post-action OCR or UIA buffers")
            if post_obs.active_window_title != pre_obs.active_window_title:
                evidence.append(f"Active window shifted during typing from '{pre_obs.active_window_title}' to '{post_obs.active_window_title}'")
                return FailureReport(
                    action_id=action.action_id,
                    action_type=act_type,
                    category=FailureCategory.WINDOW_NOT_FOCUSED,
                    diagnosis="Active window lost focus during text entry attempt.",
                    evidence_observed=evidence,
                    suggested_remediation_direction="Re-focus input field and retry typing",
                    is_transient=True,
                )
            return FailureReport(
                action_id=action.action_id,
                action_type=act_type,
                category=FailureCategory.TEXT_ENTRY_MISMATCH,
                diagnosis=f"Typed text '{expected_text}' was not accepted or rendered by target control.",
                evidence_observed=evidence,
                suggested_remediation_direction="Try clipboard atomic injection or click to focus input control first",
                is_transient=True,
            )

        # 3. Pointer click failure
        if act_type in (AbstractActionType.CLICK, AbstractActionType.DOUBLE_CLICK, AbstractActionType.RIGHT_CLICK):
            evidence.append(f"No observable desktop state delta detected after clicking target '{action.target.name if action.target else 'unnamed'}'")
            return FailureReport(
                action_id=action.action_id,
                action_type=act_type,
                category=FailureCategory.TARGET_UNRESPONSIVE,
                diagnosis=f"Click on '{action.target.name if action.target else 'target'}' produced no observable UI state change.",
                evidence_observed=evidence,
                suggested_remediation_direction="Re-ground target coordinates with visual verification or retry with settle pause",
                is_transient=True,
            )

        # 4. General postcondition failure
        evidence.append(f"Verification reason: {reason or err_msg or 'Postcondition contract unsatisfied'}")
        return FailureReport(
            action_id=action.action_id,
            action_type=act_type,
            category=FailureCategory.POSTCONDITION_UNSATISFIED,
            diagnosis=f"Action postcondition was not verified: {reason or err_msg or 'state unchanged'}",
            evidence_observed=evidence,
            suggested_remediation_direction="Re-evaluate observation and compose alternative action sequence",
            is_transient=True,
        )
