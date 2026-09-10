"""Hardened Shell Environment Provider enforcing Zero Physical OS Bypass.

INVARIANT:
Shell execution is strictly a non-physical environment interface (e.g. for CLI inspection,
data transformation, headless tool execution). Under NO circumstances may shell commands be
used as a backdoor to spawn GUI applications, dispatch keystrokes/mouse events, or manipulate
desktop windows. All physical execution is the exclusive authority of PrimitiveExecutionController.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from orbit.runtime.agent.contracts import AbstractAction
from orbit.runtime.environment.registry import EnvironmentProvider, ProviderExecutionResult

logger = logging.getLogger(__name__)


class ShellSecurityViolation(Exception):
    """Raised when a shell command attempts a physical OS bypass or dangerous operation."""
    pass


class RestrictedShellPolicy:
    """Security policy enforcing zero physical OS bypass and non-physical shell execution."""

    # Prohibited GUI executables that would spawn an interactive window or app
    FORBIDDEN_GUI_APPS: Set[str] = {
        "notepad", "notepad.exe",
        "calc", "calc.exe",
        "mspaint", "mspaint.exe",
        "explorer", "explorer.exe",
        "winword", "winword.exe",
        "excel", "excel.exe",
        "powerpnt", "powerpnt.exe",
        "chrome", "chrome.exe",
        "msedge", "msedge.exe",
        "firefox", "firefox.exe",
        "cmd.exe /c start",
        "start-process",
        "start",
    }

    # Prohibited UI automation / desktop interaction keywords
    FORBIDDEN_UI_KEYWORDS: Set[str] = {
        "sendkeys",
        "system.windows.forms.sendkeys",
        "wscript.shell",
        "sendinput",
        "mouse_event",
        "keybd_event",
        "show-command",
        "out-gridview",
        "appactivate",
        "msgbox",
        "system.windows",
        "system.drawing",
        "presentationframework",
        "showdialog",
        "messagebox",
    }

    # Prohibited indirect launchers and script hosts (Phase 0 Rule #10)
    FORBIDDEN_INDIRECT_EXEC: Set[str] = {
        "wscript", "wscript.exe",
        "cscript", "cscript.exe",
        "mshta", "mshta.exe",
        "rundll32", "rundll32.exe",
        "regsvr32", "regsvr32.exe",
        "certutil", "certutil.exe",
        "schtasks", "schtasks.exe",
        "bitsadmin", "bitsadmin.exe",
    }

    # Prohibited dynamic evaluation, encoded commands, process spawning, command substitution
    FORBIDDEN_DYNAMIC_PATTERNS: List[re.Pattern] = [
        re.compile(r"(?:\b|^)(?:invoke-expression|iex|invoke-command|icm)\b", re.IGNORECASE),
        re.compile(r"(?:\b|^)(?:start-process|start-job)\b", re.IGNORECASE),
        re.compile(r"\bwmic\s+process\s+call\s+create\b", re.IGNORECASE),
        re.compile(r"-(?:enc|encodedcommand)\b", re.IGNORECASE),
        re.compile(r"frombase64string", re.IGNORECASE),
        re.compile(r"\$\(.*?\)", re.IGNORECASE),  # subshell command substitution
    ]

    # Prohibited destructive system commands
    FORBIDDEN_DESTRUCTIVE_COMMANDS: Set[str] = {
        "format",
        "diskpart",
        "bcdedit",
        "shutdown",
        "stop-computer",
        "restart-computer",
        "reg delete",
    }

    def __init__(
        self,
        allowlist: Optional[List[str]] = None,
        block_arbitrary_shell: bool = False,
    ) -> None:
        self._allowlist = [cmd.lower().strip() for cmd in allowlist] if allowlist else None
        self._block_arbitrary_shell = block_arbitrary_shell

    def validate_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate whether a command is safe and strictly non-physical."""
        if not command or not command.strip():
            return False, "Command cannot be empty"

        cleaned = command.strip().lower()

        # If arbitrary shell is blocked and an allowlist is provided, must match allowlist prefix
        if self._allowlist is not None:
            matches_allowlist = any(
                cleaned == allowed or cleaned.startswith(allowed + " ")
                for allowed in self._allowlist
            )
            if not matches_allowlist:
                return False, f"COMMAND_NOT_PERMITTED: Command '{command}' is not in the approved allowlist"

        # Check for prohibited GUI-spawning invocations (Zero Physical OS Bypass)
        for gui_app in self.FORBIDDEN_GUI_APPS:
            # Match word boundary or prefix
            pattern = rf"(?:\b|^){re.escape(gui_app)}(?:\b|$)"
            if re.search(pattern, cleaned):
                return False, (
                    f"COMMAND_NOT_PERMITTED: Physical OS bypass attempt. "
                    f"GUI-spawning command '{gui_app}' is prohibited in environment shell. "
                    f"Physical application launch must route through LAUNCH_APPLICATION primitive."
                )

        # Check for UI automation / SendKeys backdoors
        for ui_kw in self.FORBIDDEN_UI_KEYWORDS:
            if ui_kw in cleaned:
                return False, (
                    f"COMMAND_NOT_PERMITTED: Physical OS bypass attempt. "
                    f"UI automation pattern '{ui_kw}' is prohibited in environment shell. "
                    f"Physical interaction must route through canonical primitives."
                )

        # Check for indirect executable launching and script hosts (Phase 0 Rule #10)
        for indirect_bin in self.FORBIDDEN_INDIRECT_EXEC:
            pattern = rf"(?:\b|^){re.escape(indirect_bin)}(?:\b|$)"
            if re.search(pattern, cleaned):
                return False, (
                    f"COMMAND_NOT_PERMITTED: Indirect execution bypass attempt. "
                    f"Binary/script host '{indirect_bin}' is prohibited in environment shell."
                )

        # Check for dynamic evaluation, encoded PowerShell, and command substitution
        for dyn_pat in self.FORBIDDEN_DYNAMIC_PATTERNS:
            if dyn_pat.search(cleaned):
                return False, (
                    f"COMMAND_NOT_PERMITTED: Security policy violation. "
                    f"Dynamic evaluation, subshell substitution, or encoded execution detected."
                )

        # Check for destructive system commands
        for dest_cmd in self.FORBIDDEN_DESTRUCTIVE_COMMANDS:
            pattern = rf"(?:\b|^){re.escape(dest_cmd)}(?:\b|$)"
            if re.search(pattern, cleaned):
                return False, f"COMMAND_NOT_PERMITTED: Destructive command '{dest_cmd}' blocked by safety policy."

        # Check for dangerous root-wiping patterns
        if re.search(r"(?:rmdir|del|rm)\s+.*[/\\](?:q\s+|s\s+)*[c-zC-Z]:[/\\]", cleaned):
            return False, "COMMAND_NOT_PERMITTED: Root filesystem deletion pattern blocked."

        return True, None


