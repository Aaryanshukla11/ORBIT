"""Benchmark environment manager: OS process cleanup and scratchpad preparation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class BenchmarkEnvironmentManager:
    """Manages pre-task and post-task OS cleanups to ensure task isolation."""

    DEFAULT_CLEAN_PROCESSES = [
        "notepad.exe",
        "mspaint.exe",
        "CalculatorApp.exe",
        "calc.exe",
        "msedge.exe",
    ]

    def __init__(self, scratchpad_root: Optional[Path] = None) -> None:
        self.scratchpad_root = scratchpad_root or (Path.cwd() / "scratch" / "benchmark_scratchpad")
        self.desktop_dir = Path.home() / "Desktop"

    def setup_environment(self, clean_processes: Optional[List[str]] = None) -> Path:
        """Reset environment before running a task."""
        # 1. Clean designated processes
        procs_to_kill = clean_processes if clean_processes is not None else self.DEFAULT_CLEAN_PROCESSES
        self._terminate_processes(procs_to_kill)

        # 2. Setup scratchpad directory
        if self.scratchpad_root.exists():
            try:
                shutil.rmtree(self.scratchpad_root)
            except Exception as e:
                logger.warning(f"Could not purge scratchpad directory {self.scratchpad_root}: {e}")

        self.scratchpad_root.mkdir(parents=True, exist_ok=True)
        time.sleep(0.5)
        return self.scratchpad_root

    def teardown_environment(self, clean_processes: Optional[List[str]] = None, cleanup_files: Optional[List[str]] = None) -> None:
        """Clean up post-task state."""
        procs_to_kill = clean_processes if clean_processes is not None else self.DEFAULT_CLEAN_PROCESSES
        self._terminate_processes(procs_to_kill)

        # Cleanup designated files on Desktop or workspace if requested
        if cleanup_files:
            for fname in cleanup_files:
                for candidate in [self.desktop_dir / fname, self.scratchpad_root / fname, Path.cwd() / fname]:
                    if candidate.exists():
                        try:
                            if candidate.is_file():
                                candidate.unlink()
                            elif candidate.is_dir():
                                shutil.rmtree(candidate)
                        except Exception as e:
                            logger.warning(f"Failed to cleanup test file {candidate}: {e}")

    def _terminate_processes(self, process_names: List[str]) -> None:
        """Terminate background processes using taskkill."""
        for proc in process_names:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", proc],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                pass
