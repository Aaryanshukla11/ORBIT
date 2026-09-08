"""Comprehensive Unit Tests for Step 4: Vision/LLM Decision Brain & Production Model Routing.

Tests:
1. Model capability profiles & vision capability registry
2. Vision routing & screenshot attachment behavior
3. Strict structured output parsing
4. Coordinate security isolation (rejection of x/y/bbox)
5. Hybrid Local -> Cloud model escalation
6. AgentDecisionTrace audit telemetry
7. End-to-end AgentExecutionLoop integration with AgentDecisionEngine
"""

import base64
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from orbit.runtime.agent.contracts import (
    AbstractAction,
    AbstractActionType,
    ActionValidationFailureCode,
    AgentActionValidator,
    SemanticTarget,
)
from orbit.runtime.cognitive.agent_decision import (
    AgentDecisionEngine,
    AgentDecisionTrace,
)
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop
from orbit.runtime.cognitive.context_builder import AgentReasoningContextBuilder
from orbit.runtime.cognitive.models import (
    CognitiveDecision,
    CognitiveStepResult,
    CurrentStateObservation,
    StructuredObjective,
)
from orbit.runtime.cognitive.output_parser import (
    CoordinateSecurityViolation,
    StructuredDecisionParser,
    StructuredOutputParserError,
)
from orbit.runtime.model_runtime.base import BaseModelRuntime
from orbit.runtime.model_runtime.contracts import (
    ModelRuntimeKind,
    ModelRuntimeStatus,
    RuntimeInitializationResult,
)
from orbit.runtime.model_runtime.router import (
    ModelRouter,
    ModelRoutingTier,
    PrivacyPolicy,
    RoutingPolicy,
)
from orbit.runtime.models.capabilities import (
    ModelCapabilityProfile,
    get_model_capability_profile,
    infer_capabilities,
)
from orbit.runtime.models.models import (
    ModelCapability,
    ModelChatMessage,
    ModelChatRequest,
    ModelDescriptor,
    ModelGenerateResponse,
    ModelProviderKind,
    ModelSourceType,
    ModelStatus,
)
from orbit.models.common import BoundingBox
from orbit.runtime.perception.models import (
    DesktopObservation,
    OCRToken,
    PerceivedElement,
    ScreenshotObservation,
    UIElementObservation,
    WindowObservation,
)


class MockTestRuntime(BaseModelRuntime):
    """Configurable mock runtime for testing decision engine routing."""

    def __init__(
        self,
        descriptor: ModelDescriptor,
        chat_response_content: str = "",
        latency_ms: float = 45.0,
    ) -> None:
        super().__init__(descriptor)
        self._status = ModelRuntimeStatus.READY
        self.chat_response_content = chat_response_content
        self.latency_ms = latency_ms
        self.chat_invocations: list[ModelChatRequest] = []

    @property
    def runtime_kind(self) -> ModelRuntimeKind:
        return (
            ModelRuntimeKind.LOCAL
            if self._descriptor.source_type == ModelSourceType.LOCAL_RUNTIME
            else ModelRuntimeKind.REMOTE
        )

    async def initialize(self, timeout_seconds: float = 30.0, preload_weights: bool = True):
        self._status = ModelRuntimeStatus.READY
        return RuntimeInitializationResult(is_success=True, model_id=self.model_id, status=self._status)

    async def health_check(self):
        from orbit.runtime.model_runtime.contracts import ModelRuntimeHealth
        return ModelRuntimeHealth(model_id=self.model_id, status=self._status, is_healthy=True, latency_ms=self.latency_ms)

    async def generate(self, request):
        return ModelGenerateResponse(
            model_id=self.model_id,
            content=self.chat_response_content,
            total_duration_ms=self.latency_ms,
        )

    async def chat(self, request: ModelChatRequest) -> ModelGenerateResponse:
        self.chat_invocations.append(request)
        return ModelGenerateResponse(
            model_id=self.model_id,
            content=self.chat_response_content,
            total_duration_ms=self.latency_ms,
        )

    async def shutdown(self):
        self._status = ModelRuntimeStatus.STOPPED


