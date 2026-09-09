"""Phase 1 Unit Tests: Cognitive State, Subgoal DAG, Task Memory & Ambiguity Resolution.

Tests adherence to ASTRA evaluation dimensions:
- Dimension 1: Hierarchical Intent Decomposition & Subgoal Status Tracking
- Dimension 2: Dependency DAG, Cycle Detection & Topological Progression
- Dimension 4: Epistemic Ambiguity Resolution & User Clarification Protocol
- Dimension 8: Subgoal Execution Authority (ProgressGraph as sole source of truth)
- Dimension 9: Task-Scoped Working Memory & Credential Isolation (SecureSecretStore)
"""

import pytest
from datetime import datetime
from orbit.runtime.cognitive.models import (
    ProgressGraph,
    ProgressNode,
    ProgressSnapshot,
    SubgoalStatus,
    SubObjective,
)
from orbit.runtime.world_model.model import AgentWorldModel
from orbit.runtime.memory.task_memory import (
    MemoryFact,
    SecureSecretStore,
    TaskScopedMemory,
)
from orbit.runtime.cognitive.clarification import (
    ClarificationManager,
    ClarificationRequest,
    ClarificationResponse,
)
from orbit.runtime.task_understanding.models import (
    RawTaskRequest,
    StructuredTaskIntent,
    TargetReference,
    TaskConstraints,
    TaskGoal,
    TaskUnderstandingResult,
    TaskUnderstandingStatus,
)


# ============================================================================
# Dimension 1, 2, 8: Subgoal DAG & ProgressGraph Authority
# ============================================================================

def test_progress_graph_initialization_and_acyclicity():
    """Requirement: ProgressGraph builds topologically valid DAG from SubObjectives."""
    sub1 = SubObjective(sub_id="sub_1", title="Open Paint", dependencies=[])
    sub2 = SubObjective(sub_id="sub_2", title="Draw House", dependencies=["sub_1"])
    sub3 = SubObjective(sub_id="sub_3", title="Save File", dependencies=["sub_2"])

    graph = ProgressGraph([sub1, sub2, sub3])

    # Initial states
    assert graph.get_node("sub_1").status == SubgoalStatus.READY
    assert graph.get_node("sub_2").status == SubgoalStatus.PENDING
    assert graph.get_node("sub_3").status == SubgoalStatus.PENDING

    ready = graph.get_ready_subgoals()
    assert len(ready) == 1
    assert ready[0].sub_id == "sub_1"

    topo = graph.topological_sort()
    assert topo == ["sub_1", "sub_2", "sub_3"]


def test_progress_graph_rejects_cycles():
    """Requirement: Dependency cycles are immediately detected and rejected."""
    sub1 = SubObjective(sub_id="sub_1", title="Task A", dependencies=["sub_2"])
    sub2 = SubObjective(sub_id="sub_2", title="Task B", dependencies=["sub_1"])

    with pytest.raises(ValueError, match="cycle detected"):
        ProgressGraph([sub1, sub2])


def test_progress_graph_rejects_missing_dependency():
    """Requirement: Subgoal specifying unknown dependency raises ValueError."""
    sub1 = SubObjective(sub_id="sub_1", title="Task A", dependencies=["non_existent_sub"])

    with pytest.raises(ValueError, match="non-existent dependency"):
        ProgressGraph([sub1])


def test_progress_graph_lifecycle_execution_flow():
    """Requirement: Authoritative lifecycle transitions through ProgressGraph."""
    sub1 = SubObjective(sub_id="sub_1", title="Step 1", dependencies=[])
    sub2a = SubObjective(sub_id="sub_2a", title="Step 2A", dependencies=["sub_1"])
    sub2b = SubObjective(sub_id="sub_2b", title="Step 2B", dependencies=["sub_1"])
    sub3 = SubObjective(sub_id="sub_3", title="Step 3", dependencies=["sub_2a", "sub_2b"])

    graph = ProgressGraph([sub1, sub2a, sub2b, sub3])

    # 1. Start sub_1
    graph.start_subgoal("sub_1")
    assert graph.get_node("sub_1").status == SubgoalStatus.IN_PROGRESS
    assert graph.active_subgoal_id == "sub_1"

    # Cannot start a pending node
    with pytest.raises(ValueError, match="expected READY"):
        graph.start_subgoal("sub_2a")

    # 2. Complete sub_1 -> sub_2a and sub_2b should become READY
    graph.complete_subgoal("sub_1")
    assert graph.get_node("sub_1").status == SubgoalStatus.COMPLETED
    assert graph.get_node("sub_2a").status == SubgoalStatus.READY
    assert graph.get_node("sub_2b").status == SubgoalStatus.READY
    assert graph.get_node("sub_3").status == SubgoalStatus.PENDING

    # 3. Start and complete sub_2a -> sub_3 still PENDING (waiting for sub_2b)
    graph.start_subgoal("sub_2a")
    graph.complete_subgoal("sub_2a")
    assert graph.get_node("sub_3").status == SubgoalStatus.PENDING

    # 4. Start and complete sub_2b -> sub_3 becomes READY
    graph.start_subgoal("sub_2b")
    graph.complete_subgoal("sub_2b")
    assert graph.get_node("sub_3").status == SubgoalStatus.READY

    # 5. Execute sub_3 to completion
    graph.start_subgoal("sub_3")
    graph.complete_subgoal("sub_3")

    snap = graph.get_snapshot()
    assert snap.is_fully_completed is True
    assert snap.is_failed is False
    assert len(snap.completed_subgoals) == 4


