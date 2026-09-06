"""Integration tests for visual template target resolution, coordinate safety, and orchestrator flow."""

import pytest
import asyncio
from datetime import datetime, timezone
from typing import Optional
from PIL import Image, ImageDraw

from orbit.adapters.mocks.mock_keyboard import MockKeyboardAdapter
from orbit.adapters.mocks.mock_observation import MockObservationAdapter
from orbit.adapters.mocks.mock_pointer import MockPointerAdapter
from orbit.adapters.mocks.mock_takeover import MockHumanTakeoverAdapter
from orbit.adapters.mocks.mock_workspace import MockWorkspaceAdapter
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationConfidence,
    ObservationSnapshot,
)
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.workspace.geometry import (
    CoordinateValidationResult,
    CoordinateValidationStatus,
)
from orbit.contracts.capabilities import CapabilityType
from orbit.contracts.runtime import SystemState, TaskStatus
from orbit.infrastructure.event_bus import EventBus
from orbit.models.common import BoundingBox
from orbit.runtime.execution.engine import ClosedLoopExecutionEngine
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.perception.coordinate_mapper import OCRCoordinateMapper
from orbit.runtime.perception.models import OCRBoundingBox, OCRCoordinateSpace
from orbit.runtime.perception.visual_engine import VisualPerceptionEngine
from orbit.runtime.perception.visual_matcher import (
    MockVisualMatcher,
    TemplateVisualMatcher,
)
from orbit.runtime.perception.visual_models import (
    VisualMatchPolicy,
    VisualMatchRegion,
    VisualMatchResult,
    VisualMatchStatus,
    VisualMatcherKind,
    VisualTemplate,
    VisualTemplateSource,
)
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)
from orbit.runtime.verification.verifier import ActionVerifier


def _create_snapshot(
    generation_id: int = 0,
    is_stale: bool = False,
    screenshot_image: Optional[Image.Image] = None,
) -> ObservationSnapshot:
    snap = ObservationSnapshot(
        snapshot_id=f"snap_vis_{generation_id}",
        generation_id=generation_id,
        timestamp_ns=1000000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH if not is_stale else FreshnessState.STALE,
        is_stale=is_stale,
    )
    if screenshot_image is not None:
        snap.telemetry["screenshot"] = screenshot_image
    return snap


def _generate_test_scene_and_template() -> tuple[Image.Image, VisualTemplate]:
    scene = Image.new("RGB", (600, 400), color=(240, 240, 245))
    draw = ImageDraw.Draw(scene)
    draw.rectangle([50, 50, 550, 350], fill=(255, 255, 255), outline=(180, 180, 180))

    # Distinct gear icon pattern at (200, 150) size 40x40
    ix, iy = 200, 150
    draw.rectangle([ix, iy, ix + 40, iy + 40], fill=(0, 120, 215))
    draw.ellipse([ix + 10, iy + 10, ix + 30, iy + 30], fill=(255, 255, 255))
    draw.ellipse([ix + 15, iy + 15, ix + 25, iy + 25], fill=(0, 120, 215))

    icon_img = scene.crop((ix, iy, ix + 40, iy + 40))
    template = VisualTemplate.from_image(
        template_id="tpl_gear_btn",
        name="Settings Gear Button",
        image=icon_img,
        source=VisualTemplateSource.TRUSTED_REGISTERED_TEMPLATE,
    )
    return scene, template


# --- Integration Test 1: Registered Template -> Visual Match -> Safe Action Point -> Workspace Validation ---

@pytest.mark.asyncio
async def test_visual_template_resolution_and_workspace_validation():
    wsp = MockWorkspaceAdapter()
    await wsp.initialize()
    active_gen = wsp.get_desktop_generation()

    scene, template = _generate_test_scene_and_template()

    match_region = VisualMatchRegion(
        template_id=template.template_id,
        template_name=template.name,
        bounding_box=OCRBoundingBox(left=200, top=150, right=240, bottom=190),
        confidence=0.98,
        scale_factor=1.0,
        source_provider="TEMPLATE_NCC",
    )
    match_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id=template.template_id,
        observation_id=f"snap_vis_{active_gen}",
        desktop_generation_id=active_gen,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_snapshot(generation_id=active_gen, screenshot_image=scene)

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": match_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None
    assert res.target.safe_point.x == 219
    assert res.target.safe_point.y == 169

    val_res = wsp.validate_coordinate(
        res.target.safe_point.x,
        res.target.safe_point.y,
        expected_generation=snap.generation_id,
    )
    assert val_res.is_valid is True
    assert val_res.status == CoordinateValidationStatus.VALID