def create_sample_desktop_obs() -> DesktopObservation:
    """Create sample observation for unit tests."""
    bounds = BoundingBox(left=0, top=0, width=1920, height=1080)
    return DesktopObservation(
        foreground_window=WindowObservation(
            hwnd=1001,
            title="Canva - Chrome",
            window_class="Chrome_WidgetWin_1",
            process_name="chrome.exe",
            window_bounds=bounds,
            client_bounds=bounds,
        ),
        visible_windows=[
            WindowObservation(
                hwnd=1001,
                title="Canva - Chrome",
                window_class="Chrome_WidgetWin_1",
                process_name="chrome.exe",
                window_bounds=bounds,
                client_bounds=bounds,
            ),
            WindowObservation(
                hwnd=1002,
                title="File Explorer",
                window_class="CabinetWClass",
                process_name="explorer.exe",
                window_bounds=bounds,
                client_bounds=bounds,
            ),
        ],
        screenshot_reference=ScreenshotObservation(
            width=1920,
            height=1080,
            raw_bytes=b"fake_png_bytes_12345",
        ),
        uia_elements=[
            UIElementObservation(
                name="Create a design",
                control_type="Button",
                bounding_box=BoundingBox(left=50, top=50, width=120, height=40),
            ),
            UIElementObservation(
                name="Search",
                control_type="Edit",
                bounding_box=BoundingBox(left=200, top=50, width=300, height=40),
            ),
        ],
        ocr_tokens=[
            OCRToken(
                text="Create a design",
                confidence=0.99,
                bounding_box=BoundingBox(left=50, top=50, width=120, height=40),
            ),
            OCRToken(
                text="Canva",
                confidence=0.98,
                bounding_box=BoundingBox(left=10, top=10, width=80, height=30),
            ),
        ],
        perceived_elements=[
            PerceivedElement(
                name="Create a design",
                role="button",
                confidence=0.99,
            ),
        ],
        desktop_summary="Chrome is open on Canva homepage.",
    )


# ==============================================================================
# 1. Model Capability Profile & Registry Tests
# ==============================================================================

def test_model_capability_profiles():
    profile_local_vision = get_model_capability_profile("ollama:llava:latest")
    assert profile_local_vision.supports_vision is True
    assert profile_local_vision.is_local is True

    profile_local_text = get_model_capability_profile("ollama:qwen2.5:latest")
    assert profile_local_text.supports_vision is False
    assert profile_local_text.is_local is True
    assert profile_local_text.supports_tools is True

    profile_cloud = get_model_capability_profile("cloud:gpt-4o")
    assert profile_cloud.supports_vision is True
    assert profile_cloud.is_local is False

    # Dynamic descriptor inference
    desc = ModelDescriptor(
        model_id="ollama:my-custom-vision-vl",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="my-custom-vision-vl",
        capabilities={ModelCapability.CHAT, ModelCapability.VISION},
    )
    custom_prof = ModelCapabilityProfile.from_descriptor(desc)
    assert custom_prof.supports_vision is True


# ==============================================================================
# 2. Vision Routing & Screenshot Attachment Tests
# ==============================================================================

def test_vision_routing_screenshot_attachment():
    obs = create_sample_desktop_obs()
    objective = StructuredObjective(
        raw_prompt="Open Canva and create a design",
        user_goal="Create a design in Canva",
        end_condition="design_editor_open",
        target_entities=["chrome", "canva"],
    )

    # 1. When model supports vision, screenshot image is attached
    profile_vision = get_model_capability_profile("cloud:gpt-4o")
    chat_req_vision, attached_vision = AgentReasoningContextBuilder.build_chat_request(
        objective=objective,
        observation=obs,
        model_profile=profile_vision,
    )
    assert attached_vision is True
    assert chat_req_vision.messages[1].images is not None
    assert len(chat_req_vision.messages[1].images) == 1
    assert "fake_png_bytes_12345" in base64.b64decode(chat_req_vision.messages[1].images[0]).decode("latin1")

    # 2. When model is text-only, screenshot is omitted cleanly
    profile_text = get_model_capability_profile("ollama:qwen2.5:latest")
    chat_req_text, attached_text = AgentReasoningContextBuilder.build_chat_request(
        objective=objective,
        observation=obs,
        model_profile=profile_text,
    )
    assert attached_text is False
    assert chat_req_text.messages[1].images is None
    # Text prompt still contains rich OCR and UIA elements
    assert "Create a design" in chat_req_text.messages[1].content


# ==============================================================================
# 3. Structured Decision Parsing & Action Protocol Tests
# ==============================================================================

def test_structured_decision_parsing_valid():
    valid_json = """
    ```json
    {
      "decision_summary": "Canva is open. The next step is to click 'Create a design'.",
      "goal_progress": "IN_PROGRESS",
      "confidence": 0.94,
      "evidence_used": ["OCR: Create a design", "UIA: Button 'Create a design'"],
      "expected_state_transition": "Design creation dropdown opens",
      "reason_summary": "Starting a new design canvas.",
      "next_action": {
        "action_type": "CLICK",
        "target": {
          "name": "Create a design",
          "role": "button",
          "context": "Canva header"
        },
        "parameters": {},
        "expected_effect": "Design creation dropdown opens"
      }
    }
    ```
    """
    decision = StructuredDecisionParser.parse_decision(valid_json, step_index=1, model_id="cloud:gpt-4o")
    assert not decision.is_goal_satisfied
    assert decision.decision_confidence == 0.94
    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.CLICK
    assert decision.next_action.target is not None
    assert decision.next_action.target.name == "Create a design"
    assert decision.next_action.target.role == "button"
    assert decision.next_action.expected_effect == "Design creation dropdown opens"


