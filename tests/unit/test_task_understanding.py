"""Unit test suite for ORBIT Task Understanding Subsystem (M1.8 Step 1)."""

import pytest
from orbit.runtime.task_understanding import (
    DeterministicTaskParser,
    RawTaskRequest,
    TaskGoal,
    TaskNormalizer,
    TaskUnderstandingEngine,
    TaskUnderstandingStatus,
    TaskUnderstandingValidator,
)


@pytest.fixture
def engine():
    return TaskUnderstandingEngine()


# ============================================================================
# 1. Basic Single-Intent Understanding Tests
# ============================================================================

def test_understand_open_notepad(engine):
    """Test standard single goal 'Open Notepad'."""
    res = engine.understand("Open Notepad")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 1
    intent = res.intents[0]
    assert intent.goal == TaskGoal.OPEN_APPLICATION
    assert intent.target is not None
    assert intent.target.identifier == "Notepad"
    assert intent.target.semantic_type == "application"
    assert not intent.is_negated
    assert not intent.is_ambiguous
    assert any("Notepad" in ev for ev in intent.evidence)


def test_understand_open_calculator(engine):
    """Test single goal 'Launch Calculator'."""
    res = engine.understand("Launch Calculator")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 1
    intent = res.intents[0]
    assert intent.goal == TaskGoal.OPEN_APPLICATION
    assert intent.target.identifier == "Calculator"
    assert not intent.is_negated


def test_understand_click_save(engine):
    """Test single goal 'Click Save'."""
    res = engine.understand("Click Save")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 1
    intent = res.intents[0]
    assert intent.goal == TaskGoal.CLICK_TARGET
    assert intent.target.identifier == "Save"
    assert intent.target.semantic_type == "ui_control"
    assert not intent.is_negated


def test_understand_save_document(engine):
    """Test single goal 'Save document'."""
    res = engine.understand("Save document")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 1
    intent = res.intents[0]
    assert intent.goal == TaskGoal.SAVE_DOCUMENT
    assert not intent.is_negated


def test_understand_search_query(engine):
    """Test search intent 'Search for weather'."""
    res = engine.understand("Search for weather")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 1
    intent = res.intents[0]
    assert intent.goal == TaskGoal.SEARCH
    assert intent.constraints.content == "weather"
    assert not intent.is_negated


def test_understand_copy_and_paste(engine):
    """Test copy and paste intents."""
    res_copy = engine.understand("Copy the selected text")
    assert res_copy.status == TaskUnderstandingStatus.UNDERSTOOD
    assert res_copy.intents[0].goal == TaskGoal.COPY_CONTENT

    res_paste = engine.understand("Paste the copied text")
    assert res_paste.status == TaskUnderstandingStatus.UNDERSTOOD
    assert res_paste.intents[0].goal == TaskGoal.PASTE_CONTENT


# ============================================================================
# 2. Composite Multi-Clause Requests
# ============================================================================

def test_composite_open_notepad_and_type_hello_world(engine):
    """Test composite request 'Open Notepad and type Hello World'."""
    res = engine.understand("Open Notepad and type Hello World")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 2

    # Intent 1: OPEN_APPLICATION
    intent_1 = res.intents[0]
    assert intent_1.sequence_index == 0
    assert intent_1.goal == TaskGoal.OPEN_APPLICATION
    assert intent_1.target.identifier == "Notepad"

    # Intent 2: WRITE_TEXT with inherited application context
    intent_2 = res.intents[1]
    assert intent_2.sequence_index == 1
    assert intent_2.goal == TaskGoal.WRITE_TEXT
    assert intent_2.constraints.content == "Hello World"
    assert intent_2.constraints.application_name == "Notepad"
    assert not intent_2.is_negated


def test_composite_open_calculator_and_calculate_something(engine):
    """Test composite with partially supported calculation semantics."""
    res = engine.understand("Open Calculator and calculate something")
    # Intent 1: Open Calculator (understood), Intent 2: calculate something (unknown/unsupported)
    assert res.status == TaskUnderstandingStatus.PARTIALLY_UNDERSTOOD
    assert len(res.intents) == 2
    assert res.intents[0].goal == TaskGoal.OPEN_APPLICATION
    assert res.intents[1].goal in {TaskGoal.UNKNOWN, TaskGoal.UNSUPPORTED}


def test_composite_three_clauses(engine):
    """Test three-clause composite: 'Open Notepad, type Hello, and save document'."""
    res = engine.understand("Open Notepad and type Hello and save document")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 3
    assert res.intents[0].goal == TaskGoal.OPEN_APPLICATION
    assert res.intents[1].goal == TaskGoal.WRITE_TEXT
    assert res.intents[2].goal == TaskGoal.SAVE_DOCUMENT


# ============================================================================
# 3. Quoted and Literal Content Preservation
# ============================================================================

def test_quoted_content_exact_preservation(engine):
    """Verify double-quoted text payload preserves casing and special punctuation exactly."""
    prompt = 'Type "Hello, World! Here is a 100% test @ #1."'
    res = engine.understand(prompt)
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 1
    intent = res.intents[0]
    assert intent.goal == TaskGoal.WRITE_TEXT
    assert intent.constraints.content == "Hello, World! Here is a 100% test @ #1."