# --- Integration Test 2: Low-Confidence Match -> ZERO Dispatch ---

@pytest.mark.asyncio
async def test_low_confidence_visual_match_causes_zero_dispatch():
    event_bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()

    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)

    scene, template = _generate_test_scene_and_template()

    # Low confidence result (status=LOW_CONFIDENCE)
    low_conf_result = VisualMatchResult(
        status=VisualMatchStatus.LOW_CONFIDENCE,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[],
        best_match=None,
        template_id=template.template_id,
        desktop_generation_id=0,
        error_message="Best match score 0.65 below minimum confidence 0.85",
    )

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )
    await orchestrator.initialize()

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": low_conf_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_low_conf_test",
        prompt="Click Settings Gear",
        context={"target_intent": intent.model_dump()},
    )

    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.02)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.FAILED
    # Zero pointer clicks dispatched
    assert len(ptr.click_history) == 0


# --- Integration Test 3: Duplicate Match Ambiguity -> ZERO Dispatch ---

@pytest.mark.asyncio
async def test_duplicate_visual_match_ambiguity_causes_zero_dispatch():
    event_bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()

    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)

    _, template = _generate_test_scene_and_template()

    m1 = VisualMatchRegion(
        template_id=template.template_id,
        template_name=template.name,
        bounding_box=OCRBoundingBox(left=100, top=100, right=140, bottom=140),
        confidence=0.95,
    )
    m2 = VisualMatchRegion(
        template_id=template.template_id,
        template_name=template.name,
        bounding_box=OCRBoundingBox(left=400, top=100, right=440, bottom=140),
        confidence=0.95,
    )
    ambiguous_result = VisualMatchResult(
        status=VisualMatchStatus.AMBIGUOUS,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[m1, m2],
        best_match=None,
        template_id=template.template_id,
        desktop_generation_id=0,
    )

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )
    await orchestrator.initialize()

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": ambiguous_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_ambig_vis_test",
        prompt="Click Settings Gear",
        context={"target_intent": intent.model_dump()},
    )

    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.02)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.FAILED
    assert len(ptr.click_history) == 0


# --- Integration Test 4: Stale Screenshot Rejection -> ZERO Dispatch ---

@pytest.mark.asyncio
async def test_stale_visual_observation_causes_zero_dispatch():
    event_bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()

    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)

    _, template = _generate_test_scene_and_template()

    match_region = VisualMatchRegion(
        template_id=template.template_id,
        template_name=template.name,
        bounding_box=OCRBoundingBox(left=200, top=150, right=240, bottom=190),
        confidence=0.98,
    )
    # Stale generation (generation 88 != wsp generation 0)
    stale_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id=template.template_id,
        desktop_generation_id=88,
    )

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )
    await orchestrator.initialize()

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": stale_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_stale_vis_test",
        prompt="Click Settings Gear",
        context={"target_intent": intent.model_dump()},
    )

    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.02)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.FAILED
    assert len(ptr.click_history) == 0


# --- Integration Test 5: Visual Target Colliding with Reserved AppBar Dock -> ZERO Dispatch ---

@pytest.mark.asyncio
async def test_visual_target_inside_appbar_dock_fails_closed():
    # Setup Workspace with right-docked AppBar (width 300px on 1920x1080 display -> [1620..1920) is reserved)
    wsp = MockWorkspaceAdapter()
    await wsp.initialize()
    await wsp.register_appbar(edge="right", size=300)
    active_gen = wsp.get_desktop_generation()

    _, template = _generate_test_scene_and_template()

    # Visual template detected inside reserved dock region at (1700, 200)
    match_region = VisualMatchRegion(
        template_id=template.template_id,
        template_name=template.name,
        bounding_box=OCRBoundingBox(left=1700, top=200, right=1740, bottom=240),
        confidence=0.96,
    )
    match_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id=template.template_id,
        observation_id=f"snap_vis_{active_gen}",
        desktop_generation_id=active_gen,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_snapshot(generation_id=active_gen)
    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": match_result},
    )

    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None

    # Workspace validation MUST reject the coordinate
    val_res = wsp.validate_coordinate(
        res.target.safe_point.x,
        res.target.safe_point.y,
        expected_generation=active_gen,
    )
    assert val_res.is_valid is False
    assert val_res.status == CoordinateValidationStatus.RESERVED_WORKSPACE_COLLISION


