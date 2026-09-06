"""Integration tests for Multi-Modal Target Resolution, Safety Gating & Closed-Loop Zero-Dispatch Guarantees."""

import asyncio
from datetime import datetime, timezone
import pytest

from orbit.adapters.mocks import (
    MockHumanTakeoverAdapter,
    MockKeyboardAdapter,
    MockObservationAdapter,
    MockPointerAdapter,
    MockSafetyCoordinator,
    MockWorkspaceAdapter,
)
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
    ObservedElement,
    ObservedWindow,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import TaskStatus
from orbit.infrastructure.clock import SystemClock
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRWord,
)
from orbit.runtime.perception.visual_models import (
    VisualMatchRegion,
    VisualMatchResult,
    VisualMatchStatus,
    VisualMatcherKind,
)
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    TargetBoundingBox,
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)


@pytest.fixture
def multimodal_test_env():
    bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    tkv = MockHumanTakeoverAdapter()
    wsp = MockWorkspaceAdapter()
    sft = MockSafetyCoordinator()

    reg = CapabilityRegistry()
    reg.register(CapabilityType.OBSERVATION, obs)
    reg.register(CapabilityType.POINTER, ptr)
    reg.register(CapabilityType.KEYBOARD, kbd)
    reg.register(CapabilityType.HUMAN_TAKEOVER, tkv)
    reg.register(CapabilityType.WORKSPACE, wsp)
    reg.register(CapabilityType.SAFETY, sft)

    orch = OrbitOrchestrator(
        event_bus=bus,
        registry=reg,
        clock=SystemClock(),
    )
    return orch, obs, ptr, wsp, tkv


