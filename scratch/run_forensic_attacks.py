"""Forensic verification script for Step 5 (Invalid Proposal Attack) and Step 6 (Legacy Engine Attack)."""

import asyncio
from unittest.mock import MagicMock, AsyncMock

from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.engine import OrbitDecisionEngine, CognitiveDecisionEngine
from orbit.runtime.cognitive.agent_decision import AgentDecisionEngine
from orbit.runtime.cognitive.models import CurrentStateObservation, StructuredObjective, AbstractActionType, AbstractAction
from orbit.runtime.cognitive.primitive_validator import ModelProposalValidator
from orbit.runtime.cognitive.model_proposal import ModelActionProposal, ModelActionType, TargetSelector


async def run_attacks():
    print("=== STEP 5: INVALID PROPOSAL ATTACK ===")
    validator = ModelProposalValidator()

    # 1. Stage 1 Schema: Missing expected_outcome
    p_schema = ModelActionProposal(
        action_type=ModelActionType.CLICK,
        expected_outcome="",
    )
    res_schema = validator.validate_proposal(p_schema, current_observation_id="obs_1")
    assert not res_schema.is_valid
    assert res_schema.failed_stage.value == "SCHEMA"
    print(f"  [PASS] Stage 1 (SCHEMA) rejection verified: {res_schema.failure_reason}")

    # 2. Stage 3 Safety: Restricted security keyword
    p_safety = ModelActionProposal(
        action_type=ModelActionType.TYPE,
        parameters={"text": "powershell -e bad_payload"},
        expected_outcome="Payload typed",
    )
    res_safety = validator.validate_proposal(p_safety, current_observation_id="obs_1")
    assert not res_safety.is_valid
    assert res_safety.failed_stage.value == "SAFETY"
    print(f"  [PASS] Stage 3 (SAFETY) rejection verified: {res_safety.failure_reason}")

    # 3. Stage 4 Grounding: Stale observation ID
    p_stale = ModelActionProposal(
        action_type=ModelActionType.CLICK,
        target_selector=TargetSelector(name="save_btn", role="button", observation_id="obs_old"),
        expected_outcome="Button clicked",
    )
    res_stale = validator.validate_proposal(p_stale, current_observation_id="obs_fresh")
    assert not res_stale.is_valid
    assert res_stale.failed_stage.value == "GROUNDING"
    print(f"  [PASS] Stage 4 (GROUNDING - STALE OBS) rejection verified: {res_stale.failure_reason}")

    # 4. Stage 4 Grounding: Out-of-bounds normalized coordinates
    p_bad_coords = ModelActionProposal(
        action_type=ModelActionType.CLICK,
        target_selector=TargetSelector(name="bad_target", bounds=[1200, 500, 1500, 800]),
        expected_outcome="should fail",
    )
    res_coords = validator.validate_proposal(p_bad_coords, current_observation_id="obs_1")
    assert not res_coords.is_valid
    assert res_coords.failed_stage.value == "GROUNDING"
    print(f"  [PASS] Stage 4 (GROUNDING - OUT OF BOUNDS) rejection verified: {res_coords.failure_reason}")

    # 5. CoordinatePolicyViolation on AbstractAction parameters
    try:
        AbstractAction(
            action_type=AbstractActionType.CLICK,
            parameters={"coordinates": [{"x": 100, "y": 200}]},
        )
        print("  [FAIL] Coordinates were not blocked in AbstractAction")
    except Exception as e:
        print(f"  [PASS] Physical Coordinate Policy strictly enforced: {type(e).__name__} -> {e}")

    print("\n=== STEP 6: LEGACY ENGINE ATTACK ===")
    def legacy_boom(*args, **kwargs):
        raise RuntimeError("FATAL: Legacy deterministic engine was illegally called!")

    CognitiveDecisionEngine._decide_deterministic = legacy_boom
    CognitiveDecisionEngine.decide_next_step = legacy_boom
    AgentDecisionEngine.decide_next_action = legacy_boom

    # Run OrbitDecisionEngine
    model_json = '{"action_type": "LAUNCH", "parameters": {"application_name": "notepad"}, "expected_outcome": "notepad open", "confidence": 1.0, "diagnostic_reasoning": "model launch"}'
    engine = OrbitDecisionEngine(model_client=AsyncMock(return_value=model_json))
    obs = CurrentStateObservation(observation_id="obs_attack")
    decision = await engine.decide_next_step(
        objective=StructuredObjective(raw_prompt="test", user_goal="test", end_condition="done"),
        observation=obs,
    )
    assert decision.next_action.action_type == AbstractActionType.LAUNCH_APPLICATION
    assert decision.next_action.parameters.get("application_name") == "notepad"
    print("  [PASS] OrbitDecisionEngine successfully decided next step without triggering legacy boom")


if __name__ == "__main__":
    asyncio.run(run_attacks())