# --- Integration Test 6: Closed-Loop Execution Engine with Visual Target ---

@pytest.mark.asyncio
async def test_closed_loop_execution_with_visual_template_target():
    event_bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()

    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)

    scene, template = _generate_test_scene_and_template()

    match_region = VisualMatchRegion(
        template_id=template.template_id,
        template_name=template.name,
        bounding_box=OCRBoundingBox(left=200, top=150, right=240, bottom=190),
        confidence=0.97,
    )
    match_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id=template.template_id,
        desktop_generation_id=0,
    )

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )
    await orchestrator.initialize()

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": match_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_closed_loop_vis",
        prompt="Click Settings Gear",
        context={"target_intent": intent.model_dump()},
    )

    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.02)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.COMPLETED
    assert len(ptr.click_history) == 1
    click = ptr.click_history[0]
    # Center of [200, 150, 240, 190] is (219, 169)
    assert click["x"] == 219
    assert click["y"] == 169


# --- Integration Test 7: Human Takeover Preemption during Visual Resolution ---

@pytest.mark.asyncio
async def test_human_takeover_preempts_visual_target_execution():
    event_bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()
    tkv = MockHumanTakeoverAdapter()

    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)
    registry.register(CapabilityType.HUMAN_TAKEOVER, tkv)

    _, template = _generate_test_scene_and_template()

    match_region = VisualMatchRegion(
        template_id=template.template_id,
        template_name=template.name,
        bounding_box=OCRBoundingBox(left=200, top=150, right=240, bottom=190),
        confidence=0.97,
    )
    match_result = VisualMatchResult(
        status=VisualMatchStatus.MATCHED,
        matcher_kind=VisualMatcherKind.TEMPLATE_NCC,
        matches=[match_region],
        best_match=match_region,
        template_id=template.template_id,
        desktop_generation_id=0,
    )

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )
    await orchestrator.initialize()

    # Trigger human takeover BEFORE submitting task or right at dispatch
    await orchestrator.handle_human_takeover(reason="User physically grabbed mouse")

    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
        metadata={"visual_match_result": match_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_takeover_vis",
        prompt="Click Settings Gear",
        context={"target_intent": intent.model_dump()},
    )

    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.02)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
    # ZERO pointer clicks dispatched
    assert len(ptr.click_history) == 0


# --- Integration Test 8: Closed-Loop Dynamic Visual Perception Retry ---

@pytest.mark.asyncio
async def test_closed_loop_visual_target_retry_with_fresh_snapshot():
    event_bus = EventBus()
    obs = MockObservationAdapter()
    ptr = MockPointerAdapter()
    kbd = MockKeyboardAdapter()
    wsp = MockWorkspaceAdapter()

    registry = CapabilityRegistry()
    registry.register(CapabilityType.OBSERVATION, obs)
    registry.register(CapabilityType.POINTER, ptr)
    registry.register(CapabilityType.KEYBOARD, kbd)
    registry.register(CapabilityType.WORKSPACE, wsp)

    scene, template = _generate_test_scene_and_template()

    # Pass template in intent so dynamic matching runs against fresh observation
    intent = TargetIntent(
        strategy=TargetStrategy.VISUAL_TEMPLATE,
        template=template,
    )

    # Put screenshot in mock observation adapter
    obs.mock_snapshot = _create_snapshot(generation_id=0, screenshot_image=scene)

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
    )
    await orchestrator.initialize()

    task = await orchestrator.submit_task(
        session_id="session_dynamic_vis_match",
        prompt="Click Settings Gear",
        context={"target_intent": intent.model_dump()},
    )

    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.02)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.COMPLETED
    assert len(ptr.click_history) == 1
    click = ptr.click_history[0]
    assert click["x"] == 219
    assert click["y"] == 169