# ==============================================================================
# 4. Coordinate Security Isolation Invariant Tests
# ==============================================================================

def test_coordinate_security_violation_rejection():
    # LLM attempts to output physical screen coordinates
    malicious_json = """{
      "decision_summary": "Clicking button at fixed pixel coordinates",
      "goal_progress": "IN_PROGRESS",
      "confidence": 0.8,
      "evidence_used": ["Visual"],
      "next_action": {
        "action_type": "CLICK",
        "target": {
          "name": "Submit",
          "x": 450,
          "y": 620
        },
        "parameters": {
          "screen_x": 450,
          "screen_y": 620
        }
      }
    }"""

    with pytest.raises(CoordinateSecurityViolation):
        StructuredDecisionParser.parse_decision(malicious_json, step_index=0)


# ==============================================================================
# 5. Hybrid Local -> Cloud Escalation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_hybrid_local_to_cloud_escalation():
    # Setup local text model that returns low confidence
    local_desc = ModelDescriptor(
        model_id="ollama:qwen2.5:latest",
        provider=ModelProviderKind.OLLAMA,
        provider_model_name="qwen2.5:latest",
        source_type=ModelSourceType.LOCAL_RUNTIME,
        capabilities={ModelCapability.CHAT, ModelCapability.TEXT_GENERATION},
    )
    local_runtime = MockTestRuntime(
        descriptor=local_desc,
        chat_response_content=json.dumps({
            "decision_summary": "Uncertain about visual desktop state",
            "goal_progress": "IN_PROGRESS",
            "confidence": 0.40,  # Below threshold 0.60
            "next_action": {"action_type": "WAIT", "parameters": {"duration_ms": 500}},
        }),
    )

    # Setup cloud vision model with high confidence
    cloud_desc = ModelDescriptor(
        model_id="cloud:gpt-4o",
        provider=ModelProviderKind.CLOUD_OPENAI,
        provider_model_name="gpt-4o",
        source_type=ModelSourceType.CLOUD_PROVIDER,
        capabilities={ModelCapability.CHAT, ModelCapability.VISION},
    )
    cloud_runtime = MockTestRuntime(
        descriptor=cloud_desc,
        chat_response_content=json.dumps({
            "decision_summary": "Visual analysis confirms Create a design button is visible.",
            "goal_progress": "IN_PROGRESS",
            "confidence": 0.95,
            "next_action": {
              "action_type": "CLICK",
              "target": {"name": "Create a design", "role": "button"},
              "parameters": {},
            },
        }),
    )

    mock_session_mgr = MagicMock()
    mock_session_mgr.list_all_descriptors = AsyncMock(return_value=[local_desc, cloud_desc])
    mock_session_mgr.get_or_create_runtime = AsyncMock(
        side_effect=lambda mid: local_runtime if mid == "ollama:qwen2.5:latest" else cloud_runtime
    )
    mock_session_mgr.get_active_runtime.return_value = local_runtime

    router = ModelRouter(session_manager=mock_session_mgr)
    decision_engine = AgentDecisionEngine(
        router=router,
        confidence_threshold=0.60,
    )

    obs = create_sample_desktop_obs()
    objective = StructuredObjective(
        raw_prompt="Open Canva and create a design",
        user_goal="Create a design in Canva",
        end_condition="design_editor_open",
    )

    decision = await decision_engine.decide_next_step(
        objective=objective,
        observation=obs,
        step_history=[],
        step_index=0,
        routing_policy=RoutingPolicy(
            tier=ModelRoutingTier.PREFER_LOCAL,
            privacy=PrivacyPolicy(allow_cloud_transfer=True, strictly_local=False),
        ),
    )

    # Escalation occurred to cloud:gpt-4o because local confidence was 0.40 < 0.60
    assert decision.decision_confidence == 0.95
    assert decision.next_action is not None
    assert decision.next_action.action_type == AbstractActionType.CLICK
    assert decision.next_action.target.name == "Create a design"

    # Verify telemetry trace recorded escalation
    traces = decision_engine.get_recent_traces()
    assert len(traces) > 0
    assert traces[-1].escalated_to_cloud is True
    assert traces[-1].model_id == "cloud:gpt-4o"
    assert traces[-1].used_vision is True


