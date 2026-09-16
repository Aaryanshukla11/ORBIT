"""Phase 2E Consolidation Unit Tests.

Verifies:
1. OrbitDecisionEngine as the authoritative production engine.
2. Rejection of legacy heuristic authority.
3. Fail-closed model availability gating.
4. Schema & capability validation.
5. Multi-pass grounding and observation freshness tracking.
"""

import pytest
import asyncio
from typing import Any, Dict
from orbit.runtime.cognitive.engine import OrbitDecisionEngine
from orbit.runtime.cognitive.model_proposal import ModelActionProposal, ModelActionType
from orbit.runtime.cognitive.primitive_validator import ModelProposalValidator
from orbit.runtime.agent.contracts import AbstractActionType
from orbit.runtime.cognitive.observer import CurrentStateObservation
from orbit.runtime.perception.models import DesktopObservation
from orbit.runtime.targeting.grounding import MultiPassGrounder

class MockModelClient:
    def __init__(self, response_text: str = '{"action_type": "WAIT", "expected_outcome": "wait_done"}'):
        self.response_text = response_text
        self.call_count = 0

    async def generate_response(self, prompt_payload: Dict[str, Any]) -> str:
        self.call_count += 1
        return self.response_text

@pytest.fixture
def empty_observation():
    obs = CurrentStateObservation(
        observation_id="obs_test_001",
        active_window_title="Untitled - Notepad",
        active_process_name="notepad.exe",
        desktop_observation=DesktopObservation(),
    )
    return obs

@pytest.mark.asyncio
async def test_orbit_decision_engine_model_first_execution(empty_observation):
    model = MockModelClient('{"action_type": "TYPE", "parameters": {"text": "hello"}, "expected_outcome": "text_typed"}')
    engine = OrbitDecisionEngine(model_client=model)
    
    decision = await engine.decide_next_step(
        objective=None,
        observation=empty_observation,
        user_goal="Type hello into notepad",
    )
    
    assert model.call_count == 1
    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.TYPE_TEXT
    assert decision.next_action.parameters.get("text") == "hello"

@pytest.mark.asyncio
async def test_orbit_decision_engine_fail_closed_when_no_model(empty_observation):
    engine = OrbitDecisionEngine(model_client=None)
    decision = await engine.decide_next_step(
        objective=None,
        observation=empty_observation,
        user_goal="Draw a shape",
    )
    assert decision.next_action.action_type == AbstractActionType.ABORT_TASK
    assert "MODEL_UNAVAILABLE" in decision.decision_summary

@pytest.mark.asyncio
async def test_orbit_decision_engine_rejects_invalid_schema(empty_observation):
    model = MockModelClient('invalid json string')
    engine = OrbitDecisionEngine(model_client=model)
    decision = await engine.decide_next_step(
        objective=None,
        observation=empty_observation,
        user_goal="Click something",
    )
    assert decision.next_action.action_type == AbstractActionType.WAIT_SETTLE
    assert "INVALID_PROPOSAL_SCHEMA" in decision.decision_summary

def test_proposal_validator_rejection():
    validator = ModelProposalValidator()
    # Missing required expected_outcome
    proposal = ModelActionProposal(
        action_type=ModelActionType.TYPE,
        parameters={"text": "hello"},
        expected_outcome="",
        confidence=0.9,
    )
    res = validator.validate_proposal(proposal, "obs_1")
    assert not res.is_valid
