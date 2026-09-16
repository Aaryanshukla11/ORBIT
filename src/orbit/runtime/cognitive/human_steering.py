"""Human-in-the-Loop Steering & Safety Policy Subsystem.

Phase 3E (Astra 6 Modernization):
Provides real-time steering interrupts, sensitive action risk evaluation,
approval gating for irreversible operations, and seamless human takeover coordination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType

logger = logging.getLogger(__name__)


class ActionRiskLevel(str, Enum):
    """Safety classification of proposed agent actions."""

    SAFE = "SAFE"                              # Standard UI interactions (Click, Scroll, Select, Launch verified apps)
    ELEVATED_RISK = "ELEVATED_RISK"            # Modifying settings, overwriting existing files, submitting web forms
    CRITICAL_RISK = "CRITICAL_RISK"            # Permanent file deletion, disk operations, security/auth credentials, payments


class SteeringInterruptType(str, Enum):
    """Types of human intervention signals during agent execution."""

    PAUSE = "PAUSE"
    RESUME = "RESUME"
    ABORT = "ABORT"
    STEER_PROMPT = "STEER_PROMPT"              # User injected new instruction or constraint mid-task
    PHYSICAL_TAKEOVER = "PHYSICAL_TAKEOVER"    # User moved physical mouse or pressed physical keyboard


class HumanApprovalRequest(BaseModel):
    """A formal request for user confirmation before executing an elevated or critical action."""

    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:8]}")
    action: AbstractAction
    risk_level: ActionRiskLevel
    risk_reason: str
    is_approved: Optional[bool] = None
    approval_token: Optional[str] = None
    requested_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HumanTakeoverSteeringManager:
    """Manages human steering interrupts, physical takeover safety, and sensitive action gating."""

    # Keywords associated with critical irreversible or sensitive operations
    CRITICAL_KEYWORDS = {
        "delete", "remove", "format", "rmdir", "del ", "drop table", "shutdown",
        "regedit", "reg delete", "password", "secret", "token", "credit card", "payment",
        "purchase", "wire transfer", "sudo", "truncate", "wipe",
    }

    # Keywords associated with elevated risk (file overwrites, system settings)
    ELEVATED_KEYWORDS = {
        "overwrite", "replace", "save as", "modify setting", "install", "uninstall",
        "close without saving", "discard", "submit", "send email",
    }

    def __init__(self, strict_approval_mode: bool = True) -> None:
        self.strict_approval_mode = strict_approval_mode
        self._is_paused: bool = False
        self._pending_steering_prompt: Optional[str] = None
        self._active_approval_requests: Dict[str, HumanApprovalRequest] = {}
        self._approved_tokens: Set[str] = set()

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def inject_steering_prompt(self, prompt: str) -> None:
        """Inject a human guidance instruction to be prioritized in the next reasoning cycle."""
        logger.info("[HumanSteering] User injected steering prompt: '%s'", prompt)
        self._pending_steering_prompt = prompt

    def consume_steering_prompt(self) -> Optional[str]:
        """Retrieve and clear the pending steering guidance prompt."""
        prompt = self._pending_steering_prompt
        self._pending_steering_prompt = None
        return prompt

    def pause_execution(self, reason: str = "User requested pause") -> None:
        """Pause agent physical dispatch."""
        logger.info("[HumanSteering] Execution paused: %s", reason)
        self._is_paused = True

    def resume_execution(self) -> None:
        """Resume agent physical dispatch."""
        logger.info("[HumanSteering] Execution resumed by user.")
        self._is_paused = False

    def evaluate_action_safety(self, action: AbstractAction) -> Tuple[ActionRiskLevel, str]:
        """Classify action risk level based on action type, parameters, and sensitive keywords."""
        act_type = action.action_type
        params = action.parameters or {}
        param_str = str(params).lower()
        t_name = (action.target.name if action.target else "").lower()
        combined_text = f"{param_str} {t_name}"

        # 1. Check for critical risk triggers
        for kw in self.CRITICAL_KEYWORDS:
            if kw in combined_text:
                return ActionRiskLevel.CRITICAL_RISK, f"Action references critical sensitive keyword: '{kw}'"

        # 2. Check for elevated risk triggers
        for kw in self.ELEVATED_KEYWORDS:
            if kw in combined_text:
                return ActionRiskLevel.ELEVATED_RISK, f"Action references elevated operation keyword: '{kw}'"

        # Default safe
        return ActionRiskLevel.SAFE, "Action is classified as standard non-destructive operation"

    def requires_approval(self, action: AbstractAction) -> Tuple[bool, Optional[HumanApprovalRequest]]:
        """Determine if an action requires explicit user approval before execution."""
        risk_level, reason = self.evaluate_action_safety(action)

        if risk_level == ActionRiskLevel.SAFE:
            return False, None

        if not self.strict_approval_mode and risk_level == ActionRiskLevel.ELEVATED_RISK:
            return False, None

        # Create approval request
        req = HumanApprovalRequest(
            action=action,
            risk_level=risk_level,
            risk_reason=reason,
        )
        self._active_approval_requests[req.request_id] = req
        return True, req

    def grant_approval(self, request_id: str) -> str:
        """Grant user approval for a pending sensitive action, returning an approval token."""
        if request_id not in self._active_approval_requests:
            raise KeyError(f"Approval request '{request_id}' not found")

        token = f"appr_tok_{uuid4().hex[:12]}"
        req = self._active_approval_requests[request_id]
        req.is_approved = True
        req.approval_token = token
        self._approved_tokens.add(token)
        logger.info("[HumanSteering] User GRANTED approval for request %s (Token: %s)", request_id, token)
        return token

    def deny_approval(self, request_id: str, reason: str = "User rejected operation") -> None:
        """Deny user approval for a pending sensitive action."""
        if request_id in self._active_approval_requests:
            req = self._active_approval_requests[request_id]
            req.is_approved = False
            logger.info("[HumanSteering] User DENIED approval for request %s: %s", request_id, reason)

    def is_token_valid(self, approval_token: Optional[str]) -> bool:
        """Verify validity of a sensitive action approval token."""
        return approval_token is not None and approval_token in self._approved_tokens