class ShellExecutionProvider(EnvironmentProvider):
    """Hardened environment provider executing verified non-physical shell commands."""

    def __init__(
        self,
        policy: Optional[RestrictedShellPolicy] = None,
        default_timeout_seconds: float = 30.0,
    ) -> None:
        self._policy = policy or RestrictedShellPolicy()
        self._default_timeout = default_timeout_seconds

    @property
    def provider_id(self) -> str:
        return "restricted_shell_provider"

    @property
    def supported_features(self) -> List[str]:
        return ["headless_cli", "non_physical", "stdout_capture", "timeout_enforced"]

    async def is_available(self) -> bool:
        """Shell provider is available on standard operating systems."""
        return True

    async def check_permissions(self, action: AbstractAction) -> bool:
        """Check if action command adheres to non-physical safety policy."""
        cmd = self._extract_command(action)
        if not cmd:
            return False
        is_safe, _ = self._policy.validate_command(cmd)
        return is_safe

    def _extract_command(self, action: AbstractAction) -> Optional[str]:
        """Extract shell command string from action parameters."""
        params = action.parameters or {}
        cmd = params.get("command") or params.get("cmd") or params.get("script")
        return str(cmd).strip() if cmd else None

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        """Execute a non-physical shell command under strict security boundaries."""
        cmd = self._extract_command(action)
        if not cmd:
            return ProviderExecutionResult(
                success=False,
                error="COMMAND_NOT_PERMITTED: Missing required 'command' parameter in action",
            )

        # Enforce security validation before invoking any subprocess
        is_safe, violation_reason = self._policy.validate_command(cmd)
        if not is_safe:
            logger.warning(
                "[RESTRICTED SHELL] Command rejected by policy: %s (Reason: %s)",
                cmd, violation_reason,
            )
            return ProviderExecutionResult(
                success=False,
                error=violation_reason or "COMMAND_NOT_PERMITTED: Command rejected by safety policy",
                metadata={"command": cmd, "policy_violation": True},
            )

        timeout = float(action.parameters.get("timeout_seconds", self._default_timeout))

        # Prepare subprocess creation flags on Windows to prevent console window popping up
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        logger.info("[RESTRICTED SHELL] Executing verified non-physical command: %s", cmd)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return ProviderExecutionResult(
                    success=False,
                    error=f"SHELL_TIMEOUT: Command exceeded timeout of {timeout} seconds",
                    metadata={"command": cmd, "timeout": True},
                )

            stdout_text = stdout_data.decode("utf-8", errors="replace")
            stderr_text = stderr_data.decode("utf-8", errors="replace")
            exit_code = proc.returncode

            return ProviderExecutionResult(
                success=(exit_code == 0),
                output={
                    "command": cmd,
                    "exit_code": exit_code,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                },
                error=stderr_text if exit_code != 0 else None,
                metadata={
                    "provider": self.provider_id,
                    "exit_code": exit_code,
                    "zero_physical_bypass_enforced": True,
                },
            )

        except Exception as exc:
            logger.error("[RESTRICTED SHELL] Execution failed for command '%s': %s", cmd, exc, exc_info=True)
            return ProviderExecutionResult(
                success=False,
                error=f"SHELL_EXECUTION_ERROR: {str(exc)}",
                metadata={"command": cmd},
            )
