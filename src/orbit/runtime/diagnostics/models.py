"""Data contracts and schemas for ORBIT system diagnostics and health evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DiagnosticStatus(str, Enum):
    """Normalized health and diagnostic status."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class IssueSeverity(str, Enum):
    """Severity classification for structured diagnostic issues."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class StructuredIssue(BaseModel):
    """Structured diagnostic issue or recent failure with actionable remediation."""
    issue_id: str = Field(..., description="Unique issue identifier")
    severity: IssueSeverity = Field(default=IssueSeverity.WARNING)
    title: str = Field(..., description="Short descriptive title of the issue")
    description: str = Field(..., description="Detailed explanation of what failed or is degraded")
    subsystem: str = Field(..., description="Subsystem identity associated with the issue")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    remediation: Optional[str] = Field(default=None, description="Recommended remediation step for the user")
    technical_details: Optional[str] = Field(default=None, description="Sanitized technical error message or context")


class SubsystemDiagnosticReport(BaseModel):
    """Diagnostic health report for a specific ORBIT subsystem."""
    subsystem_id: str = Field(..., description="Canonical ID: backend, gateway, websocket, execution_engine, model_runtime, safety, perception, action, desktop_shell")
    name: str = Field(..., description="Human readable display name")
    status: DiagnosticStatus = Field(default=DiagnosticStatus.UNKNOWN)
    summary: str = Field(..., description="Brief one-line summary of subsystem operational state")
    latency_ms: Optional[float] = Field(default=None, description="Subsystem response or probe latency in ms")
    details: Dict[str, Any] = Field(default_factory=dict, description="Structured truthful diagnostic metrics")
    last_checked: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SystemDiagnosticReport(BaseModel):
    """Aggregated system diagnostic report across all active ORBIT subsystems."""
    overall_status: DiagnosticStatus = Field(default=DiagnosticStatus.UNKNOWN)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    subsystems: List[SubsystemDiagnosticReport] = Field(default_factory=list)
    issues: List[StructuredIssue] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    summary_text: str = Field(default="", description="Sanitized overall diagnostic summary text")