def test_progress_graph_failure_and_downstream_blocking():
    """Requirement: Unambiguous failure cascade: failing a subgoal blocks all dependents."""
    sub1 = SubObjective(sub_id="sub_1", title="Step 1", dependencies=[])
    sub2 = SubObjective(sub_id="sub_2", title="Step 2", dependencies=["sub_1"])
    sub3 = SubObjective(sub_id="sub_3", title="Step 3", dependencies=["sub_2"])

    graph = ProgressGraph([sub1, sub2, sub3])
    graph.start_subgoal("sub_1")

    # Fail sub_1 without retry
    retrying = graph.fail_subgoal("sub_1", reason="Window crashed", allow_retry=False)
    assert retrying is False

    node1 = graph.get_node("sub_1")
    assert node1.status == SubgoalStatus.FAILED
    assert node1.failure_reason == "Window crashed"

    # Dependents cascaded to BLOCKED
    assert graph.get_node("sub_2").status == SubgoalStatus.BLOCKED
    assert "Ancestor dependency 'sub_1' failed" in graph.get_node("sub_2").failure_reason
    assert graph.get_node("sub_3").status == SubgoalStatus.BLOCKED

    snap = graph.get_snapshot()
    assert snap.is_failed is True
    assert snap.is_fully_completed is False


def test_progress_graph_retry_policy():
    """Requirement: Retrying a failed subgoal resets it to READY until max_retries reached."""
    sub = SubObjective(sub_id="sub_retry", title="Flaky action", dependencies=[])
    graph = ProgressGraph([sub])

    graph.start_subgoal("sub_retry")
    # First failure -> allowed retry
    retrying = graph.fail_subgoal("sub_retry", reason="Network glitch", allow_retry=True)
    assert retrying is True
    assert graph.get_node("sub_retry").status == SubgoalStatus.READY
    assert graph.get_node("sub_retry").retry_count == 1

    # Second failure -> allowed retry
    graph.start_subgoal("sub_retry")
    retrying = graph.fail_subgoal("sub_retry", reason="Network glitch 2", allow_retry=True)
    assert retrying is True
    assert graph.get_node("sub_retry").retry_count == 2

    # Third failure -> max retries exceeded -> FAILED
    graph.start_subgoal("sub_retry")
    retrying = graph.fail_subgoal("sub_retry", reason="Network persistent failure", allow_retry=True)
    assert retrying is False
    assert graph.get_node("sub_retry").status == SubgoalStatus.FAILED


def test_world_model_progress_projection_invariant():
    """Requirement: WorldModel references ProgressSnapshot as projection only."""
    sub1 = SubObjective(sub_id="s1", title="Step 1", dependencies=[])
    graph = ProgressGraph([sub1])
    graph.start_subgoal("s1")
    graph.complete_subgoal("s1")

    snapshot = graph.get_snapshot()
    wm = AgentWorldModel()
    wm.update_progress_snapshot(snapshot)

    assert wm.progress_snapshot is not None
    assert wm.progress_snapshot.is_fully_completed is True
    assert "s1" in wm.progress_snapshot.completed_subgoals


# ============================================================================
# Dimension 9: Task-Scoped Memory & Credential Isolation
# ============================================================================

def test_task_scoped_memory_variables_and_facts():
    """Requirement: Ephemeral variable storage and empirical facts scoped to task."""
    mem = TaskScopedMemory(task_id="task_test_01")
    mem.set_variable("counter", 42)
    mem.set_variable("target_filename", "budget.xlsx")

    assert mem.get_variable("counter") == 42
    assert mem.get_variable("target_filename") == "budget.xlsx"
    assert mem.has_variable("counter") is True
    assert mem.has_variable("non_existent") is False

    mem.store_fact("paint_window", "Paint window is open at (100, 100)", category="ui")
    fact = mem.get_fact("paint_window")
    assert fact is not None
    assert fact.category == "ui"
    assert "Paint window is open" in fact.statement


