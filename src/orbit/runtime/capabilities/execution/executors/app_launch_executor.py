"""Application Launch Capability Executor (M1.9)."""

from __future__ import annotations

import asyncio
import inspect
import logging
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple

from orbit.runtime.capabilities.execution.contracts import (
    CapabilityExecutionRequest,
    CapabilityExecutionResult,
    StageOutcomeStatus,
)
from orbit.runtime.capabilities.execution.executors.base import BaseCapabilityExecutor

logger = logging.getLogger(__name__)


class ApplicationLaunchExecutor(BaseCapabilityExecutor):
    """Executes LAUNCH_APPLICATION by invoking the workspace adapter or host OS launch APIs."""

    def __init__(self, workspace: Optional[Any] = None) -> None:
        super().__init__(capability_id="LAUNCH_APPLICATION")
        self._workspace = workspace

    def is_available(self) -> bool:
        # Launching is always supported on host OS via workspace or Windows ShellExecute
        return True

    def validate_inputs(self, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        app_name = parameters.get("application_name") or parameters.get("app_name")
        if not app_name:
            return False, "Missing required parameter 'application_name' or 'app_name'"
        return True, None

    async def _execute_internal(
        self,
        request: CapabilityExecutionRequest,
    ) -> CapabilityExecutionResult:
        app_name = str(request.parameters.get("application_name") or request.parameters.get("app_name")).strip()
        logger.info("[ApplicationLaunchExecutor] Launching application '%s'", app_name)

        pid: Optional[int] = None
        dispatch_success = False
        err_msg: Optional[str] = None

        if self._workspace is not None and hasattr(self._workspace, "launch_process"):
            raw_proc = self._workspace.launch_process(app_name)
            proc_info = await raw_proc if inspect.isawaitable(raw_proc) else raw_proc
            dispatch_success = bool(proc_info)
            if hasattr(proc_info, "pid"):
                pid = proc_info.pid
        else:
            try:
                if sys.platform == "win32":
                    import ctypes
                    app_lower = app_name.lower()
                    if "paint" in app_lower:
                        try:
                            ctypes.windll.shell32.ShellExecuteW(None, "open", "mspaint.exe", None, None, 1)
                        except Exception:
                            subprocess.Popen("mspaint.exe", shell=True)
                    elif "calc" in app_lower:
                        try:
                            ctypes.windll.shell32.ShellExecuteW(None, "open", "calc.exe", None, None, 1)
                        except Exception:
                            subprocess.Popen("calc.exe", shell=True)
                    elif "notepad" in app_lower:
                        try:
                            subprocess.Popen("cmd /c start notepad.exe", shell=True)
                        except Exception:
                            subprocess.Popen("notepad.exe", shell=True)
                    else:
                        subprocess.Popen(f"start {app_name}", shell=True)
                else:
                    subprocess.Popen(app_name, shell=True)
                dispatch_success = True
            except Exception as ex:
                dispatch_success = False
                err_msg = str(ex)

        if not dispatch_success:
            return CapabilityExecutionResult(
                capability_id=self.capability_id,
                stage_index=request.stage_index,
                dispatch_success=False,
                execution_success=False,
                stage_status=StageOutcomeStatus.FAILED,
                failure_code="LAUNCH_FAILED",
                failure_reason=err_msg or f"Failed to launch application '{app_name}'",
            )

        # Allow brief window settlement
        await asyncio.sleep(0.5)

        return CapabilityExecutionResult(
            capability_id=self.capability_id,
            stage_index=request.stage_index,
            dispatch_success=True,
            execution_success=True,
            stage_status=StageOutcomeStatus.DISPATCHED,
            output={
                "application_name": app_name,
                "pid": pid,
            },
            evidence={
                "target_app": app_name,
                "dispatch_method": "workspace" if self._workspace else "host_os",
            },
        )
