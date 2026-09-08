"""Unit tests for the 5 core AI-Native Agent components (Milestone M2.0)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.agent.contracts import (
    ActionExecutionOutcome,
    ActionType,
    AgentAction,
    ExpectedState,
    SemanticTarget,
    VerificationStrategy,
)
from orbit.runtime.agent.perception_router import (
    PerceptionLayer,
    PerceptionQueryResult,
    PerceptionRouter,
)
from orbit.runtime.agent.progress_graph import (
    ProgressGraph,
    SubgoalNode,
    SubgoalStatus,
)
from orbit.runtime.agent.state import (
    AgentStateManager,
    DesktopStateSnapshot,
    TaskMemory,
)
from orbit.runtime.agent.verifier import AgentStateTransitionVerifier
from orbit.runtime.model_runtime.router import ModelRouter
from orbit.runtime.models.models import ModelGenerateResponse
from orbit.runtime.targeting import (
    EvidenceBasedTargetLocator,
    ResolvedTarget,
    SafeActionPoint,
    TargetBoundingBox,
    TargetEvidence,
    TargetResolutionResult,
    TargetResolutionStatus,
)


# =============================================================================
# 1. Agent State Manager Tests
# =============================================================================

def test_agent_state_manager_maintains_memory_and_snapshots():
    sm = AgentStateManager(task_id="task_123", goal="Open Paint and draw a circle")
    assert sm.task_id == "task_123"
    assert sm.goal == "Open Paint and draw a circle"

    # Set variables and cache
    sm.set_variable("current_shape", "circle")
    assert sm.get_variable("current_shape") == "circle"
    assert sm.get_variable("missing_key", "default") == "default"

    sm.cache_window("mspaint", 998877)
    assert sm.get_cached_window("mspaint") == 998877
    assert sm.get_cached_window("nonexistent") is None

    sm.add_note("Discovered canvas element at index 0")
    assert len(sm.memory.notes) == 1

    # Record snapshots
    snp1 = DesktopStateSnapshot(
        active_window_title="Desktop",
        active_window_hwnd=1122,
        target_app_exists=False,
    )
    sm.record_snapshot(snp1)
    assert sm.get_latest_snapshot().active_window_title == "Desktop"

    summary = sm.get_summary()
    assert summary["task_id"] == "task_123"
    assert summary["variables_count"] == 1
    assert summary["discovered_windows"]["mspaint"] == 998877


# =============================================================================
# 2. Agent Action Protocol Tests
# =============================================================================

def test_agent_action_protocol_enforces_schemas_and_forbids_coordinates():
    # Valid actions
    act1 = AgentAction(
        action_type=ActionType.CLICK,
        semantic_target=SemanticTarget(name="Submit", role="button", context="LoginForm"),
        expected_effect="Form submitted",
        verification_strategy=VerificationStrategy.AUTO_ROUTED,
    )
    assert act1.action_type == ActionType.CLICK
    assert act1.semantic_target.name == "Submit"

    act2 = AgentAction(
        action_type=ActionType.TYPE,
        parameters={"text": "Hello world"},
        expected_effect="Text entered",
    )
    assert act2.parameters["text"] == "Hello world"

    # Strict invariant: Must reject static physical screen coordinates
    with pytest.raises(ValueError):
        AgentAction(
            action_type=ActionType.CLICK,
            parameters={"x": 500, "y": 300},
        )

    with pytest.raises(ValueError):
        AgentAction(
            action_type=ActionType.CLICK,
            parameters={"screen_x": 100, "screen_y": 200},
        )


# =============================================================================
# 3. Perception Router Tests
# =============================================================================

@pytest.mark.asyncio
async def test_perception_router_hierarchy_resolution():
    mock_locator = MagicMock(spec=EvidenceBasedTargetLocator)
    mock_router = MagicMock(spec=ModelRouter)

    # 1. Tier 2: UIA resolution
    bbox = TargetBoundingBox(left=100, top=200, right=250, bottom=250)
    safe_pt = SafeActionPoint(x=175, y=225, bounding_box=bbox, desktop_generation_id=1)
    ev = TargetEvidence(source="UI_AUTOMATION", name="Save")
    rt = ResolvedTarget(
        target_id="tgt_save",
        bounding_box=bbox,
        safe_point=safe_pt,
        confidence=0.96,
        evidence=ev,
        observation_id="obs_1",
        desktop_generation_id=1,
    )
    mock_locator.locate_target = AsyncMock(
        return_value=TargetResolutionResult(status=TargetResolutionStatus.RESOLVED, target=rt)
    )

    p_router = PerceptionRouter(target_locator=mock_locator, model_router=mock_router)
    res = await p_router.query_target(SemanticTarget(name="Save", role="button"))
    assert res.is_resolved is True
    assert res.layer_used == PerceptionLayer.UIA
    assert res.coordinates == (175, 225)

    # 2. Tier 4: Vision Model fallback when UIA and OCR fail
    mock_locator.locate_target = AsyncMock(
        return_value=TargetResolutionResult(status=TargetResolutionStatus.NOT_FOUND)
    )
    mock_router.generate = AsyncMock(
        return_value=ModelGenerateResponse(model_id="gpt-4o", content="Target located at center region")
    )
    res_vision = await p_router.query_target(SemanticTarget(name="UnlabelledIcon", role="icon"))
    assert res_vision.is_resolved is True
    assert res_vision.layer_used == PerceptionLayer.VISION_MODEL


# =============================================================================
# 4. Agent State Transition Verifier Tests
# =============================================================================

@pytest.mark.asyncio
async def test_agent_state_transition_verifier_evaluates_expected_state():
    verifier = AgentStateTransitionVerifier()

    pre = DesktopStateSnapshot(active_window_title="Desktop", active_window_hwnd=100, target_app_exists=False)
    post = DesktopStateSnapshot(
        active_window_title="Paint",
        active_window_hwnd=200,
        target_app_exists=True,
        visible_windows=[{"title": "Paint", "class_name": "MSPaintApp", "hwnd": 200}],
    )

    # Verify App Launch
    action_launch = AgentAction(
        action_type=ActionType.LAUNCH_APPLICATION,
        parameters={"app_name": "mspaint"},
        expected_state=ExpectedState(description="Paint window visible", strategy=VerificationStrategy.WIN32_WINDOW),
    )
    outcome = await verifier.verify_action_outcome(
        action=action_launch,
        dispatch_success=True,
        pre_state=pre,
        post_state=post,
    )
    assert outcome.verified is True
    assert outcome.expected_effect_observed is True
    assert "verified visible and active" in outcome.verification_reason

    # Verify Click with Expected Window Title
    action_click = AgentAction(
        action_type=ActionType.CLICK,
        semantic_target=SemanticTarget(name="FileMenu"),
        expected_state=ExpectedState(
            description="Menu opens",
            strategy=VerificationStrategy.WIN32_WINDOW,
            expected_window_title="Paint",
        ),
    )
    outcome_click = await verifier.verify_action_outcome(
        action=action_click,
        dispatch_success=True,
        pre_state=pre,
        post_state=post,
    )
    assert outcome_click.verified is True


# =============================================================================
# 5. Agent Memory + Progress Graph Tests
# =============================================================================

def test_progress_graph_tracks_subgoals_and_detects_loops():
    pg = ProgressGraph(goal="Create a presentation")

    # Add subgoals with dependencies: A -> B -> C -> D
    sg_a = pg.add_subgoal("Launch PowerPoint", node_id="sg_a")
    sg_b = pg.add_subgoal("Create Blank Slide", dependencies=["sg_a"], node_id="sg_b")
    sg_c = pg.add_subgoal("Add Title Text", dependencies=["sg_b"], node_id="sg_c")
    sg_d = pg.add_subgoal("Save Presentation", dependencies=["sg_c"], node_id="sg_d")

    assert len(pg.nodes) == 4
    assert not pg.is_all_completed

    # First active is A
    active = pg.get_active_subgoal()
    assert active.node_id == "sg_a"

    # Start and complete A
    pg.start_subgoal("sg_a", action_id="act_1")
    assert pg.get_subgoal("sg_a").status == SubgoalStatus.IN_PROGRESS
    pg.complete_subgoal("sg_a", evidence={"window": "PowerPoint"})
    assert pg.get_subgoal("sg_a").status == SubgoalStatus.COMPLETED

    # Next active is B
    active_b = pg.get_active_subgoal()
    assert active_b.node_id == "sg_b"
    pg.start_subgoal("sg_b", action_id="act_2")
    pg.complete_subgoal("sg_b")

    # Next active is C
    active_c = pg.get_active_subgoal()
    assert active_c.node_id == "sg_c"
    pg.start_subgoal("sg_c", action_id="act_3")
    pg.complete_subgoal("sg_c")

    # Next active is D
    active_d = pg.get_active_subgoal()
    assert active_d.node_id == "sg_d"
    pg.start_subgoal("sg_d", action_id="act_4")
    pg.complete_subgoal("sg_d")

    assert pg.is_all_completed is True

    # Test Loop / Thrashing Detection
    pg_loop = ProgressGraph(goal="Loop test", max_repeated_cycles=3)
    sg_retry = pg_loop.add_subgoal("Flaky step", node_id="sg_flaky")
    
    for _ in range(2):
        pg_loop.start_subgoal("sg_flaky")
        can_retry, loop_det = pg_loop.fail_subgoal_attempt("sg_flaky", "Element not found")
        assert can_retry is True
        assert loop_det is False

    # 3rd failure hits repeated cycle threshold
    pg_loop.start_subgoal("sg_flaky")
    can_retry_3, loop_det_3 = pg_loop.fail_subgoal_attempt("sg_flaky", "Element not found again")
    assert can_retry_3 is False
    assert loop_det_3 is True
    assert pg_loop.get_subgoal("sg_flaky").status == SubgoalStatus.FAILED