def test_task_scoped_memory_rejects_raw_credentials():
    """Requirement: Credentials must never be stored in plain task variables."""
    mem = TaskScopedMemory(task_id="task_test_sec")

    with pytest.raises(ValueError, match="cannot be stored in TaskScopedMemory"):
        mem.set_variable("admin_password", "supersecret123")

    with pytest.raises(ValueError, match="cannot be stored in TaskScopedMemory"):
        mem.set_variable("user_api_key", "sk-1234567890")


def test_secure_secret_store_and_redaction():
    """Requirement: SecureSecretStore isolates secrets and masks them in telemetry."""
    mem = TaskScopedMemory(task_id="task_test_sec_store")
    handle = mem.secret_store.store_secret("api_token", "super_secret_bearer_token_xyz")

    assert handle.startswith("sec_tok_")
    assert mem.secret_store.has_secret("api_token") is True
    assert mem.secret_store.has_secret(handle) is True

    # Resolved safely in-memory
    assert mem.secret_store.resolve_secret(handle) == "super_secret_bearer_token_xyz"
    assert mem.secret_store.resolve_secret("api_token") == "super_secret_bearer_token_xyz"

    # Log redaction test
    log_line = f"Connecting with header: Bearer super_secret_bearer_token_xyz to server"
    masked_line = mem.secret_store.mask_text(log_line)
    assert "super_secret_bearer_token_xyz" not in masked_line
    assert "***REDACTED***" in masked_line


def test_task_scoped_memory_wipe_zeroization():
    """Requirement: Wipe clears all variables, facts, and secret store, blocking subsequent access."""
    mem = TaskScopedMemory(task_id="task_test_wipe")
    mem.set_variable("temp_var", "temp_value")
    mem.secret_store.store_secret("pwd", "secret_pass_123")
    mem.store_fact("f1", "Fact 1")

    mem.wipe()
    assert mem.is_wiped is True
    assert mem.secret_store.resolve_secret("pwd") is None

    # Further operations raise RuntimeError
    with pytest.raises(RuntimeError, match="has already been wiped"):
        mem.set_variable("new_var", "value")

    with pytest.raises(RuntimeError, match="has already been wiped"):
        mem.get_variable("temp_var")


# ============================================================================
# Dimension 4: Epistemic Ambiguity Resolution & User Clarification Protocol
# ============================================================================

def test_clarification_manager_detects_ambiguity():
    """Requirement: Ambiguous or unsupported tasks trigger clarification without physical execution."""
    mgr = ClarificationManager()

    ambig_intent = StructuredTaskIntent(
        intent_id="i1",
        sequence_index=0,
        goal=TaskGoal.CLICK_TARGET,
        is_ambiguous=True,
        unresolved_reason="Target control has no application context",
    )
    result_ambig = TaskUnderstandingResult(
        request_id="req_1",
        raw_request=RawTaskRequest(raw_text="Click the button"),
        status=TaskUnderstandingStatus.AMBIGUOUS,
        intents=[ambig_intent],
        unresolved_constraints=["Unspecified target control application"],
    )

    assert mgr.is_clarification_needed(result_ambig) is True

    req = mgr.generate_clarification_request("task_ambig", "Click the button", result_ambig)
    assert req.task_id == "task_ambig"
    assert len(req.clarification_questions) > 0
    assert any("Unspecified target control" in q for q in req.clarification_questions)

    # Applying clarification resolves the prompt
    revised = mgr.apply_clarification(
        "Click the button",
        ClarificationResponse(request_id=req.request_id, user_response="The Submit button in Chrome"),
    )
    assert "Click the button (Clarification: The Submit button in Chrome)" == revised


def test_clarification_manager_allows_understood_tasks():
    """Requirement: Fully understood tasks do NOT trigger clarification."""
    mgr = ClarificationManager()

    clean_intent = StructuredTaskIntent(
        intent_id="i2",
        sequence_index=0,
        goal=TaskGoal.OPEN_APPLICATION,
        constraints=TaskConstraints(application_name="notepad"),
        is_ambiguous=False,
    )
    result_clean = TaskUnderstandingResult(
        request_id="req_2",
        raw_request=RawTaskRequest(raw_text="Open Notepad"),
        status=TaskUnderstandingStatus.UNDERSTOOD,
        intents=[clean_intent],
    )

    assert mgr.is_clarification_needed(result_clean) is False
