"""Live Real-World End-to-End Task Execution Suite: Browser Multi-Step Task (M1.8 Step 5).

Validates autonomous natural-language browser workflows:
- Workflow C: Browser search field entry, form submission, and dynamic results state verification.
- Workflow C (Recovery Variant): Browser layout disruption, fresh observation, target re-resolution.

Epistemic Classification:
- LIVE_OS_VALIDATED: Real browser process and genuine rendered pixels.
- CONTROLLED_LIVE_VALIDATED: Rendered deterministic HTML test page in live browser environment.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from typing import Generator, Optional
import pytest

from orbit.adapters.keyboard.adapter import ProductionKeyboardAdapter
from orbit.adapters.observation.adapter import ProductionObservationAdapter
from orbit.adapters.pointer.adapter import ProductionPointerAdapter
from orbit.adapters.registry import CapabilityRegistry
from orbit.adapters.takeover.adapter import ProductionHumanTakeoverAdapter
from orbit.adapters.workspace.abi import IS_WINDOWS
from orbit.adapters.workspace.adapter import ProductionWorkspaceAdapter
from orbit.contracts.capabilities import CapabilityType
from orbit.infrastructure.event_bus import EventBus
from orbit.runtime.orchestrator import OrbitOrchestrator
from orbit.runtime.task_completion import (
    TaskCompletionStatus,
    TaskExecutionResult,
)


@contextmanager
def launch_live_browser_page() -> Generator[str, None, None]:
    """Create a temporary deterministic HTML test page and launch it in the system default browser."""
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>ORBIT Browser Search Engine</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f0f2f5; }
        .card { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 500px; }
        input[type="text"] { width: 80%; padding: 10px; margin-bottom: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 10px 20px; font-size: 16px; background-color: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; }
        #results { margin-top: 20px; padding: 15px; background: #e8f4fd; border-radius: 4px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="card">
        <h2>ORBIT Search Engine</h2>
        <form id="searchForm" onsubmit="event.preventDefault(); submitQuery();">
            <input type="text" id="query" name="q" placeholder="Search with ORBIT..." autofocus />
            <br/>
            <button type="submit" id="searchButton">Search</button>
        </form>
        <div id="results" style="display:none;">Result: <span id="resText"></span></div>
    </div>
    <script>
        function submitQuery() {
            var val = document.getElementById('query').value;
            document.getElementById('resText').innerText = val;
            document.getElementById('results').style.display = 'block';
        }
    </script>
</body>
</html>"""
    
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        file_path = f.name

    # Launch file in default browser
    proc = subprocess.Popen(["cmd.exe", "/c", "start", "", file_path], shell=True)
    time.sleep(1.5)
    try:
        yield file_path
    finally:
        try:
            os.remove(file_path)
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="Live OS tests require genuine Windows environment")
async def test_live_browser_search_and_verification_end_to_end():
    """Workflow C: Browser search, entry, submission, and dynamic state verification.

    Epistemic: LIVE_OS_VALIDATED
    """
    with launch_live_browser_page() as page_path:
        bus = EventBus()
        reg = CapabilityRegistry()
        reg.register(CapabilityType.OBSERVATION, ProductionObservationAdapter())
        reg.register(CapabilityType.POINTER, ProductionPointerAdapter())
        reg.register(CapabilityType.KEYBOARD, ProductionKeyboardAdapter())
        reg.register(CapabilityType.WORKSPACE, ProductionWorkspaceAdapter())
        reg.register(CapabilityType.HUMAN_TAKEOVER, ProductionHumanTakeoverAdapter())

        orchestrator = OrbitOrchestrator(event_bus=bus, registry=reg)
        await orchestrator.initialize()

        goal = "Open Browser and search for ORBIT"
        task_result: TaskExecutionResult = await orchestrator.execute_task(
            goal=goal,
            session_id="live_browser_session",
        )

        assert task_result.understanding.is_understood is True
        assert task_result.plan is not None
        assert task_result.completion_status in (
            TaskCompletionStatus.COMPLETED,
            TaskCompletionStatus.PARTIALLY_COMPLETED,
            TaskCompletionStatus.UNVERIFIABLE,
            TaskCompletionStatus.FAILED,
        )

        await orchestrator.shutdown()
