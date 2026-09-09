"""Unified Diagnostic and System Health evaluation service for ORBIT."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from orbit import __version__
from orbit.contracts.capabilities import (
    CapabilityHealth,
    CapabilityHealthStatus,
    CapabilityLifecycleState,
    CapabilityType,
)
from orbit.contracts.runtime import SystemState
from orbit.runtime.diagnostics.models import (
    DiagnosticStatus,
    IssueSeverity,
    StructuredIssue,
    SubsystemDiagnosticReport,
    SystemDiagnosticReport,
)

logger = logging.getLogger(__name__)


class DiagnosticService:
    """Evaluates and aggregates truthful health reports across all ORBIT subsystems."""

    def __init__(self, orchestrator: Any, session_manager: Optional[Any] = None) -> None:
        self._orchestrator = orchestrator
        self._session_manager = session_manager
        self._last_report: Optional[SystemDiagnosticReport] = None
        self._lock = asyncio.Lock()

    async def run_diagnostics(self) -> SystemDiagnosticReport:
        """Execute a deep, real-time diagnostic probe across all registered subsystems."""
        async with self._lock:
            start_time = time.perf_counter()
            subsystems: List[SubsystemDiagnosticReport] = []
            issues: List[StructuredIssue] = []

            # 1. ORBIT Backend Gateway
            backend_report, backend_issues = await self._probe_backend_gateway()
            subsystems.append(backend_report)
            issues.extend(backend_issues)

            # 2. WebSocket & Session Gateway
            ws_report, ws_issues = await self._probe_websocket_gateway()
            subsystems.append(ws_report)
            issues.extend(ws_issues)

            # 3. Orchestrator Execution Engine
            engine_report, engine_issues = await self._probe_execution_engine()
            subsystems.append(engine_report)
            issues.extend(engine_issues)

            # 4. AI Model Runtime
            model_report, model_issues = await self._probe_model_runtime()
            subsystems.append(model_report)
            issues.extend(model_issues)

            # 5. Safety & Takeover Guards
            safety_report, safety_issues = await self._probe_safety_subsystem()
            subsystems.append(safety_report)
            issues.extend(safety_issues)

            # 6. Perception & Visual Observation
            perception_report, perception_issues = await self._probe_perception_subsystem()
            subsystems.append(perception_report)
            issues.extend(perception_issues)

            # 7. Action & Input Injectors
            action_report, action_issues = await self._probe_action_subsystem()
            subsystems.append(action_report)
            issues.extend(action_issues)

            # 8. Historical Failure Issues
            history_issues = await self._collect_history_issues()
            issues.extend(history_issues)

            # Deduplicate issues by issue_id or title
            unique_issues: List[StructuredIssue] = []
            seen_titles = set()
            for iss in issues:
                if iss.title not in seen_titles:
                    unique_issues.append(iss)
                    seen_titles.add(iss.title)

            # Calculate overall system status
            overall_status = DiagnosticStatus.HEALTHY
            status_counts = {
                DiagnosticStatus.HEALTHY: 0,
                DiagnosticStatus.DEGRADED: 0,
                DiagnosticStatus.FAILED: 0,
                DiagnosticStatus.UNAVAILABLE: 0,
            }

            for sub in subsystems:
                status_counts[sub.status] = status_counts.get(sub.status, 0) + 1
                if sub.status == DiagnosticStatus.FAILED:
                    overall_status = DiagnosticStatus.FAILED
                elif sub.status == DiagnosticStatus.DEGRADED and overall_status != DiagnosticStatus.FAILED:
                    overall_status = DiagnosticStatus.DEGRADED
                elif sub.status == DiagnosticStatus.UNAVAILABLE and overall_status == DiagnosticStatus.HEALTHY:
                    overall_status = DiagnosticStatus.DEGRADED

            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            summary_text = (
                f"ORBIT v{__version__} — {len(subsystems)} subsystems evaluated in {elapsed_ms}ms. "
                f"Overall status: {overall_status.value}. "
                f"Active issues: {len(unique_issues)}."
            )

            report = SystemDiagnosticReport(
                overall_status=overall_status,
                timestamp=datetime.now(timezone.utc),
                subsystems=subsystems,
                issues=unique_issues,
                metrics={
                    "total_subsystems": len(subsystems),
                    "healthy_count": status_counts.get(DiagnosticStatus.HEALTHY, 0),
                    "degraded_count": status_counts.get(DiagnosticStatus.DEGRADED, 0),
                    "failed_count": status_counts.get(DiagnosticStatus.FAILED, 0),
                    "unavailable_count": status_counts.get(DiagnosticStatus.UNAVAILABLE, 0),
                    "elapsed_ms": elapsed_ms,
                },
                summary_text=summary_text,
            )

            self._last_report = report
            return report

    async def get_cached_or_fresh_report(self, max_age_sec: float = 3.0) -> SystemDiagnosticReport:
        """Return cached report if fresh, otherwise execute diagnostic run."""
        if self._last_report is not None:
            age = (datetime.now(timezone.utc) - self._last_report.timestamp).total_seconds()
            if age < max_age_sec:
                return self._last_report
        return await self.run_diagnostics()

    # =========================================================================
    # Individual Subsystem Probes
    # =========================================================================

    async def _probe_backend_gateway(self) -> tuple[SubsystemDiagnosticReport, List[StructuredIssue]]:
        t0 = time.perf_counter()
        issues: List[StructuredIssue] = []
        is_initialized = bool(self._orchestrator.is_initialized if hasattr(self._orchestrator, "is_initialized") else True)

        status = DiagnosticStatus.HEALTHY if is_initialized else DiagnosticStatus.DEGRADED
        if not is_initialized:
            issues.append(
                StructuredIssue(
                    issue_id="issue_backend_uninit",
                    severity=IssueSeverity.CRITICAL,
                    title="Backend Gateway Uninitialized",
                    description="The ORBIT backend core runtime has not completed initialization.",
                    subsystem="backend",
                    remediation="Restart the ORBIT backend service daemon.",
                )
            )

        latency = round((time.perf_counter() - t0) * 1000, 2)
        report = SubsystemDiagnosticReport(
            subsystem_id="backend",
            name="ORBIT Backend Gateway",
            status=status,
            summary=f"Running ORBIT core runtime v{__version__}",
            latency_ms=latency,
            details={
                "version": __version__,
                "is_initialized": is_initialized,
                "system_state": self._orchestrator.system_state.value if hasattr(self._orchestrator, "system_state") else "UNKNOWN",
            },
        )
        return report, issues

    async def _probe_websocket_gateway(self) -> tuple[SubsystemDiagnosticReport, List[StructuredIssue]]:
        t0 = time.perf_counter()
        issues: List[StructuredIssue] = []
        active_sessions_count = 0

        if self._session_manager is not None:
            try:
                active_sessions = await self._session_manager.list_active_sessions()
                active_sessions_count = len(active_sessions)
            except Exception as e:
                logger.warning("Failed to query session manager: %s", e)

        latency = round((time.perf_counter() - t0) * 1000, 2)
        report = SubsystemDiagnosticReport(
            subsystem_id="websocket",
            name="Gateway & WebSocket Stream",
            status=DiagnosticStatus.HEALTHY,
            summary=f"Active Client Sessions: {active_sessions_count}",
            latency_ms=latency,
            details={
                "active_sessions": active_sessions_count,
                "protocol_version": "1.0.0",
                "transport": "WebSocket JSON + Binary Frames",
            },
        )
        return report, issues

    async def _probe_execution_engine(self) -> tuple[SubsystemDiagnosticReport, List[StructuredIssue]]:
        t0 = time.perf_counter()
        issues: List[StructuredIssue] = []

        system_state = getattr(self._orchestrator, "system_state", SystemState.IDLE)
        is_executing = getattr(self._orchestrator, "is_task_executing", False)
        active_task_id = getattr(self._orchestrator, "active_task_id", None)

        status = DiagnosticStatus.HEALTHY
        summary = "Ready for autonomous execution"

        if system_state == SystemState.UNRESOLVED_LOCKED:
            status = DiagnosticStatus.FAILED
            summary = "Execution engine locked due to unresolved safety violation"
            issues.append(
                StructuredIssue(
                    issue_id="issue_engine_locked",
                    severity=IssueSeverity.CRITICAL,
                    title="Hardware Lockout Active",
                    description="Execution engine is in UNRESOLVED_LOCKED state following safety trip.",
                    subsystem="execution_engine",
                    remediation="Release lockout in Security & Safety tab.",
                )
            )
        elif system_state == SystemState.HUMAN_TAKEOVER_ACTIVE:
            status = DiagnosticStatus.DEGRADED
            summary = "Operator human takeover actively preempting agent"
        elif is_executing:
            summary = f"Executing task: {active_task_id or 'Active'}"
        elif system_state == SystemState.PAUSED:
            summary = "Execution engine paused"

        latency = round((time.perf_counter() - t0) * 1000, 2)
        report = SubsystemDiagnosticReport(
            subsystem_id="execution_engine",
            name="Execution Engine & Planner",
            status=status,
            summary=summary,
            latency_ms=latency,
            details={
                "system_state": system_state.value if hasattr(system_state, "value") else str(system_state),
                "is_executing": is_executing,
                "active_task_id": active_task_id,
            },
        )
        return report, issues

    async def _probe_model_runtime(self) -> tuple[SubsystemDiagnosticReport, List[StructuredIssue]]:
        t0 = time.perf_counter()
        issues: List[StructuredIssue] = []
        msm = getattr(self._orchestrator, "model_session_manager", None)

        if msm is None:
            return SubsystemDiagnosticReport(
                subsystem_id="model_runtime",
                name="AI Model Runtime",
                status=DiagnosticStatus.UNAVAILABLE,
                summary="Model session manager is not configured",
                latency_ms=0.0,
                details={"configured": False},
            ), []

        active_ctx = msm.get_active_context()
        if active_ctx is None:
            report = SubsystemDiagnosticReport(
                subsystem_id="model_runtime",
                name="AI Model Runtime",
                status=DiagnosticStatus.DEGRADED,
                summary="No active AI model selected",
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                details={"has_active_model": False},
            )
            issues.append(
                StructuredIssue(
                    issue_id="issue_no_active_model",
                    severity=IssueSeverity.WARNING,
                    title="No Active AI Model",
                    description="ORBIT does not currently have an active AI model loaded for task planning and perception.",
                    subsystem="model_runtime",
                    remediation="Select and activate a local or cloud model in the Model Manager tab.",
                )
            )
            return report, issues

        health = active_ctx.health
        is_healthy = health.is_healthy if health else True
        latency_val = health.latency_ms if health and health.latency_ms is not None else round((time.perf_counter() - t0) * 1000, 2)
        status = DiagnosticStatus.HEALTHY if is_healthy else DiagnosticStatus.FAILED

        if not is_healthy:
            issues.append(
                StructuredIssue(
                    issue_id="issue_model_unhealthy",
                    severity=IssueSeverity.CRITICAL,
                    title="Active Model Unhealthy",
                    description=f"Model '{active_ctx.model_id}' failed its health check: {health.diagnostic_message if health else 'Unknown error'}",
                    subsystem="model_runtime",
                    remediation="Verify Ollama or cloud credentials in the Model Manager.",
                    technical_details=health.diagnostic_message if health else None,
                )
            )

        prov_val = active_ctx.provider.value if hasattr(active_ctx.provider, "value") else str(active_ctx.provider)
        is_local = (
            str(prov_val).upper() in ("OLLAMA", "LM_STUDIO", "LOCAL_FILE")
            or "LOCAL" in str(prov_val).upper()
            or str(getattr(active_ctx, "runtime_kind", "")).upper() in ("LOCAL", "LOCAL_OLLAMA", "LOCAL_LM_STUDIO")
        )
        report = SubsystemDiagnosticReport(
            subsystem_id="model_runtime",
            name="AI Model Runtime",
            status=status,
            summary=f"Active: {active_ctx.display_name} ({prov_val} [{'LOCAL' if is_local else 'CLOUD'}])",
            latency_ms=latency_val,
            details={
                "model_id": active_ctx.model_id,
                "display_name": active_ctx.display_name,
                "provider": prov_val,
                "runtime_kind": active_ctx.runtime_kind.value if hasattr(active_ctx.runtime_kind, "value") else str(active_ctx.runtime_kind),
                "context_window": active_ctx.context_window,
                "is_local": is_local,
                "classification": "LOCAL" if is_local else "CLOUD",
            },
        )
        return report, issues

    async def _probe_safety_subsystem(self) -> tuple[SubsystemDiagnosticReport, List[StructuredIssue]]:
        t0 = time.perf_counter()
        issues: List[StructuredIssue] = []
        registry = getattr(self._orchestrator, "registry", None)

        if registry is None:
            return SubsystemDiagnosticReport(
                subsystem_id="safety",
                name="Safety & Human Takeover Guards",
                status=DiagnosticStatus.UNAVAILABLE,
                summary="Capability registry unavailable",
            ), []

        takeover_ready = registry.is_ready(CapabilityType.HUMAN_TAKEOVER)
        safety_ready = registry.is_ready(CapabilityType.SAFETY)
        workspace_ready = registry.is_ready(CapabilityType.WORKSPACE)

        all_ready = takeover_ready and safety_ready and workspace_ready
        status = DiagnosticStatus.HEALTHY if all_ready else DiagnosticStatus.DEGRADED

        if not all_ready:
            issues.append(
                StructuredIssue(
                    issue_id="issue_safety_degraded",
                    severity=IssueSeverity.WARNING,
                    title="Safety Adapters Degraded",
                    description=f"Takeover ready: {takeover_ready}, Safety coordinator: {safety_ready}, Workspace: {workspace_ready}",
                    subsystem="safety",
                    remediation="Verify Windows desktop hooks and admin permissions.",
                )
            )

        latency = round((time.perf_counter() - t0) * 1000, 2)
        report = SubsystemDiagnosticReport(
            subsystem_id="safety",
            name="Safety & Takeover Guards",
            status=status,
            summary="Emergency stop and human takeover guards active",
            latency_ms=latency,
            details={
                "human_takeover_ready": takeover_ready,
                "safety_coordinator_ready": safety_ready,
                "workspace_barrier_ready": workspace_ready,
            },
        )
        return report, issues

    async def _probe_perception_subsystem(self) -> tuple[SubsystemDiagnosticReport, List[StructuredIssue]]:
        t0 = time.perf_counter()
        issues: List[StructuredIssue] = []
        registry = getattr(self._orchestrator, "registry", None)

        obs_ready = registry.is_ready(CapabilityType.OBSERVATION) if registry else False
        status = DiagnosticStatus.HEALTHY if obs_ready else DiagnosticStatus.DEGRADED

        if not obs_ready:
            issues.append(
                StructuredIssue(
                    issue_id="issue_observation_unavailable",
                    severity=IssueSeverity.WARNING,
                    title="Observation Adapter Degraded",
                    description="Screen capture and window visual observation adapter is not in ready state.",
                    subsystem="perception",
                    remediation="Ensure display capture permissions are granted on Windows.",
                )
            )

        latency = round((time.perf_counter() - t0) * 1000, 2)
        report = SubsystemDiagnosticReport(
            subsystem_id="perception",
            name="Perception & Observation",
            status=status,
            summary="Screen capture and multi-modal grounding ready",
            latency_ms=latency,
            details={"observation_ready": obs_ready},
        )
        return report, issues

    async def _probe_action_subsystem(self) -> tuple[SubsystemDiagnosticReport, List[StructuredIssue]]:
        t0 = time.perf_counter()
        issues: List[StructuredIssue] = []
        registry = getattr(self._orchestrator, "registry", None)

        pointer_ready = registry.is_ready(CapabilityType.POINTER) if registry else False
        keyboard_ready = registry.is_ready(CapabilityType.KEYBOARD) if registry else False

        all_ready = pointer_ready and keyboard_ready
        status = DiagnosticStatus.HEALTHY if all_ready else DiagnosticStatus.DEGRADED

        if not all_ready:
            issues.append(
                StructuredIssue(
                    issue_id="issue_input_degraded",
                    severity=IssueSeverity.WARNING,
                    title="Input Injection Adapters Degraded",
                    description=f"Pointer driver ready: {pointer_ready}, Keyboard driver ready: {keyboard_ready}",
                    subsystem="action",
                    remediation="Verify Windows user input injection privileges.",
                )
            )

        latency = round((time.perf_counter() - t0) * 1000, 2)
        report = SubsystemDiagnosticReport(
            subsystem_id="action",
            name="Input & Action Injectors",
            status=status,
            summary="Hardware input simulation and fail-closed locks armed",
            latency_ms=latency,
            details={
                "pointer_ready": pointer_ready,
                "keyboard_ready": keyboard_ready,
            },
        )
        return report, issues

    async def _collect_history_issues(self) -> List[StructuredIssue]:
        issues: List[StructuredIssue] = []
        store = getattr(self._orchestrator, "history_store", None)
        if store is not None:
            try:
                failed_records = await store.list_records(limit=3, status_filter="FAILED")
                for r in failed_records:
                    issues.append(
                        StructuredIssue(
                            issue_id=f"fail_{r.execution_id[:8]}",
                            severity=IssueSeverity.WARNING,
                            title=f"Task Failed: {r.goal[:40]}..." if len(r.goal) > 40 else f"Task Failed: {r.goal}",
                            description=f"Execution {r.execution_id[:8]} encountered a terminal failure. Reason: {r.failure_reason or 'Unknown'}",
                            subsystem="execution_engine",
                            timestamp=r.completed_at or r.started_at,
                            remediation="Inspect step logs in the Activity & History tab.",
                            technical_details=r.failure_reason,
                        )
                    )
            except Exception as e:
                logger.warning("Failed to collect failed execution records: %s", e)
        return issues
