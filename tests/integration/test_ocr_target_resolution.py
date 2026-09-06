"""Integration tests for OCR target resolution, workspace coordinate safety, and orchestrator flow."""

import pytest
import asyncio
from datetime import datetime, timezone
from typing import Optional

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
from orbit.runtime.perception.engine import SemanticPerceptionEngine
from orbit.runtime.perception.models import (
    OCRBoundingBox,
    OCRCoordinateSpace,
    OCRProviderKind,
    OCRResult,
    OCRStatus,
    OCRTextRegion,
    OCRWord,
)
from orbit.runtime.perception.ocr import MockOCRProvider
from orbit.runtime.targeting.locator import EvidenceBasedTargetLocator
from orbit.runtime.targeting.models import (
    TargetIntent,
    TargetResolutionStatus,
    TargetStrategy,
)
from orbit.runtime.verification.verifier import ActionVerifier


def _create_snapshot(generation_id: int = 0, is_stale: bool = False) -> ObservationSnapshot:
    return ObservationSnapshot(
        snapshot_id=f"snap_int_{generation_id}",
        generation_id=generation_id,
        timestamp_ns=1000000,
        desktop_geometry=BoundingBox(left=0, top=0, width=1920, height=1080),
        coordinate_space=CoordinateSpace.VIRTUAL_DESKTOP,
        confidence=ObservationConfidence.CONFIRMED,
        freshness_state=FreshnessState.FRESH if not is_stale else FreshnessState.STALE,
        is_stale=is_stale,
    )


@pytest.mark.asyncio
async def test_ocr_target_resolution_and_workspace_coordinate_validation():
    # 1. Setup Workspace & Generation
    wsp = MockWorkspaceAdapter()
    await wsp.initialize()
    active_gen = wsp.get_desktop_generation()

    # 2. Setup OCR text region under active generation
    region = OCRTextRegion(
        text="Open Project Settings",
        normalized_text="open project settings",
        bounding_box=OCRBoundingBox(left=200, top=300, right=450, bottom=360),
        words=[],
        confidence=0.98,
        source_provider="MOCK",
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="Open Project Settings",
        observation_id=f"snap_int_{active_gen}",
        desktop_generation_id=active_gen,
    )

    # 3. Setup Locator
    locator = EvidenceBasedTargetLocator()
    snap = _create_snapshot(generation_id=active_gen)
    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Open Project Settings",
        metadata={"ocr_result": ocr_result},
    )

    # 4. Locate target
    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None

    # 5. Validate coordinates against Workspace
    val_res = wsp.validate_coordinate(
        res.target.safe_point.x,
        res.target.safe_point.y,
        expected_generation=snap.generation_id,
    )
    assert val_res.is_valid is True
    assert val_res.status == CoordinateValidationStatus.VALID


@pytest.mark.asyncio
async def test_ocr_target_inside_appbar_dock_boundary_fails_closed():
    # Setup Workspace with right-docked AppBar (width 300px on 1920x1080 display -> [1620..1920) is reserved)
    wsp = MockWorkspaceAdapter()
    await wsp.initialize()
    await wsp.register_appbar(edge="right", size=300)
    active_gen = wsp.get_desktop_generation()

    # OCR detects text inside the reserved dock area (e.g. at x=1750, y=400)
    region = OCRTextRegion(
        text="Reserved Tool Window",
        normalized_text="reserved tool window",
        bounding_box=OCRBoundingBox(left=1650, top=350, right=1880, bottom=450),
        words=[],
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="Reserved Tool Window",
        observation_id=f"snap_int_{active_gen}",
        desktop_generation_id=active_gen,
    )

    locator = EvidenceBasedTargetLocator()
    snap = _create_snapshot(generation_id=active_gen)
    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Reserved Tool Window",
        metadata={"ocr_result": ocr_result},
    )

    # Target locator resolves the bounding box
    res = locator.locate_target(snap, intent)
    assert res.status == TargetResolutionStatus.RESOLVED
    assert res.target is not None

    # Workspace validation MUST reject the coordinate because it collides with reserved AppBar dock area
    val_res = wsp.validate_coordinate(
        res.target.safe_point.x,
        res.target.safe_point.y,
        expected_generation=active_gen,
    )
    assert val_res.is_valid is False
    assert val_res.status == CoordinateValidationStatus.RESERVED_WORKSPACE_COLLISION