@pytest.mark.asyncio
async def test_multimodal_target_resolved_orchestrator_flow(multimodal_test_env):
    """Full end-to-end flow: MULTIMODAL target resolution -> coordinate validation -> pointer click."""
    orch, obs, ptr, wsp, tkv = multimodal_test_env
    await orch.initialize()

    element = ObservedElement(
        element_id="btn_submit_01",
        source="UI_AUTOMATION",
        name="Submit Form",
        role="Button",
        control_type="Button",
        bounds=BoundingBox(left=300, top=200, width=150, height=40),
        is_enabled=True,
    )

    ocr_word = OCRWord(
        text="Submit",
        normalized_text="submit",
        bounding_box=OCRBoundingBox(left=310, top=210, right=370, bottom=230, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.99,
    )
    ocr_region = OCRTextRegion(
        text="Submit Form",
        normalized_text="submit form",
        bounding_box=OCRBoundingBox(left=310, top=210, right=440, bottom=230, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[ocr_word],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        full_text="Submit Form",
        desktop_generation_id=wsp.desktop_generation_id,
    )

    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_multi_01",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        detected_elements=[element],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        telemetry={"ocr_result": ocr_res},
    )

    task = await orch.submit_task(
        session_id="sess_multi_01",
        prompt="Click the submit form button",
        context={
            "target_intent": {
                "strategy": "MULTIMODAL",
                "name": "Submit Form",
                "text": "Submit Form",
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED

    assert len(ptr.click_history) == 1
    click = ptr.click_history[0]
    assert 300 <= click["x"] < 450
    assert 200 <= click["y"] < 240

    await orch.shutdown()


@pytest.mark.asyncio
async def test_multimodal_contradictory_orchestrator_fails_closed(multimodal_test_env):
    """Contradictory multimodal channels fail closed with ZERO pointer clicks."""
    orch, obs, ptr, wsp, tkv = multimodal_test_env
    await orch.initialize()

    v1 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=100, top=100, right=140, bottom=140, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_gear",
        template_name="Settings",
    )
    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[v1],
        best_match=v1,
        desktop_generation_id=wsp.desktop_generation_id,
    )

    ocr_region = OCRTextRegion(
        text="Settings",
        normalized_text="settings",
        bounding_box=OCRBoundingBox(left=800, top=800, right=880, bottom=830, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        desktop_generation_id=wsp.desktop_generation_id,
    )

    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_multi_contra",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        telemetry={"ocr_result": ocr_res, "visual_match_result": vis_res},
    )

    task = await orch.submit_task(
        session_id="sess_multi_contra",
        prompt="Click the settings icon",
        context={
            "target_intent": {
                "strategy": "MULTIMODAL",
                "text": "Settings",
                "template_id": "tpl_gear",
                "metadata": {"require_colocated": True},
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_multimodal_ambiguous_orchestrator_fails_closed(multimodal_test_env):
    """Ambiguous multimodal evidence fails closed with ZERO pointer clicks."""
    orch, obs, ptr, wsp, tkv = multimodal_test_env
    await orch.initialize()

    v1 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=150, top=100, right=182, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_btn",
        template_name="Button",
    )
    v2 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=250, top=100, right=282, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_btn",
        template_name="Button",
    )
    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[v1, v2],
        best_match=v1,
        desktop_generation_id=wsp.desktop_generation_id,
    )

    ocr_region = OCRTextRegion(
        text="Label",
        normalized_text="label",
        bounding_box=OCRBoundingBox(left=200, top=100, right=240, bottom=120, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        desktop_generation_id=wsp.desktop_generation_id,
    )

    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_multi_ambig",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        telemetry={"ocr_result": ocr_res, "visual_match_result": vis_res},
    )

    task = await orch.submit_task(
        session_id="sess_multi_ambig",
        prompt="Click the button",
        context={
            "target_intent": {
                "strategy": "MULTIMODAL",
                "text": "Label",
                "template_id": "tpl_btn",
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_multimodal_dock_collision_orchestrator_fails_closed(multimodal_test_env):
    """Target resolving inside reserved AppBar dock fails workspace validation with ZERO clicks."""
    orch, obs, ptr, wsp, tkv = multimodal_test_env
    await orch.initialize()
    await wsp.register_appbar(edge="left", size=200)

    # Element placed inside left dock at left=50
    element = ObservedElement(
        element_id="btn_docked",
        source="UI_AUTOMATION",
        name="Docked Control",
        role="Button",
        control_type="Button",
        bounds=BoundingBox(left=50, top=100, width=80, height=30),
        is_enabled=True,
    )

    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_multi_dock",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        detected_elements=[element],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
    )

    task = await orch.submit_task(
        session_id="sess_multi_dock",
        prompt="Click docked control",
        context={
            "target_intent": {
                "strategy": "MULTIMODAL",
                "name": "Docked Control",
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.FAILED
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_multimodal_human_takeover_preempts_dispatch(multimodal_test_env):
    """Active human takeover pre-empts multimodal execution with ZERO clicks."""
    orch, obs, ptr, wsp, tkv = multimodal_test_env
    await orch.initialize()

    # Trigger human takeover
    tkv.trigger_takeover()

    element = ObservedElement(
        element_id="btn_normal",
        source="UI_AUTOMATION",
        name="Normal Button",
        role="Button",
        control_type="Button",
        bounds=BoundingBox(left=500, top=500, width=100, height=40),
        is_enabled=True,
    )

    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_multi_takeover",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        detected_elements=[element],
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
    )

    task = await orch.submit_task(
        session_id="sess_multi_takeover",
        prompt="Click normal button",
        context={
            "target_intent": {
                "strategy": "MULTIMODAL",
                "name": "Normal Button",
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.PAUSED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status in {TaskStatus.FAILED, TaskStatus.PAUSED, TaskStatus.CANCELLED}
    assert len(ptr.click_history) == 0

    await orch.shutdown()


@pytest.mark.asyncio
async def test_multimodal_visual_plus_ocr_anchoring_orchestrator_flow(multimodal_test_env):
    """Visual template with duplicate candidates disambiguated by OCR anchor clicks exact target."""
    orch, obs, ptr, wsp, tkv = multimodal_test_env
    await orch.initialize()

    # 3 visual candidate icons at X=100, X=300, X=500
    v1 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=100, top=100, right=132, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_gear",
        template_name="Settings",
    )
    v2 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=300, top=100, right=332, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_gear",
        template_name="Settings",
    )
    v3 = VisualMatchRegion(
        bounding_box=OCRBoundingBox(left=500, top=100, right=532, bottom=132, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        confidence=0.95,
        template_id="tpl_gear",
        template_name="Settings",
    )
    vis_res = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[v1, v2, v3],
        best_match=v1,
        template_id="tpl_gear",
        desktop_generation_id=wsp.desktop_generation_id,
    )

    # OCR text anchor near second icon (X=340)
    ocr_region = OCRTextRegion(
        text="General Settings",
        normalized_text="general settings",
        bounding_box=OCRBoundingBox(left=340, top=105, right=440, bottom=125, coordinate_space=OCRCoordinateSpace.SCREENSHOT_PIXEL_SPACE),
        words=[],
        confidence=0.99,
    )
    ocr_res = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.WINDOWS_NATIVE,
        text_regions=[ocr_region],
        full_text="General Settings",
        desktop_generation_id=wsp.desktop_generation_id,
    )

    obs.mock_snapshot = ObservationSnapshot(
        snapshot_id="snap_multi_anchor",
        generation_id=wsp.desktop_generation_id,
        timestamp_ns=10000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH,
        is_stale=False,
        telemetry={"ocr_result": ocr_res, "visual_match_result": vis_res},
    )

    task = await orch.submit_task(
        session_id="sess_multi_anchor",
        prompt="Click the general settings icon",
        context={
            "target_intent": {
                "strategy": "MULTIMODAL",
                "text": "General Settings",
                "template_id": "tpl_gear",
            }
        },
    )

    for _ in range(50):
        t = await orch.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        await asyncio.sleep(0.05)

    final_task = await orch.task_manager.get_task(task.task_id)
    assert final_task.status == TaskStatus.COMPLETED

    assert len(ptr.click_history) == 1
    click = ptr.click_history[0]
    # Must have clicked the second icon at X in [300, 332]
    assert 300 <= click["x"] <= 332
    assert 100 <= click["y"] <= 132

    await orch.shutdown()
