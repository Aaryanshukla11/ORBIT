"""Deterministic, secure application launcher boundary for ORBIT.

Treats application identifiers strictly as data, resolves names through an
approved application registry, and executes without shell string interpolation.
"""

from dataclasses import dataclass
import logging
import os
import re
import subprocess
import sys
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Standard application alias dictionary mapping user-facing names to verified executable identifiers
APPROVED_APPLICATION_REGISTRY: Dict[str, str] = {
    "notepad": "notepad.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "explorer": "explorer.exe",
}

# Dangerous shell metacharacters that must never be present in application launch data
SHELL_METACHAR_PATTERN = re.compile(r"[&|;><`$\n\r\t]")


@dataclass(frozen=True)
class ApplicationLaunchResult:
    """Structured result of an application launch attempt."""

    success: bool
    app_name: str
    executable_path: Optional[str] = None
    pid: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class ApplicationLauncher:
    """Secure application launcher boundary.

    Eliminates shell string construction and enforces deterministic application resolution.
    """

    def __init__(self, registry: Optional[Dict[str, str]] = None) -> None:
        self._registry = dict(registry or APPROVED_APPLICATION_REGISTRY)

    @property
    def registered_applications(self) -> Dict[str, str]:
        return dict(self._registry)

    def resolve_application(self, app_name: str) -> Optional[str]:
        """Deterministically resolve an application identifier to an approved executable path/name."""
        if not app_name or not isinstance(app_name, str):
            return None

        clean_name = app_name.strip()

        # Reject dangerous characters
        if SHELL_METACHAR_PATTERN.search(clean_name):
            logger.warning("[APPLICATION LAUNCHER] Rejected application name containing shell metacharacters: '%s'", clean_name)
            return None

        # Reject path traversal
        if ".." in clean_name or "/" in clean_name or "\\" in clean_name:
            logger.warning("[APPLICATION LAUNCHER] Rejected application name with path traversal: '%s'", clean_name)
            return None

        name_lower = clean_name.lower()

        # Check standard registry
        if name_lower in self._registry:
            return self._registry[name_lower]

        # Check with .exe extension
        if name_lower.endswith(".exe"):
            stem = name_lower[:-4]
            if stem in self._registry:
                return self._registry[stem]

        # Unknown / unapproved application name fails deterministic resolution
        return None

    def launch(self, app_name: str) -> ApplicationLaunchResult:
        """Launch an approved application deterministically without shell execution."""
        resolved_exe = self.resolve_application(app_name)
        if not resolved_exe:
            err_msg = f"Application '{app_name}' is not an approved or resolvable application."
            logger.warning("[APPLICATION LAUNCHER] %s", err_msg)
            return ApplicationLaunchResult(
                success=False,
                app_name=app_name,
                error_code="LAUNCH_RESOLUTION_FAILED",
                error_message=err_msg,
            )

        try:
            if sys.platform == "win32":
                # Prefer os.startfile for registered desktop applications
                try:
                    os.startfile(resolved_exe)  # type: ignore[attr-defined]
                    logger.info("[APPLICATION LAUNCHER] Successfully launched '%s' (%s) via os.startfile", app_name, resolved_exe)
                    return ApplicationLaunchResult(
                        success=True,
                        app_name=app_name,
                        executable_path=resolved_exe,
                    )
                except Exception as startfile_err:
                    logger.debug("os.startfile fallback for %s: %s", resolved_exe, startfile_err)

            # Fallback: parameterized Popen with shell=False
            proc = subprocess.Popen([resolved_exe], shell=False)
            logger.info("[APPLICATION LAUNCHER] Successfully launched '%s' (%s) with PID %d", app_name, resolved_exe, proc.pid)
            return ApplicationLaunchResult(
                success=True,
                app_name=app_name,
                executable_path=resolved_exe,
                pid=proc.pid,
            )

        except Exception as ex:
            logger.warning("[APPLICATION LAUNCHER] Launch failed for '%s' (%s): %s", app_name, resolved_exe, ex)
            return ApplicationLaunchResult(
                success=False,
                app_name=app_name,
                executable_path=resolved_exe,
                error_code="PROCESS_SPAWN_FAILED",
                error_message=str(ex),
            )
