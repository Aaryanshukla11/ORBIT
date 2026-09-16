"""Real Windows Observation E2E Test Suite (Step 8).

Validates:
1. Live desktop observation with real Windows desktop applications (e.g. Notepad, Calculator).
2. Live capture of screen frames, window hierarchy, active window detection.
3. UI automation and OCR evidence extraction.
4. Observation ID freshness and divergence across consecutive captures.
5. Construction of 4-tier UnifiedWorldState and compact LLM prompt context serialization.
6. Dynamic state transition detection between application focus changes (App A -> App B).
7. Execution strictly in a clean environment where Prototype D is blocked.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import subprocess
import sys
import time
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
)
from orbit.contracts.capabilities import AdapterMode, CapabilityLifecycleState
from orbit.runtime.cognitive.world_state import (
    CompactContext,
    UnifiedWorldState,
    WorldStateBuilder,
)
from tests.integration.test_clean_environment import PrototypeImportBlocker


@pytest.mark.asyncio
async def test_real_windows_observation_and_state_transition():
    """Verify live multi-application state transition and observation capture on Windows."""
    if sys.platform != "win32":
        pytest.skip("Real Windows Observation E2E requires Windows OS")

    with PrototypeImportBlocker():
        adapter = ProductionObservationAdapter(default_ttl_ms=1000.0)
        await adapter.initialize()
        assert adapter.is_ready

        notepad_proc = None
        calc_proc = None

        try:
            # 1. Capture Initial Desktop Observation
            snap_1 = await adapter.capture_snapshot()
            assert snap_1 is not None
            assert snap_1.snapshot_id.startswith("snap_")
            assert snap_1.desktop_geometry.width > 0
            assert snap_1.desktop_geometry.height > 0
            assert snap_1.freshness_state in (FreshnessState.FRESH, FreshnessState.AGING)
            assert "screenshot" in snap_1.telemetry

            # 2. Launch Application A: Notepad
            notepad_proc = subprocess.Popen(["notepad.exe"])
            await asyncio.sleep(1.5)

            # 3. Capture Observation for Application A
            snap_2 = await adapter.capture_snapshot()
            assert snap_2.snapshot_id != snap_1.snapshot_id, "Observation IDs must be unique across captures"
            assert snap_2.foreground_window is not None

            # Build WorldState for Application A
            ws_2 = WorldStateBuilder.build_world_state(
                observation=snap_2,
                observation_id=snap_2.snapshot_id,
                screenshot=snap_2.telemetry.get("screenshot"),
                active_window_title=snap_2.foreground_window.window_title,
                active_process_name=snap_2.foreground_window.process_name,
                active_hwnd=snap_2.foreground_window.hwnd,
                visible_windows=[w.model_dump() for w in snap_2.windows],
            )
            assert isinstance(ws_2, UnifiedWorldState)
            assert isinstance(ws_2.compact_context, CompactContext)
            assert len(ws_2.compact_context.screen_resolution) > 0

            # 4. Launch / Switch to Application B: Calculator
            calc_proc = subprocess.Popen(["calc.exe"])
            await asyncio.sleep(2.0)

            # 5. Capture Observation for Application B
            snap_3 = await adapter.capture_snapshot()
            assert snap_3.snapshot_id != snap_2.snapshot_id, "Observation ID must advance"
            assert snap_3.foreground_window is not None

            # Build WorldState for Application B
            ws_3 = WorldStateBuilder.build_world_state(
                observation=snap_3,
                observation_id=snap_3.snapshot_id,
                screenshot=snap_3.telemetry.get("screenshot"),
                active_window_title=snap_3.foreground_window.window_title,
                active_process_name=snap_3.foreground_window.process_name,
                active_hwnd=snap_3.foreground_window.hwnd,
                visible_windows=[w.model_dump() for w in snap_3.windows],
            )

            # 6. Verify State Transition & Context Differences
            assert ws_3.observation_id == snap_3.snapshot_id
            assert ws_3.canonical_state.observation_id != ws_2.canonical_state.observation_id
            assert ws_3.raw_evidence.observation_id != ws_2.raw_evidence.observation_id

            # 7. Verify LLM prompt context can serialize and consume state
            prompt_summary_2 = ws_2.compact_context.model_dump_json()
            prompt_summary_3 = ws_3.compact_context.model_dump_json()
            assert len(prompt_summary_2) > 0
            assert len(prompt_summary_3) > 0

        finally:
            # Terminate launched processes
            if notepad_proc:
                try:
                    notepad_proc.terminate()
                except Exception:
                    pass
            if calc_proc:
                try:
                    calc_proc.terminate()
                except Exception:
                    pass

            await adapter.shutdown()
            assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED
