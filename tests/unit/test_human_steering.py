"""Unit tests for HumanTakeoverSteeringManager (Phase 3E)."""

import pytest
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.human_steering import (
    ActionRiskLevel,
    HumanApprovalRequest,
    HumanTakeoverSteeringManager,
)


def test_human_steering_pause_and_resume():
    """Verify pause and resume states."""
    manager = HumanTakeoverSteeringManager()
    assert manager.is_paused is False

    manager.pause_execution("Testing pause")
    assert manager.is_paused is True

    manager.resume_execution()
    assert manager.is_paused is False


def test_human_steering_prompt_injection():
    """Verify steering guidance prompt injection and consumption."""
    manager = HumanTakeoverSteeringManager()

    manager.inject_steering_prompt("Use dark mode instead of light mode")
    consumed = manager.consume_steering_prompt()
    assert consumed == "Use dark mode instead of light mode"

    # Subsequent consumption is empty
    assert manager.consume_steering_prompt() is None


def test_human_steering_evaluates_risk_levels():
    """Verify risk classification for safe, elevated, and critical actions."""
    manager = HumanTakeoverSteeringManager()

    # Safe click
    safe_act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="View Tab"))
    risk_safe, _ = manager.evaluate_action_safety(safe_act)
    assert risk_safe == ActionRiskLevel.SAFE

    # Elevated risk (overwrite)
    elev_act = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="Overwrite File"),
    )
    risk_elev, _ = manager.evaluate_action_safety(elev_act)
    assert risk_elev == ActionRiskLevel.ELEVATED_RISK

    # Critical risk (permanent deletion)
    crit_act = AbstractAction(
        action_type=AbstractActionType.TYPE_TEXT,
        parameters={"text": "del /f /q C:\\Users\\data.bin"},
    )
    risk_crit, reason_crit = manager.evaluate_action_safety(crit_act)
    assert risk_crit == ActionRiskLevel.CRITICAL_RISK
    assert "del" in reason_crit


def test_human_steering_approval_token_lifecycle():
    """Verify approval gating requires token and grants valid execution token upon approval."""
    manager = HumanTakeoverSteeringManager(strict_approval_mode=True)

    crit_act = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="Delete Database Record"),
    )

    needs_appr, req = manager.requires_approval(crit_act)
    assert needs_appr is True
    assert req is not None
    assert req.risk_level == ActionRiskLevel.CRITICAL_RISK

    # Unapproved token validation fails
    assert manager.is_token_valid("invalid_token") is False

    # Grant approval
    token = manager.grant_approval(req.request_id)
    assert token.startswith("appr_tok_")
    assert manager.is_token_valid(token) is True
    assert req.is_approved is True


def test_human_steering_denial():
    """Verify denial marks request unapproved."""
    manager = HumanTakeoverSteeringManager()

    crit_act = AbstractAction(
        action_type=AbstractActionType.CLICK,
        target=SemanticTarget(name="Format Drive D:"),
    )

    needs_appr, req = manager.requires_approval(crit_act)
    assert needs_appr is True

    manager.deny_approval(req.request_id, reason="User cancelled risky operation")
    assert req.is_approved is False
    assert manager.is_token_valid(req.approval_token) is False
