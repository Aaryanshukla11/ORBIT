"""Unit tests for MultimodalContextBuilder (Phase 3A)."""

import base64
import io
from PIL import Image
import pytest
from unittest.mock import MagicMock

from orbit.adapters.observation.snapshot import BoundingBox, ObservedElement
from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType, SemanticTarget
from orbit.runtime.cognitive.context_compactor import ContextCompactor
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.multimodal_context_builder import (
    ASTRA6_SYSTEM_PROMPT,
    MultimodalContextBuilder,
    MultimodalContextPayload,
)
from orbit.runtime.cognitive.trajectory_memory import TrajectoryMemory


def test_multimodal_context_builder_basic_payload():
    """Verify context builder produces structured text prompt and metadata."""
    builder = MultimodalContextBuilder()

    obj = StructuredObjective(
        raw_prompt="Create a new document in Notepad and write 'Hello World'",
        user_goal="Create a new document in Notepad and write 'Hello World'",
        end_condition="notepad_contains_text",
        subtasks=["Open Notepad", "Type Hello World", "Save document"],
    )

    obs = CurrentStateObservation(
        observation_id="obs_notepad_1",
        active_window_hwnd=1001,
        active_window_title="Untitled - Notepad",
        active_window_class="Notepad",
        target_app_exists=True,
    )

    payload = builder.build_context(
        objective=obj,
        observation=obs,
        step_index=1,
    )

    assert isinstance(payload, MultimodalContextPayload)
    assert payload.system_prompt == ASTRA6_SYSTEM_PROMPT
    assert "Create a new document in Notepad" in payload.user_text_prompt
    assert "- [x] Open Notepad" in payload.user_text_prompt
    assert "- [ ] Type Hello World" in payload.user_text_prompt
    assert "Untitled - Notepad" in payload.user_text_prompt
    assert payload.build_duration_ms >= 0.0


def test_multimodal_context_builder_attaches_som_overlay():
    """Verify context builder processes screenshot and embeds Set-of-Marks base64."""
    builder = MultimodalContextBuilder()
    img = Image.new("RGB", (1280, 720), color="blue")

    elem = MagicMock(spec=ObservedElement)
    elem.bounding_box = BoundingBox(left=50, top=50, width=120, height=40)
    elem.name = "File"
    elem.control_type = "MenuItem"

    obs = CurrentStateObservation(
        observation_id="obs_som_1",
        active_window_hwnd=2002,
        active_window_title="App Window",
        raw_evidence={"interactive_elements": [elem]},
    )

    payload = builder.build_context(
        objective="Click File menu",
        observation=obs,
        raw_image=img,
    )

    assert payload.som_image_base64 is not None
    assert len(payload.som_image_base64) > 100
    assert payload.som_result is not None
    assert len(payload.som_result.marks) >= 1
    assert "MenuItem" in payload.user_text_prompt
    assert "File" in payload.user_text_prompt


def test_multimodal_context_builder_converts_to_openai_and_anthropic():
    """Verify standard schema conversion for OpenAI and Anthropic APIs."""
    builder = MultimodalContextBuilder()
    img = Image.new("RGB", (400, 300), color="red")

    obs = CurrentStateObservation(
        observation_id="obs_test_conv",
        active_window_hwnd=111,
        active_window_title="Test Window",
    )

    payload = builder.build_context(
        objective="Test Goal",
        observation=obs,
        raw_image=img,
    )

    # 1. OpenAI format
    openai_msgs = payload.to_openai_messages()
    assert len(openai_msgs) == 2
    assert openai_msgs[0]["role"] == "system"
    assert openai_msgs[1]["role"] == "user"
    user_parts = openai_msgs[1]["content"]
    assert any(part.get("type") == "image_url" for part in user_parts)
    assert any(part.get("type") == "text" for part in user_parts)

    # 2. Anthropic format
    sys_prompt, anthropic_msgs = payload.to_anthropic_messages()
    assert sys_prompt == ASTRA6_SYSTEM_PROMPT
    assert len(anthropic_msgs) == 1
    anthropic_parts = anthropic_msgs[0]["content"]
    assert any(part.get("type") == "image" for part in anthropic_parts)
    assert any(part.get("type") == "text" for part in anthropic_parts)


def test_multimodal_context_builder_compacts_history_and_detects_loops():
    """Verify compacted history and loop warnings are embedded in the prompt."""
    builder = MultimodalContextBuilder()
    traj = TrajectoryMemory()

    act = AbstractAction(action_type=AbstractActionType.CLICK, target=SemanticTarget(name="Retry Button"))
    step_res = CognitiveStepResult(
        step_index=0,
        observation_before=CurrentStateObservation(observation_id="obs_0"),
        decision=CognitiveDecision(
            decision_summary="Clicked button",
            is_goal_satisfied=False,
            decision_confidence=0.9,
            next_action=act,
        ),
        action_dispatched=act,
        observation_after=CurrentStateObservation(observation_id="obs_1"),
    )

    # Record loop A -> A -> A
    traj.record_step(step_res, active_window_title="App Window")
    traj.record_step(step_res, active_window_title="App Window")
    traj.record_step(step_res, active_window_title="App Window")

    obs = CurrentStateObservation(observation_id="obs_2", active_window_hwnd=500)

    payload = builder.build_context(
        objective="Looping Objective",
        observation=obs,
        step_history=[step_res],
        step_index=3,
        trajectory_memory=traj,
        failure_feedback="Button was unresponsive",
    )

    assert "TRAJECTORY WARNING" in payload.user_text_prompt
    assert "LAST ACTION FAILURE DIAGNOSTICS" in payload.user_text_prompt
    assert "Button was unresponsive" in payload.user_text_prompt


def test_multimodal_context_builder_image_downsampling():
    """Verify large 4K images are safely downscaled below max dimension."""
    builder = MultimodalContextBuilder(max_image_dimension=1000)
    img_4k = Image.new("RGB", (3840, 2160), color="green")

    obs = CurrentStateObservation(observation_id="obs_4k", active_window_hwnd=999)
    payload = builder.build_context(
        objective="4K Screen task",
        observation=obs,
        raw_image=img_4k,
    )

    assert payload.som_image_base64 is not None
    # Decode image to verify downscaling
    raw_bytes = base64.b64decode(payload.som_image_base64)
    decoded = Image.open(io.BytesIO(raw_bytes))
    assert max(decoded.size) <= 1000