# ==============================================================================
# 6. AgentDecisionTrace Telemetry Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_agent_decision_trace_telemetry():
    desc = ModelDescriptor(
        model_id="cloud:gemini-2.0-flash",
        provider=ModelProviderKind.CLOUD_GEMINI,
        provider_model_name="gemini-2.0-flash",
        source_type=ModelSourceType.CLOUD_PROVIDER,
        capabilities={ModelCapability.CHAT, ModelCapability.VISION},
    )
    runtime = MockTestRuntime(
        descriptor=desc,
        chat_response_content=json.dumps({
            "decision_summary": "Navigating to home view",
            "goal_progress": "IN_PROGRESS",
            "confidence": 0.88,
            "evidence_used": ["OCR: Canva"],
            "next_action": {
                "action_type": "CLICK",
                "target": {"name": "Home", "role": "link"},
            },
        }),
    )

    mock_session_mgr = MagicMock()
    mock_session_mgr.get_active_runtime.return_value = runtime
    mock_session_mgr.list_all_descriptors = AsyncMock(return_value=[desc])
    mock_session_mgr.get_or_create_runtime = AsyncMock(return_value=runtime)

    router = ModelRouter(session_manager=mock_session_mgr)
    decision_engine = AgentDecisionEngine(router=router)

    obs = create_sample_desktop_obs()
    objective = StructuredObjective(
        raw_prompt="Go to Canva Home",
        user_goal="Navigate to Canva Home",
        end_condition="home_view_active",
    )

    decision = await decision_engine.decide_next_step(objective, obs, step_index=2)
    assert decision.decision_confidence == 0.88

    traces = decision_engine.get_recent_traces()
    assert len(traces) == 1
    t = traces[0]
    assert t.model_id == "cloud:gemini-2.0-flash"
    assert t.action_type == "CLICK"
    assert t.target_name == "Home"
    assert t.used_vision is True
    assert t.used_ocr is True
    assert t.used_uia is True
    assert t.validation_result == "VALID"


# ==============================================================================
# 7. End-to-End AgentExecutionLoop Integration with Decision Brain
# ==============================================================================

@pytest.mark.asyncio
async def test_agent_execution_loop_invokes_decision_brain():
    desc = ModelDescriptor(
        model_id="cloud:gpt-4o",
        provider=ModelProviderKind.CLOUD_OPENAI,
        provider_model_name="gpt-4o",
        source_type=ModelSourceType.CLOUD_PROVIDER,
        capabilities={ModelCapability.CHAT, ModelCapability.VISION},
    )
    # Turn 1: Click "Create a design"
    # Turn 2: Goal Complete
    step_responses = [
        json.dumps({
            "decision_summary": "Canva homepage open. Clicking Create a design.",
            "goal_progress": "IN_PROGRESS",
            "confidence": 0.95,
            "next_action": {
                "action_type": "CLICK",
                "target": {"name": "Create a design", "role": "button"},
                "expected_effect": "Menu opens",
            },
        }),
        json.dumps({
            "decision_summary": "Design created successfully.",
            "goal_progress": "COMPLETED",
            "confidence": 0.98,
            "next_action": {
                "action_type": "COMPLETE_GOAL",
                "expected_effect": "Goal finished",
            },
        }),
    ]

    class MultiTurnMockRuntime(MockTestRuntime):
        def __init__(self, desc):
            super().__init__(desc)
            self.turn = 0

        async def chat(self, request: ModelChatRequest):
            content = step_responses[min(self.turn, len(step_responses) - 1)]
            self.turn += 1
            self.chat_invocations.append(request)
            return ModelGenerateResponse(model_id=self.model_id, content=content, total_duration_ms=50.0)

    runtime = MultiTurnMockRuntime(desc)
    mock_session_mgr = MagicMock()
    mock_session_mgr.get_active_runtime.return_value = runtime
    mock_session_mgr.list_all_descriptors = AsyncMock(return_value=[desc])
    mock_session_mgr.get_or_create_runtime = AsyncMock(return_value=runtime)

    router = ModelRouter(session_manager=mock_session_mgr)
    decision_engine = AgentDecisionEngine(router=router)

    obs = create_sample_desktop_obs()
    mock_observer = AsyncMock()
    mock_observer.observe = AsyncMock(return_value=CurrentStateObservation(
        active_window_title="Canva - Chrome",
        desktop_observation=obs,
    ))

    loop = AgentExecutionLoop(
        router=router,
        decision_engine=decision_engine,
        observer=mock_observer,
    )

    result = await loop.run(
        prompt="Open Canva and create a design",
        task_id="test_step4_task",
    )

    assert result.is_success is True
    assert len(runtime.chat_invocations) >= 2
    # Verify that model received the goal and multimodal screenshot
    assert "Open Canva and create a design" in runtime.chat_invocations[0].messages[1].content
    assert runtime.chat_invocations[0].messages[1].images is not None
