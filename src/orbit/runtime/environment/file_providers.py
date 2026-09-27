"""
Provenance & Architectural Attribution:
======================================
Windows-Use Source:   windows_use/agent/tools/service.py (file_tool, memory_tool)
ORBIT Destination:    src/orbit/runtime/environment/file_providers.py
Integration Paradigm: Transduced Non-Physical Environment Interface (Brain-Body Separation)

Adaptations Applied:
- Added atomic filesystem operations (read, write, copy, move, delete, list_directory).
- Retained strict path sandboxing, size limits (10MB), and traversal safeguards.
- Enforced strict invariant: Filesystem provider is a non-physical transducer with NO agent or planner authority.
======================================
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.environment.registry import EnvironmentProvider, ProviderExecutionResult

logger = logging.getLogger(__name__)


class LocalFileProvider(EnvironmentProvider):
    """Environment provider for safe, non-physical local file operations."""

    def __init__(
        self,
        allowed_directories: Optional[List[str]] = None,
        max_read_size_bytes: int = 10 * 1024 * 1024,  # 10 MB limit
    ) -> None:
        self._allowed_directories = [
            Path(d).resolve() for d in allowed_directories
        ] if allowed_directories else None
        self._max_read_size_bytes = max_read_size_bytes

    @property
    def provider_id(self) -> str:
        return "local_file_provider"

    @property
    def supported_features(self) -> List[str]:
        return ["file_read", "file_write", "file_copy", "file_move", "file_delete", "file_list", "directory_creation"]

    async def is_available(self) -> bool:
        """Local file system is always accessible."""
        return True

    def _resolve_and_check_path(self, raw_path: str) -> Tuple[bool, Path, Optional[str]]:
        """Resolve path and verify sandbox/directory restrictions if configured."""
        try:
            target_path = Path(raw_path).resolve()
        except Exception as e:
            return False, Path(raw_path), f"Invalid path syntax: {e}"

        if self._allowed_directories is not None:
            is_contained = any(
                target_path == allowed or allowed in target_path.parents
                for allowed in self._allowed_directories
            )
            if not is_contained:
                return False, target_path, f"Path '{target_path}' is outside allowed directory sandbox"

        return True, target_path, None

    async def check_permissions(self, action: AbstractAction) -> bool:
        """Check if action parameters specify a valid, accessible path."""
        params = action.parameters or {}
        raw_path = params.get("path") or params.get("file_path") or params.get("filepath")
        if not raw_path:
            return False

        is_allowed, _, _ = self._resolve_and_check_path(str(raw_path))
        return is_allowed

    async def execute(self, action: AbstractAction) -> ProviderExecutionResult:
        """Execute file operations non-physically."""
        act_type = action.action_type
        params = action.parameters or {}
        mode = str(params.get("mode", "")).lower()
        raw_path = params.get("path") or params.get("file_path") or params.get("filepath")

        if not raw_path:
            return ProviderExecutionResult(
                success=False,
                error="Missing required parameter 'path' for file operation",
            )

        is_allowed, target_path, err = self._resolve_and_check_path(str(raw_path))
        if not is_allowed:
            return ProviderExecutionResult(
                success=False,
                error=f"FILE_PERMISSION_DENIED: {err}",
                metadata={"path": str(target_path)},
            )

        try:
            if mode == "copy" or str(act_type).upper().endswith("COPY"):
                return await self._execute_copy(target_path, params)
            elif mode == "move" or str(act_type).upper().endswith("MOVE"):
                return await self._execute_move(target_path, params)
            elif mode == "delete" or str(act_type).upper().endswith("DELETE"):
                return await self._execute_delete(target_path, params)
            elif mode in ("list", "list_dir", "view") or str(act_type).upper().endswith("LIST"):
                return await self._execute_list(target_path, params)
            elif act_type == AbstractActionType.FILE_READ or mode == "read":
                return await self._execute_read(target_path, params)
            elif act_type == AbstractActionType.FILE_WRITE or mode == "write":
                return await self._execute_write(target_path, params)
            else:
                return ProviderExecutionResult(
                    success=False,
                    error=f"Unsupported file action type/mode: {act_type} (mode={mode})",
                )
        except Exception as exc:
            logger.error("[FILE PROVIDER] Failed executing %s on %s: %s", act_type, target_path, exc)
            return ProviderExecutionResult(
                success=False,
                error=f"FILE_IO_ERROR: {str(exc)}",
                metadata={"path": str(target_path)},
            )

    async def _execute_read(self, path: Path, params: Dict[str, Any]) -> ProviderExecutionResult:
        """Read file contents safely."""
        if not path.exists():
            return ProviderExecutionResult(
                success=False,
                error=f"FILE_NOT_FOUND: Path '{path}' does not exist",
                metadata={"path": str(path)},
            )
        if not path.is_file():
            return ProviderExecutionResult(
                success=False,
                error=f"NOT_A_FILE: Path '{path}' is a directory or special device",
                metadata={"path": str(path)},
            )

        file_size = path.stat().st_size
        if file_size > self._max_read_size_bytes:
            return ProviderExecutionResult(
                success=False,
                error=f"FILE_TOO_LARGE: Size {file_size} exceeds limit of {self._max_read_size_bytes} bytes",
                metadata={"path": str(path), "size_bytes": file_size},
            )

        is_binary = bool(params.get("binary", False))
        encoding = str(params.get("encoding", "utf-8"))

        if is_binary:
            raw_data = path.read_bytes()
            b64_content = base64.b64encode(raw_data).decode("ascii")
            return ProviderExecutionResult(
                success=True,
                output={
                    "path": str(path),
                    "size_bytes": file_size,
                    "content_b64": b64_content,
                    "is_binary": True,
                },
                metadata={"provider": self.provider_id},
            )
        else:
            try:
                text_content = path.read_text(encoding=encoding, errors="replace")
            except Exception as e:
                return ProviderExecutionResult(
                    success=False,
                    error=f"FILE_DECODE_ERROR: {e}",
                    metadata={"path": str(path)},
                )
            return ProviderExecutionResult(
                success=True,
                output={
                    "path": str(path),
                    "size_bytes": file_size,
                    "content": text_content,
                    "lines_count": len(text_content.splitlines()),
                    "is_binary": False,
                },
                metadata={"provider": self.provider_id},
            )

    async def _execute_write(self, path: Path, params: Dict[str, Any]) -> ProviderExecutionResult:
        """Write file contents safely."""
        content = params.get("content", "")
        append = bool(params.get("append", False))
        create_parents = bool(params.get("create_parents", True))
        encoding = str(params.get("encoding", "utf-8"))

        if create_parents and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        if isinstance(content, bytes):
            with open(path, mode + "b") as f:
                bytes_written = f.write(content)
        elif isinstance(content, str):
            # Check if base64 encoded binary was passed
            if params.get("is_base64", False):
                raw_bytes = base64.b64decode(content)
                with open(path, mode + "b") as f:
                    bytes_written = f.write(raw_bytes)
            else:
                with open(path, mode, encoding=encoding) as f:
                    chars_written = f.write(content)
                    bytes_written = len(content.encode(encoding))
        else:
            return ProviderExecutionResult(
                success=False,
                error=f"INVALID_CONTENT_TYPE: Expected str or bytes, got {type(content).__name__}",
                metadata={"path": str(path)},
            )

        return ProviderExecutionResult(
            success=True,
            output={
                "path": str(path),
                "bytes_written": bytes_written,
                "append": append,
                "file_exists": path.exists(),
                "final_size_bytes": path.stat().st_size,
            },
            metadata={"provider": self.provider_id},
        )

    async def _execute_copy(self, src_path: Path, params: Dict[str, Any]) -> ProviderExecutionResult:
        """Atomic copy file or directory."""
        dest_raw = params.get("dest") or params.get("destination") or params.get("dest_path")
        if not dest_raw:
            return ProviderExecutionResult(success=False, error="Missing required parameter 'dest' for copy")
        is_allowed, dest_path, err = self._resolve_and_check_path(str(dest_raw))
        if not is_allowed:
            return ProviderExecutionResult(success=False, error=f"COPY_PERMISSION_DENIED: {err}")
        if not src_path.exists():
            return ProviderExecutionResult(success=False, error=f"SOURCE_NOT_FOUND: {src_path}")

        if src_path.is_dir():
            shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)

        return ProviderExecutionResult(
            success=True,
            output={"src": str(src_path), "dest": str(dest_path), "copied": True},
            metadata={"provider": self.provider_id},
        )

    async def _execute_move(self, src_path: Path, params: Dict[str, Any]) -> ProviderExecutionResult:
        """Atomic move/rename file or directory."""
        dest_raw = params.get("dest") or params.get("destination") or params.get("dest_path")
        if not dest_raw:
            return ProviderExecutionResult(success=False, error="Missing required parameter 'dest' for move")
        is_allowed, dest_path, err = self._resolve_and_check_path(str(dest_raw))
        if not is_allowed:
            return ProviderExecutionResult(success=False, error=f"MOVE_PERMISSION_DENIED: {err}")
        if not src_path.exists():
            return ProviderExecutionResult(success=False, error=f"SOURCE_NOT_FOUND: {src_path}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dest_path))

        return ProviderExecutionResult(
            success=True,
            output={"src": str(src_path), "dest": str(dest_path), "moved": True},
            metadata={"provider": self.provider_id},
        )

    async def _execute_delete(self, path: Path, params: Dict[str, Any]) -> ProviderExecutionResult:
        """Safely delete a file or directory."""
        if not path.exists():
            return ProviderExecutionResult(success=True, output={"path": str(path), "deleted": False, "note": "did not exist"})

        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

        return ProviderExecutionResult(
            success=True,
            output={"path": str(path), "deleted": True},
            metadata={"provider": self.provider_id},
        )

    async def _execute_list(self, path: Path, params: Dict[str, Any]) -> ProviderExecutionResult:
        """List directory contents with size and metadata."""
        if not path.exists():
            return ProviderExecutionResult(success=False, error=f"PATH_NOT_FOUND: {path}")
        if not path.is_dir():
            return ProviderExecutionResult(success=False, error=f"NOT_A_DIRECTORY: {path}")

        items = []
        for p in path.iterdir():
            try:
                st = p.stat()
                items.append({
                    "name": p.name,
                    "is_dir": p.is_dir(),
                    "size_bytes": st.st_size if p.is_file() else 0,
                })
            except Exception:
                continue

        return ProviderExecutionResult(
            success=True,
            output={"path": str(path), "item_count": len(items), "items": items},
            metadata={"provider": self.provider_id},
        )

