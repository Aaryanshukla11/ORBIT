"""Independent multi-tier verification engine for benchmark tasks."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from benchmark.schema import BenchmarkTask, ExpectedDeliverable, TaskExpectation
from orbit.runtime.perception.windows import Win32WindowObserver


class VerificationResult(BaseModel):
    """Result of independent postcondition verification."""
    is_passed: bool = False
    goal_verified: bool = False
    artifact_verified: bool = False
    failure_reason: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class TaskOutcomeVerifier:
    """Independent ground-truth evaluator verifying real OS state without LLM trust."""

    # Magic byte signatures for common formats
    MAGIC_BYTES = {
        "png": b"\x89PNG\r\n\x1a\n",
        "jpeg": b"\xff\xd8\xff",
        "jpg": b"\xff\xd8\xff",
        "pdf": b"%PDF-",
        "zip": b"PK\x03\x04",
        "bmp": b"BM",
    }

    def __init__(self, window_observer: Optional[Win32WindowObserver] = None) -> None:
        self.window_observer = window_observer or Win32WindowObserver()

    async def verify_task_outcome(
        self,
        task: BenchmarkTask,
        workspace_dir: Optional[Path] = None,
        scratchpad_dir: Optional[Path] = None,
    ) -> VerificationResult:
        """Evaluate task postconditions against live OS and physical filesystem."""
        exp: TaskExpectation = task.expectations
        details: Dict[str, Any] = {}
        failure_reasons: List[str] = []

        # 1. Window / Process State Verification
        fg_window, windows = self.window_observer.observe_windows()

        details["visible_windows_count"] = len(windows)
        details["foreground_window_title"] = getattr(fg_window, "title", getattr(fg_window, "window_title", None)) if fg_window else None

        # Check required window title
        if exp.expected_window_title:
            matched_title = any(
                exp.expected_window_title.lower() in getattr(w, "title", getattr(w, "window_title", "")).lower()
                for w in windows
            )
            details["window_title_match"] = matched_title
            if not matched_title:
                failure_reasons.append(
                    f"Expected window title '{exp.expected_window_title}' not found in open windows."
                )

        # Check required process name
        if exp.expected_process_name:
            matched_proc = any(
                exp.expected_process_name.lower() in (w.process_name or "").lower()
                for w in windows
            )
            details["process_name_match"] = matched_proc
            if not matched_proc:
                failure_reasons.append(
                    f"Expected process '{exp.expected_process_name}' is not running."
                )

        # Check app closed requirement
        if exp.require_app_closed and exp.expected_process_name:
            still_open = any(
                exp.expected_process_name.lower() in (w.process_name or "").lower()
                for w in windows
            )
            details["app_closed_verified"] = not still_open
            if still_open:
                failure_reasons.append(
                    f"Application '{exp.expected_process_name}' was expected to be closed, but remains running."
                )

        goal_verified = (len(failure_reasons) == 0)

        # 2. Physical File Artifact Verification
        artifact_verified = True
        if exp.expected_deliverable:
            art_res, art_reason, art_details = self._verify_artifact(
                exp.expected_deliverable,
                workspace_dir=workspace_dir,
                scratchpad_dir=scratchpad_dir,
            )
            details["artifact_details"] = art_details
            artifact_verified = art_res
            if not art_res:
                failure_reasons.append(f"Artifact verification failed: {art_reason}")

        overall_passed = goal_verified and artifact_verified

        return VerificationResult(
            is_passed=overall_passed,
            goal_verified=goal_verified,
            artifact_verified=artifact_verified,
            failure_reason=" | ".join(failure_reasons) if failure_reasons else None,
            details=details,
        )

    def _verify_artifact(
        self,
        deliverable: ExpectedDeliverable,
        workspace_dir: Optional[Path] = None,
        scratchpad_dir: Optional[Path] = None,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Verify presence, non-zero size, magic bytes, and checksum of a file artifact."""
        raw_path = deliverable.file_path
        details: Dict[str, Any] = {"expected_path": raw_path}

        # Resolve candidate locations
        candidate_paths: List[Path] = []
        p = Path(raw_path)
        if p.is_absolute():
            candidate_paths.append(p)
        else:
            if scratchpad_dir:
                candidate_paths.append(scratchpad_dir / raw_path)
            if workspace_dir:
                candidate_paths.append(workspace_dir / raw_path)
            desktop_dir = Path.home() / "Desktop"
            candidate_paths.append(desktop_dir / raw_path)
            candidate_paths.append(Path.cwd() / raw_path)

        target_file: Optional[Path] = None
        for cand in candidate_paths:
            if cand.exists() and cand.is_file():
                target_file = cand
                break

        if not target_file:
            return False, f"File not found in any candidate location: {[str(c) for c in candidate_paths]}", details

        details["resolved_path"] = str(target_file)
        file_size = target_file.stat().st_size
        details["size_bytes"] = file_size

        # 1. Size Check
        if file_size < deliverable.min_size_bytes:
            return False, f"File size ({file_size} bytes) < min expected ({deliverable.min_size_bytes} bytes)", details

        raw_bytes = target_file.read_bytes()

        # 2. Magic Bytes Check
        fmt = deliverable.format.lower()
        if fmt in self.MAGIC_BYTES:
            expected_magic = self.MAGIC_BYTES[fmt]
            if not raw_bytes.startswith(expected_magic):
                return False, f"File header magic bytes mismatch for format '{fmt}'", details
        elif deliverable.magic_bytes_hex:
            expected_magic = bytes.fromhex(deliverable.magic_bytes_hex)
            if not raw_bytes.startswith(expected_magic):
                return False, f"File header magic bytes mismatch: expected {deliverable.magic_bytes_hex}", details

        # 3. Content Substring Check (Text)
        if deliverable.expected_content_substr:
            try:
                text_content = raw_bytes.decode("utf-8", errors="replace")
                if deliverable.expected_content_substr not in text_content:
                    return False, f"Expected text substring '{deliverable.expected_content_substr}' not found in file", details
            except Exception as e:
                return False, f"Failed to decode text file: {e}", details

        # 4. Checksum Check
        if deliverable.expected_checksum_sha256:
            actual_sha = hashlib.sha256(raw_bytes).hexdigest()
            details["sha256"] = actual_sha
            if actual_sha.lower() != deliverable.expected_checksum_sha256.lower():
                return False, f"SHA256 mismatch (Expected: {deliverable.expected_checksum_sha256}, Actual: {actual_sha})", details

        return True, None, details