@pytest.mark.asyncio
async def test_orchestrator_closed_loop_ocr_target_flow():
    # 1. Setup test capabilities and mock adapters
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

    region = OCRTextRegion(
        text="Launch Application",
        normalized_text="launch application",
        bounding_box=OCRBoundingBox(left=100, top=100, right=250, bottom=150),
        words=[],
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="Launch Application",
        observation_id="snap_mock_1",
        desktop_generation_id=0,
    )

    mock_ocr_provider = MockOCRProvider(injected_regions=[region])
    perception_engine = SemanticPerceptionEngine(ocr_provider=mock_ocr_provider)

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
        perception_engine=perception_engine,
    )
    await orchestrator.initialize()

    # 2. Submit task with OCR_TEXT strategy
    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Launch Application",
        metadata={"ocr_result": ocr_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_ocr_test",
        prompt="Click Launch Application",
        context={"target_intent": intent.model_dump()},
    )

    # 3. Wait for background execution to complete
    for _ in range(50):
        t = await orchestrator.task_manager.get_task(task.task_id)
        if t and t.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            break
        await asyncio.sleep(0.02)

    final_task = await orchestrator.task_manager.get_task(task.task_id)
    assert final_task is not None
    assert final_task.status == TaskStatus.COMPLETED
    assert final_task.plan is not None
    assert len(final_task.plan.steps) == 1
    # Check that pointer recorded click or movement inside the safe target bounds
    assert len(ptr.click_history) >= 1 or len(ptr.move_history) >= 1
    last_click = ptr.click_history[-1] if ptr.click_history else None
    if last_click:
        assert 100 < last_click["x"] < 250
        assert 100 < last_click["y"] < 150


@pytest.mark.asyncio
async def test_ambiguous_ocr_target_causes_zero_pointer_dispatches():
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

    # Two duplicate "Cancel" buttons
    r1 = OCRTextRegion(
        text="Cancel",
        normalized_text="cancel",
        bounding_box=OCRBoundingBox(left=100, top=100, right=200, bottom=150),
        words=[],
    )
    r2 = OCRTextRegion(
        text="Cancel",
        normalized_text="cancel",
        bounding_box=OCRBoundingBox(left=300, top=100, right=400, bottom=150),
        words=[],
    )
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[r1, r2],
        full_text="Cancel Cancel",
        observation_id="snap_mock_1",
        desktop_generation_id=0,
    )

    mock_ocr_provider = MockOCRProvider(injected_regions=[r1, r2])
    perception_engine = SemanticPerceptionEngine(ocr_provider=mock_ocr_provider)

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
        perception_engine=perception_engine,
    )
    await orchestrator.initialize()

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Cancel",
        metadata={"ocr_result": ocr_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_ambig_test",
        prompt="Click Cancel",
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
    # Zero pointer dispatches
    assert len(ptr.click_history) == 0
    assert len(ptr.move_history) == 1  # Only initial starting point


@pytest.mark.asyncio
async def test_stale_ocr_observation_causes_zero_pointer_dispatches():
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

    region = OCRTextRegion(
        text="Settings",
        normalized_text="settings",
        bounding_box=OCRBoundingBox(left=100, top=100, right=200, bottom=150),
        words=[],
    )
    # Stale OCR Result with generation mismatch (gen 99 != wsp gen 0)
    ocr_result = OCRResult(
        status=OCRStatus.SUCCESS,
        provider_kind=OCRProviderKind.MOCK,
        text_regions=[region],
        full_text="Settings",
        observation_id="snap_mock_old",
        desktop_generation_id=99,
    )

    mock_ocr_provider = MockOCRProvider(injected_regions=[region])
    perception_engine = SemanticPerceptionEngine(ocr_provider=mock_ocr_provider)

    orchestrator = OrbitOrchestrator(
        event_bus=event_bus,
        registry=registry,
        perception_engine=perception_engine,
    )
    await orchestrator.initialize()

    intent = TargetIntent(
        strategy=TargetStrategy.OCR_TEXT,
        text="Settings",
        metadata={"ocr_result": ocr_result},
    )

    task = await orchestrator.submit_task(
        session_id="session_stale_test",
        prompt="Click Settings",
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
    assert len(ptr.move_history) == 1  # Only initial starting point
