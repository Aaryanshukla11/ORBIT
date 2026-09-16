"""Integration test proving native perception independence in a clean environment.

Validates that ORBIT's ProductionObservationAdapter and perception pipeline:
1. Operate with ZERO dependency on prototypes/prototype_d_observation.
2. Initialize, capture screens, and construct rich ObservationSnapshots and WorldState
   in an environment where Prototype D is explicitly forbidden from import.
3. Pass negative import scans across all production files.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Any
import pytest

from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.observation.snapshot import (
    CoordinateSpace,
    FreshnessState,
    ObservationSnapshot,
)
from orbit.contracts.capabilities import AdapterMode, CapabilityLifecycleState
from orbit.runtime.cognitive.world_state import (
    CanonicalWorldState,
    PerceptionFusionLayer,
    RawEvidenceLayer,
    UnifiedWorldState,
    WorldStateBuilder,
)


class PrototypeImportBlocker:
    """Import hook / context manager that strictly forbids importing Prototype D."""

    def __enter__(self):
        # Remove any prototype paths from sys.path
        self._orig_sys_path = list(sys.path)
        sys.path = [p for p in sys.path if "prototype_d" not in p.replace("\\", "/")]

        # Forbid prototype_d modules
        self._blocked_modules = [m for m in sys.modules if "prototype_d" in m]
        for m in self._blocked_modules:
            del sys.modules[m]

        # Insert a meta path finder that raises ImportError if prototype_d is requested
        class ForbidPrototypeDFinder:
            def find_spec(self, fullname, path, target=None):
                if "prototype_d" in fullname or "prototype_d_observation" in fullname:
                    raise ImportError(f"PROTOTYPE D ACCESS FORBIDDEN in clean environment: {fullname}")
                return None

        self._finder = ForbidPrototypeDFinder()
        sys.meta_path.insert(0, self._finder)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, "_finder") and self._finder in sys.meta_path:
            sys.meta_path.remove(self._finder)
        sys.path = self._orig_sys_path


@pytest.mark.asyncio
async def test_negative_import_architecture_audit():
    """Architecture test: Verify ZERO production Python files reference prototype_d_observation."""
    repo_root = Path(__file__).resolve().parents[2]
    src_dir = repo_root / "src" / "orbit"

    forbidden_patterns = [
        "prototype_d_observation",
        "prototypes.prototype_d",
        "prototypes/prototype_d",
    ]

    violations = []
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in content:
                violations.append(f"{py_file.relative_to(repo_root)}: contains '{pattern}'")

    assert not violations, f"Production code contains forbidden Prototype D references:\n" + "\n".join(violations)


@pytest.mark.asyncio
async def test_clean_environment_native_observation():
    """Validate real desktop observation capture in a clean environment with Prototype D blocked."""
    with PrototypeImportBlocker():
        # Ensure import of Prototype D raises ImportError
        with pytest.raises(ImportError):
            import prototype_d_observation  # noqa: F401

        # 1. Instantiate ProductionObservationAdapter natively
        adapter = ProductionObservationAdapter(default_ttl_ms=1000.0)
        assert adapter.adapter_mode == AdapterMode.PRODUCTION
        assert adapter.lifecycle_state == CapabilityLifecycleState.CREATED

        # 2. Initialize native adapter
        await adapter.initialize()
        assert adapter.is_ready
        assert adapter.lifecycle_state == CapabilityLifecycleState.READY

        try:
            # 3. Capture Screen FrameData
            frame = await adapter.capture_screen(display_index=0)
            assert frame is not None
            assert frame.raw_bytes is not None
            assert len(frame.raw_bytes) > 0
            assert frame.resolution.width > 0
            assert frame.resolution.height > 0
            assert frame.format == "jpeg"

            # 4. Query Display Metrics
            metrics = await adapter.get_display_metrics()
            assert len(metrics) >= 1
            assert metrics[0].resolution.width > 0
            assert metrics[0].resolution.height > 0
            assert metrics[0].is_primary is True

            # 5. Capture rich ObservationSnapshot
            snapshot = await adapter.capture_snapshot()
            assert isinstance(snapshot, ObservationSnapshot)
            assert snapshot.snapshot_id.startswith("snap_")
            assert snapshot.desktop_geometry.width > 0
            assert snapshot.desktop_geometry.height > 0
            assert snapshot.coordinate_space == CoordinateSpace.VIRTUAL_DESKTOP
            assert snapshot.freshness_state in (FreshnessState.FRESH, FreshnessState.AGING)
            assert snapshot.is_stale is False

            # Verify snapshot contains real window hierarchy if running on interactive Windows
            if sys.platform == "win32":
                assert snapshot.foreground_window is not None
                assert snapshot.foreground_window.hwnd > 0
                assert len(snapshot.windows) > 0

            # 6. Verify UnifiedWorldState construction from snapshot
            world_state = WorldStateBuilder.build_world_state(
                observation=snapshot,
                observation_id=snapshot.snapshot_id,
                screenshot=snapshot.telemetry.get("screenshot"),
                active_window_title=snapshot.foreground_window.window_title if snapshot.foreground_window else "",
                active_process_name=snapshot.foreground_window.process_name if snapshot.foreground_window else "",
                active_hwnd=snapshot.foreground_window.hwnd if snapshot.foreground_window else None,
                visible_windows=[w.model_dump() for w in snapshot.windows],
            )
            assert isinstance(world_state, UnifiedWorldState)
            assert world_state.observation_id == snapshot.snapshot_id
            assert world_state.raw_evidence.screen_width > 0
            assert world_state.raw_evidence.screen_height > 0
            if snapshot.foreground_window:
                assert world_state.canonical_state.active_window_hwnd == snapshot.foreground_window.hwnd
                assert world_state.canonical_state.active_process_name == snapshot.foreground_window.process_name

            # 7. Check capability health reporting
            health = await adapter.get_health()
            assert health is not None
            assert health.status.value in ("HEALTHY", "DEGRADED")

        finally:
            await adapter.shutdown()
            assert adapter.lifecycle_state == CapabilityLifecycleState.STOPPED