def test_unicode_content_preservation(engine):
    """Verify Unicode characters and accents are preserved verbatim."""
    prompt = 'Write the following text: "Café & Naïve Résumé: €500 / ¥1000"'
    res = engine.understand(prompt)
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert res.intents[0].constraints.content == "Café & Naïve Résumé: €500 / ¥1000"


# ============================================================================
# 4. Ambiguity Detection
# ============================================================================

def test_ambiguity_open_it(engine):
    """Test ambiguous pronoun 'Open it'."""
    res = engine.understand("Open it")
    assert res.status == TaskUnderstandingStatus.AMBIGUOUS
    assert len(res.intents) == 1
    assert res.intents[0].is_ambiguous
    assert res.intents[0].target.is_ambiguous
    assert "it" in res.intents[0].target.unresolved_reason.lower()
    assert len(res.unresolved_constraints) > 0


def test_ambiguity_click_the_button(engine):
    """Test ambiguous control 'Click the button' without name."""
    res = engine.understand("Click the button")
    assert res.status == TaskUnderstandingStatus.AMBIGUOUS
    assert len(res.intents) == 1
    assert res.intents[0].is_ambiguous
    assert res.intents[0].target.is_ambiguous
    assert len(res.unresolved_constraints) > 0


def test_ambiguity_save_the_file_somewhere(engine):
    """Test ambiguous destination 'Save the file somewhere'."""
    res = engine.understand("Save the file somewhere")
    assert res.status == TaskUnderstandingStatus.AMBIGUOUS
    assert len(res.intents) == 1
    assert res.intents[0].is_ambiguous


# ============================================================================
# 5. Negation and Safety Semantics
# ============================================================================

def test_negation_do_not_save(engine):
    """Test explicit negation 'Do not save the document'."""
    res = engine.understand("Do not save the document")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 1
    intent = res.intents[0]
    assert intent.goal == TaskGoal.SAVE_DOCUMENT
    assert intent.is_negated is True
    assert intent.constraints.is_negated is True
    assert any("negation" in ev for ev in intent.evidence)


def test_negation_open_notepad_but_do_not_type(engine):
    """Test composite with negative clause 'Open Notepad but don't type anything'."""
    res = engine.understand("Open Notepad but don't type anything")
    assert res.status == TaskUnderstandingStatus.UNDERSTOOD
    assert len(res.intents) == 2

    # First intent is positive OPEN_APPLICATION
    assert res.intents[0].goal == TaskGoal.OPEN_APPLICATION
    assert not res.intents[0].is_negated

    # Second intent is negated WRITE_TEXT
    assert res.intents[1].goal == TaskGoal.WRITE_TEXT
    assert res.intents[1].is_negated is True
    assert res.intents[1].constraints.is_negated is True


# ============================================================================
# 6. Unknown / Unsupported Task Handling
# ============================================================================

def test_unsupported_quantum_teleportation(engine):
    """Test completely unsupported prompt fails honestly."""
    res = engine.understand("Perform quantum teleportation")
    assert res.status in {TaskUnderstandingStatus.UNSUPPORTED, TaskUnderstandingStatus.FAILED}
    assert res.intents[0].goal in {TaskGoal.UNKNOWN, TaskGoal.UNSUPPORTED}
    assert len(res.unresolved_constraints) > 0


# ============================================================================
# 7. Empty and Invalid Input
# ============================================================================

def test_empty_input(engine):
    """Test empty string returns INVALID status."""
    res = engine.understand("")
    assert res.status == TaskUnderstandingStatus.INVALID
    assert len(res.intents) == 0


def test_whitespace_only_input(engine):
    """Test whitespace-only string returns INVALID status."""
    res = engine.understand("   \t \n  ")
    assert res.status == TaskUnderstandingStatus.INVALID
    assert len(res.intents) == 0


# ============================================================================
# 8. Determinism
# ============================================================================

def test_determinism_identical_results(engine):
    """Verify that repeated parsing of identical prompt produces equivalent structured output."""
    prompt = "Open Notepad and type 'Deterministic Test 123' and click Save"
    res1 = engine.understand(prompt)
    res2 = engine.understand(prompt)

    assert res1.status == res2.status
    assert len(res1.intents) == len(res2.intents)

    for i1, i2 in zip(res1.intents, res2.intents):
        assert i1.sequence_index == i2.sequence_index
        assert i1.goal == i2.goal
        assert i1.is_negated == i2.is_negated
        assert i1.is_ambiguous == i2.is_ambiguous
        assert i1.constraints.content == i2.constraints.content
        assert i1.constraints.application_name == i2.constraints.application_name
        if i1.target and i2.target:
            assert i1.target.semantic_type == i2.target.semantic_type
            assert i1.target.identifier == i2.target.identifier


# ============================================================================
# 9. Invariant: Zero OS Interaction & Zero Coordinates
# ============================================================================

def test_zero_coordinates_in_understanding(engine):
    """Verify that no screen coordinates (x, y) are generated during understanding."""
    prompts = [
        "Open Notepad",
        "Click Save",
        "Type Hello World",
        "Save document",
        "Search for cat pictures",
    ]
    for p in prompts:
        res = engine.understand(p)
        for intent in res.intents:
            # Check target reference has no coordinate fields
            if intent.target:
                assert not hasattr(intent.target, "x")
                assert not hasattr(intent.target, "y")
                assert not hasattr(intent.target, "left")
                assert not hasattr(intent.target, "top")
