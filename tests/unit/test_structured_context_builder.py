"""Unit tests for StructuredAgentContext and StructuredContextBuilder."""

import pytest
from orbit.runtime.cognitive.context_builder import (
    StructuredAgentContext,
    StructuredContextBuilder,
)
from orbit.runtime.cognitive.models import SubObjective
from orbit.runtime.world_model.model import AgentWorldModel, ControlSummary
from orbit.runtime.world_model.updater import WorldModelUpdater


def test_build_structured_context():
    wm = AgentWorldModel(
        active_process_name="notepad.exe",
        active_window_title="Untitled - Notepad",
        current_url=None,
    )
    wm = WorldModelUpdater.record_fact(wm, "test_key", "test_val")

    sub = SubObjective(
        title="Type text into editor",
        description="Focus editor and enter text",
        constraints=["do not close window"],
    )

    ctx = StructuredContextBuilder.build(
        sub_objective=sub,
        world_model=wm,
        provider_availability_map={"SPREADSHEET_WRITE": "csv_fallback_provider"},
    )

    assert isinstance(ctx, StructuredAgentContext)
    assert ctx.active_process_name == "notepad.exe"
    assert ctx.active_window_title == "Untitled - Notepad"
    assert ctx.current_subgoal_title == "Type text into editor"
    assert "do not close window" in ctx.subgoal_constraints
    assert ctx.known_facts.get("test_key") == "test_val"
    assert ctx.available_providers.get("SPREADSHEET_WRITE") == "csv_fallback_provider"


def test_context_boundedness():
    wm = AgentWorldModel()
    # Add 30 controls
    wm = wm.model_copy(
        update={
            "visible_controls": [
                ControlSummary(control_type="Button", name=f"Btn{i}") for i in range(30)
            ]
        }
    )

    sub = SubObjective(title="Test Subgoal")
    ctx = StructuredContextBuilder.build(sub_objective=sub, world_model=wm)

    # Should be bounded to MAX_VISIBLE_CONTROLS (20)
    assert len(ctx.visible_controls) == StructuredContextBuilder.MAX_VISIBLE_CONTROLS
