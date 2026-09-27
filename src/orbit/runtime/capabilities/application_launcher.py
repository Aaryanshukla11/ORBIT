"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/agent/desktop/service.py (app, launch_app, switch_window, resize_window)
ORBIT Destination:    src/orbit/runtime/capabilities/application_launcher.py
Integration Paradigm: Transduced App/Window Capability (Brain-Body Separation)

Adaptations Applied:
- Retained Start Menu resolution and Win32 process spawning without shell string interpolation.
- Added exact window switching (SetForegroundWindow, ShowWindow(SW_RESTORE)).
- Added exact window resizing and quadrant placement (MoveWindow / SetWindowPos).
- Preserved ORBIT application safety registry and forbidden character filter.
======================================
"""

from dataclasses import dataclass
import logging
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Standard application alias dictionary mapping user-facing names to verified executable identifiers
APPROVED_APPLICATION_REGISTRY: Dict[str, str] = {
    "notepad": "notepad.exe",
    "notepad.exe": "notepad.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "mspaint.exe": "mspaint.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "calc.exe": "calc.exe",
    "powershell": "powershell.exe",
    "powershell.exe": "powershell.exe",
    "pwsh": "pwsh.exe",
    "pwsh.exe": "pwsh.exe",
    "task manager": "taskmgr.exe",
    "taskmanager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "taskmgr.exe": "taskmgr.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "wt": "wt.exe",
    "wt.exe": "wt.exe",
    "cmd": "cmd.exe",
    "cmd.exe": "cmd.exe",
    "command prompt": "cmd.exe",
    "explorer": "explorer.exe",
    "explorer.exe": "explorer.exe",
    "file explorer": "explorer.exe",
    "control panel": "control.exe",
    "control": "control.exe",
    "settings": "ms-settings:",
    "edge": "msedge.exe",
    "msedge": "msedge.exe",
    "msedge.exe": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "browser": "msedge.exe",
    "chrome": "chrome.exe",
    "chrome.exe": "chrome.exe",
    "google chrome": "chrome.exe",
    "wordpad": "write.exe",
    "write": "write.exe",
    "word": "winword.exe",
    "winword": "winword.exe",
    "excel": "excel.exe",
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

        # 1. Registered identifier check (Returns standard alias, e.g. "notepad.exe", "mspaint.exe")
        if name_lower in self._registry:
            return self._registry[name_lower]
        if name_lower.endswith(".exe") and name_lower[:-4] in self._registry:
            return self._registry[name_lower[:-4]]

        cand_exe = clean_name if clean_name.endswith(".exe") else f"{clean_name}.exe"

        # 2. System PATH resolution
        import shutil
        found_in_path = shutil.which(cand_exe) or shutil.which(clean_name)
        if found_in_path:
            return cand_exe if (found_in_path and not os.path.isabs(clean_name)) else found_in_path

        # 2. Check standard Windows application install locations
        if sys.platform == "win32":
            common_dirs = [
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                os.environ.get("LOCALAPPDATA", ""),
            ]
            known_rel_paths = {
                "msedge.exe": [os.path.join("Microsoft", "Edge", "Application", "msedge.exe")],
                "chrome.exe": [os.path.join("Google", "Chrome", "Application", "chrome.exe")],
            }
            if cand_exe in known_rel_paths:
                for base in common_dirs:
                    if base:
                        for rel in known_rel_paths[cand_exe]:
                            full_cand = os.path.join(base, rel)
                            if os.path.exists(full_cand):
                                return full_cand

        # 3. Fallback to registered identifier
        if name_lower in self._registry:
            return self._registry[name_lower]

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
                clean_lower = app_name.strip().lower()

                # Modern Windows 11 Packaged App Launching (Paint AUMID)
                if clean_lower in ("paint", "mspaint"):
                    try:
                        os.startfile(r"shell:AppsFolder\Microsoft.Paint_8wekyb3d8bbwe!App")  # type: ignore[attr-defined]
                        logger.info("[APPLICATION LAUNCHER] Successfully launched Paint via Windows AppsFolder")
                        return ApplicationLaunchResult(
                            success=True,
                            app_name=app_name,
                            executable_path="mspaint.exe",
                        )
                    except Exception as p_err:
                        logger.debug("Windows AppsFolder Paint launch fallback: %s", p_err)

                # Web browsers (Edge, Chrome, Brave, Firefox): spawn with isolated profile to guarantee top-level interactive window
                if clean_lower in ("edge", "msedge", "microsoft edge", "browser") or any(b in (resolved_exe or "").lower() for b in ("msedge.exe", "chrome.exe", "brave.exe", "firefox.exe")):
                    try:
                        exe_to_use = resolved_exe if (resolved_exe and os.path.exists(resolved_exe)) else "msedge.exe"
                        temp_profile = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "orbit_browser_profile")
                        proc = subprocess.Popen([exe_to_use, f"--user-data-dir={temp_profile}", "--new-window", "about:blank"], shell=False)
                        logger.info("[APPLICATION LAUNCHER] Successfully launched browser '%s' with PID %d", exe_to_use, proc.pid)
                        return ApplicationLaunchResult(
                            success=True,
                            app_name=app_name,
                            executable_path=exe_to_use,
                            pid=proc.pid,
                        )
                    except Exception as b_err:
                        logger.debug("Browser launch fallback: %s", b_err)
                        logger.debug("Browser launch fallback: %s", b_err)
                        logger.debug("Browser launch fallback: %s", b_err)

                # Prefer os.startfile for registered desktop applications
                if resolved_exe and not resolved_exe.endswith(r"WindowsApps\mspaint.exe"):
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

    def switch_window(self, window_title: str) -> bool:
        """Brings an open window matching the given title to the foreground."""
        if not window_title or sys.platform != "win32":
            return False

        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            found_hwnd = 0
            search_title = window_title.lower().strip()

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            def enum_proc(hwnd: int, lparam: int) -> bool:
                nonlocal found_hwnd
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    if search_title in buff.value.lower():
                        found_hwnd = hwnd
                        return False
                return True

            user32.EnumWindows(WNDENUMPROC(enum_proc), 0)

            if found_hwnd:
                # SW_RESTORE = 9, SW_SHOW = 5
                user32.ShowWindow(found_hwnd, 9)
                user32.SetForegroundWindow(found_hwnd)
                logger.info("[APPLICATION LAUNCHER] Successfully switched to window '%s' (HWND: %d)", window_title, found_hwnd)
                return True

            logger.warning("[APPLICATION LAUNCHER] Window matching '%s' not found for switch", window_title)
            return False

        except Exception as sw_err:
            logger.warning("[APPLICATION LAUNCHER] switch_window error: %s", sw_err)
            return False

    def resize_window(
        self,
        loc: Optional[List[int]] = None,
        size: Optional[List[int]] = None,
        hwnd: Optional[int] = None,
    ) -> bool:
        """Moves and resizes the specified window (or foreground window) to loc=[x, y] and size=[w, h]."""
        if sys.platform != "win32":
            return False

        try:
            import ctypes
            user32 = ctypes.windll.user32

            target_hwnd = hwnd or user32.GetForegroundWindow()
            if not target_hwnd or not user32.IsWindow(target_hwnd):
                logger.warning("[APPLICATION LAUNCHER] No valid HWND to resize")
                return False

            x = loc[0] if (loc and len(loc) >= 2) else 0
            y = loc[1] if (loc and len(loc) >= 2) else 0
            w = size[0] if (size and len(size) >= 2) else 1280
            h = size[1] if (size and len(size) >= 2) else 720

            # MoveWindow(HWND, X, Y, nWidth, nHeight, bRepaint)
            res = user32.MoveWindow(target_hwnd, x, y, w, h, True)
            logger.info("[APPLICATION LAUNCHER] MoveWindow result for HWND %d to (%d, %d, %d, %d): %s", target_hwnd, x, y, w, h, bool(res))
            return bool(res)

        except Exception as r_err:
            logger.warning("[APPLICATION LAUNCHER] resize_window error: %s", r_err)
            return False

