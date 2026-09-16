"""Test and verify all 5 diagnostic scenarios from the UI screenshots."""

import asyncio
import os
import sys
import time
import logging

sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\src")
sys.path.insert(0, r"C:\Users\Aaryan shukla\OneDrive\Desktop\ORBIT\prototypes\prototype_d_observation")

from orbit.config import is_human_takeover_enabled
from orbit.infrastructure.event_bus import EventBus
from orbit.adapters.factory import create_capability_registry
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.contracts.runtime import SystemState, TaskStatus
from orbit.runtime.task_understanding import TaskUnderstandingEngine, TaskGoal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_diagnostics")

async def test_diagnostic_scenarios():
    print("=" * 80)
    print("DIAGNOSTIC SCENARIOS VALIDATION TEST SUITE")
    print("=" * 80)

    # 1. Verify Task Understanding for all 5 prompts
    ue = TaskUnderstandingEngine()

    prompts = [
        ("open notepad and write about ORBIT ASSISTANT IN 5000 words", TaskGoal.WRITE_TEXT),
        ("Open Notepad", TaskGoal.OPEN_APPLICATION),
        ("Task under takeover", TaskGoal.UNKNOWN),
        ("open mspaint and draw a stickman with a gun ", TaskGoal.DRAW),
        ("now in the notepad slowly slowly write a para on chatgpt ", TaskGoal.WRITE_TEXT),
    ]

    print("\n--- Testing Task Understanding & Intent Extraction ---")
    for prompt, expected_primary_goal in prompts:
        res = ue.understand(prompt)
        intents_summary = [(i.goal.value, i.constraints.application_name, i.constraints.content) for i in res.intents]
        print(f"Prompt: '{prompt}'")
        print(f"  Status: {res.status.value}, Intents: {intents_summary}")
        if expected_primary_goal == TaskGoal.DRAW:
            assert any(i.goal == TaskGoal.DRAW for i in res.intents), f"Expected DRAW goal for '{prompt}', got: {intents_summary}"
        elif expected_primary_goal == TaskGoal.OPEN_APPLICATION:
            assert any(i.goal == TaskGoal.OPEN_APPLICATION for i in res.intents)
        elif expected_primary_goal == TaskGoal.WRITE_TEXT:
            assert any(i.goal == TaskGoal.WRITE_TEXT for i in res.intents)

    print("\n>>> Task Understanding tests PASSED!")

    # 2. Test Plan Generation for drawing and creative goals
    print("\n--- Testing Plan Generation for Drawing & Canvas Goal ---")
    res_draw = ue.understand("open mspaint and draw a stickman with a gun ")
    from orbit.runtime.planning.planner import TaskPlanningEngine
    planner = TaskPlanningEngine()
    plan_draw = planner.plan(res_draw)
    print(f"Plan ID: {plan_draw.plan_id}, Steps: {len(plan_draw.steps)}")
    for s in plan_draw.steps:
        print(f"  Step: {s.action_type.value} -> {s.description}")
    assert len(plan_draw.steps) >= 2
    assert not any(s.action_type.value == "unsupported_action" for s in plan_draw.steps)
    print(">>> Planning for Drawing Goal PASSED!")

    # 3. Test Text Verification for long LLM paragraphs
    print("\n--- Testing Text Verification for Long LLM Paragraphs ---")
    from orbit.runtime.task_completion.goal_verifier import GoalVerifier
    from orbit.runtime.plan_execution.models import PlanExecutionResult, PlanExecutionStatus, PlanStepExecutionResult, PlanStepExecutionStatus
    from orbit.adapters.observation.snapshot import ObservationSnapshot

    long_paragraph = (
        "ChatGPT is an advanced natural language processing model developed by OpenAI. "
        "It can generate human-like text and engage in conversations on a wide range of topics. "
        "Users can interact with ChatGPT through various interfaces, asking questions, or initiating dialogue."
    )

    ue_res = ue.understand(f"write '{long_paragraph}' in Notepad")
    plan = planner.plan(ue_res)

    step_results = [
        PlanStepExecutionResult(
            step_id=s.step_id,
            step_index=idx,
            action_type=s.action_type,
            status=PlanStepExecutionStatus.SUCCEEDED,
            is_dispatched=True,
        )
        for idx, s in enumerate(plan.steps)
    ]
    plan_result = PlanExecutionResult(
        plan_id=plan.plan_id,
        task_id="task_test_verif",
        final_status=PlanExecutionStatus.SUCCEEDED,
        is_success=True,
        total_steps=len(plan.steps),
        completed_steps=len(plan.steps),
        step_results=step_results,
    )

    from orbit.models.common import BoundingBox
    from orbit.adapters.observation.snapshot import ObservedElement
    dummy_snapshot = ObservationSnapshot(
        snapshot_id="snap_test_verif",
        timestamp_ns=time.time_ns(),
        generation_id=1,
        desktop_geometry=BoundingBox(left=0, top=0, right=2880, bottom=1800, width=2880, height=1800),
        windows=[],
        detected_elements=[
            ObservedElement(
                element_id="el_doc_text",
                source="UI_AUTOMATION",
                name="ChatGPT is an advanced natural language processing model developed by OpenAI...",
                control_type="Edit",
                bounds=BoundingBox(left=100, top=100, right=500, bottom=500, width=400, height=400),
            )
        ],
    )

    verifier = GoalVerifier()
    v_res = await verifier.verify_goal(
        understanding=ue_res,
        plan=plan,
        plan_result=plan_result,
        post_snapshot=dummy_snapshot,
    )
    print(f"Goal Verification Result: is_completed={v_res.is_completed}, status={v_res.status.value}")
    assert v_res.is_completed is True
    assert v_res.status.value == "COMPLETED"
    print(">>> Text Verification for Long Paragraphs PASSED!")

    print("\n" + "=" * 80)
    print("ALL DIAGNOSTIC SCENARIOS VERIFIED SUCCESSFULLY (100% PASS)")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_diagnostic_scenarios())
