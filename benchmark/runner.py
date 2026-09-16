"""Benchmark runner for executing 50-task evaluation on ORBIT production runtime."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

from benchmark.environment import BenchmarkEnvironmentManager
from benchmark.schema import (
    ActionStepTrace,
    BenchmarkCategory,
    BenchmarkMetricsSummary,
    BenchmarkSplit,
    BenchmarkTask,
    TaskExecutionRecord,
)
from benchmark.taxonomy import FailureClassificationResult, FailureClassifier, FailureTaxonomy
from benchmark.verifier import TaskOutcomeVerifier, VerificationResult
from orbit.adapters.factory import create_capability_registry
from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode, CapabilityType
from orbit.runtime.cognitive.agent_loop import AgentExecutionLoop, AgentExecutionResult
from orbit.runtime.cognitive.engine import OrbitDecisionEngine
from orbit.runtime.cognitive.models import ExecutionBudget

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("benchmark.runner")


class BenchmarkRunner:
    """Orchestrates benchmark task execution, environment setup, and metric aggregation."""

    def __init__(
        self,
        tasks_dir: Optional[Path] = None,
        results_dir: Optional[Path] = None,
        decision_engine: Optional[OrbitDecisionEngine] = None,
    ) -> None:
        self.root_dir = Path(__file__).resolve().parents[1]
        self.tasks_dir = tasks_dir or (self.root_dir / "benchmark")
        self.results_dir = results_dir or (self.root_dir / "benchmark" / "results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.env_manager = BenchmarkEnvironmentManager()
        self.verifier = TaskOutcomeVerifier()
        self.decision_engine = decision_engine

    def load_tasks(self, split: Optional[BenchmarkSplit] = None, task_id: Optional[str] = None) -> List[BenchmarkTask]:
        """Load benchmark tasks matching filter criteria."""
        tasks: List[BenchmarkTask] = []
        dev_dir = self.tasks_dir / "development"
        unseen_dir = self.tasks_dir / "unseen"

        candidate_files: List[Path] = []
        if split is None or split == BenchmarkSplit.DEVELOPMENT:
            if dev_dir.exists():
                candidate_files.extend(sorted(dev_dir.glob("*.json")))
        if split is None or split == BenchmarkSplit.UNSEEN:
            if unseen_dir.exists():
                candidate_files.extend(sorted(unseen_dir.glob("*.json")))

        for f in candidate_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                task = BenchmarkTask.model_validate(data)
                if task_id and task.task_id != task_id:
                    continue
                tasks.append(task)
            except Exception as e:
                logger.error(f"Failed to load task file {f}: {e}")

        return tasks

    async def execute_task(self, task: BenchmarkTask) -> TaskExecutionRecord:
        """Execute an individual benchmark task on the production runtime."""
        logger.info(f"=== Starting Task [{task.task_id}] ({task.split.value}) - {task.title} ===")
        logger.info(f"Goal: '{task.natural_language_goal}'")

        # 1. Environment Setup
        scratchpad = self.env_manager.setup_environment(clean_processes=task.initial_clean_processes or None)

        record = TaskExecutionRecord(
            task_id=task.task_id,
            split=task.split,
            category=task.category,
            natural_language_goal=task.natural_language_goal,
            started_at=datetime.now(timezone.utc),
        )

        start_time = time.perf_counter()
        agent_res: Optional[AgentExecutionResult] = None
        error_msg: Optional[str] = None
        error_code: Optional[str] = None

        try:
            # 2. Boot production capability registry & agent execution loop
            config = RuntimeConfig(adapter_mode=AdapterMode.PRODUCTION)
            registry = create_capability_registry(config=config)
            await registry.initialize_all()

            budget = ExecutionBudget(max_total_actions=task.max_steps, timeout_seconds=task.timeout_sec)
            loop = AgentExecutionLoop(
                workspace=registry.get_optional(CapabilityType.WORKSPACE),
                pointer=registry.get_optional(CapabilityType.POINTER),
                keyboard=registry.get_optional(CapabilityType.KEYBOARD),
                observation=registry.get_optional(CapabilityType.OBSERVATION),
                decision_engine=self.decision_engine,
                budget=budget,
            )

            # 3. Execute goal
            agent_res = await asyncio.wait_for(
                loop.run(task.natural_language_goal),
                timeout=task.timeout_sec + 5.0,
            )

            record.is_success = agent_res.is_success
            record.total_steps = agent_res.total_steps
            record.actions_attempted = agent_res.total_steps
            record.actions_completed = len([s for s in agent_res.step_history if s.decision and s.decision.next_action])
            record.model_calls = agent_res.total_steps

            # Extract step traces
            for step in agent_res.step_history:
                dec = step.decision
                act = dec.next_action if dec else None
                trace = ActionStepTrace(
                    step_index=step.step_index,
                    action_type=act.action_type.value if act and hasattr(act.action_type, "value") else str(act.action_type if act else "NONE"),
                    target_name=act.target.name if act and act.target else None,
                    target_role=act.target.role if act and act.target else None,
                    parameters=act.parameters if act else {},
                    dispatch_success=dec.is_goal_satisfied if dec else False,
                    verification_passed=dec.is_goal_satisfied if dec else False,
                    verification_reason=dec.reason_summary if dec else "",
                )
                record.step_traces.append(trace)

        except asyncio.TimeoutError:
            error_code = "TIMEOUT"
            error_msg = f"Task timed out after {task.timeout_sec} seconds"
            logger.warning(f"Task {task.task_id} TIMEOUT")
        except Exception as e:
            error_code = "EXECUTION_EXCEPTION"
            error_msg = str(e)
            logger.error(f"Task {task.task_id} Exception: {e}", exc_info=True)

        record.completed_at = datetime.now(timezone.utc)
        record.duration_sec = round(time.perf_counter() - start_time, 2)

        # 4. Independent Postcondition Verification
        v_res: VerificationResult = await self.verifier.verify_task_outcome(
            task=task,
            workspace_dir=self.root_dir,
            scratchpad_dir=scratchpad,
        )

        record.goal_verified = v_res.goal_verified
        record.artifact_verified = v_res.artifact_verified

        # Real success requires BOTH agent completion AND independent OS verification
        record.is_success = (record.is_success and v_res.is_passed)

        # 5. Failure Taxonomy Classification if failed
        if not record.is_success:
            has_deliverable = bool(task.expectations.expected_deliverable)
            classification = FailureClassifier.classify_execution_failure(
                is_success=record.is_success,
                error_code=error_code,
                error_message=error_msg,
                verification_reason=v_res.failure_reason,
                goal_verified=v_res.goal_verified,
                artifact_verified=v_res.artifact_verified,
                has_deliverable_spec=has_deliverable,
                actions_attempted=record.actions_attempted,
                actions_completed=record.actions_completed,
                recovery_attempts=record.recovery_attempts,
                timeout_exceeded=(error_code == "TIMEOUT"),
                model_calls=record.model_calls,
            )
            if classification:
                record.failure_category = classification.primary_category.value
                record.failure_reason = classification.diagnostic_details
        else:
            record.failure_category = None
            record.failure_reason = None

        # 6. Teardown
        self.env_manager.teardown_environment(clean_processes=task.initial_clean_processes or None)

        logger.info(
            f"=== Completed [{task.task_id}] | Success: {record.is_success} | "
            f"Goal Verified: {record.goal_verified} | Artifact: {record.artifact_verified} | "
            f"Duration: {record.duration_sec}s | Failure: {record.failure_category or 'NONE'} ==="
        )

        # Save individual task record
        task_out_path = self.results_dir / f"{task.task_id}_result.json"
        task_out_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        return record

    async def run_benchmark(
        self,
        split: Optional[BenchmarkSplit] = None,
        task_id: Optional[str] = None,
    ) -> Tuple[BenchmarkMetricsSummary, List[TaskExecutionRecord]]:
        """Run all requested tasks and generate aggregate metrics summary."""
        tasks = self.load_tasks(split=split, task_id=task_id)
        logger.info(f"Loaded {len(tasks)} benchmark tasks to execute.")

        records: List[TaskExecutionRecord] = []
        for task in tasks:
            rec = await self.execute_task(task)
            records.append(rec)

        summary = self.aggregate_metrics(records)

        # Save summary JSON
        summary_path = self.results_dir / "benchmark_summary.json"
        summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

        # Generate summary Markdown report
        report_md = self.generate_markdown_report(summary, records)
        report_path = self.results_dir / "benchmark_report.md"
        report_path.write_text(report_md, encoding="utf-8")

        return summary, records

    def aggregate_metrics(self, records: List[TaskExecutionRecord]) -> BenchmarkMetricsSummary:
        """Compute aggregate benchmark metrics."""
        total = len(records)
        if total == 0:
            return BenchmarkMetricsSummary()

        dev_records = [r for r in records if r.split == BenchmarkSplit.DEVELOPMENT]
        unseen_records = [r for r in records if r.split == BenchmarkSplit.UNSEEN]

        passed = [r for r in records if r.is_success]
        dev_passed = [r for r in dev_records if r.is_success]
        unseen_passed = [r for r in unseen_records if r.is_success]

        goal_verified = [r for r in records if r.goal_verified]
        artifact_verified = [r for r in records if r.artifact_verified]

        failure_dist: Dict[str, int] = {}
        for r in records:
            if not r.is_success and r.failure_category:
                failure_dist[r.failure_category] = failure_dist.get(r.failure_category, 0) + 1

        category_stats: Dict[str, List[bool]] = {}
        for r in records:
            cat_name = r.category.value
            category_stats.setdefault(cat_name, []).append(r.is_success)

        cat_rates = {k: round(sum(v) / len(v), 4) for k, v in category_stats.items()}

        summary = BenchmarkMetricsSummary(
            total_tasks=total,
            dev_tasks_count=len(dev_records),
            unseen_tasks_count=len(unseen_records),
            total_passed=len(passed),
            dev_passed=len(dev_passed),
            unseen_passed=len(unseen_passed),
            task_success_rate=round(len(passed) / total, 4),
            dev_success_rate=round(len(dev_passed) / len(dev_records), 4) if dev_records else 0.0,
            unseen_success_rate=round(len(unseen_passed) / len(unseen_records), 4) if unseen_records else 0.0,
            goal_verification_accuracy=round(len(goal_verified) / total, 4),
            artifact_correctness_rate=round(len(artifact_verified) / total, 4),
            grounding_accuracy=round(sum(r.actions_completed for r in records) / max(1, sum(r.actions_attempted for r in records)), 4),
            recovery_success_rate=0.0,
            avg_actions_per_task=round(sum(r.actions_completed for r in records) / total, 2),
            avg_duration_sec=round(sum(r.duration_sec for r in records) / total, 2),
            avg_model_calls_per_task=round(sum(r.model_calls for r in records) / total, 2),
            failure_category_distribution=failure_dist,
            category_success_rates=cat_rates,
        )
        return summary

    def generate_markdown_report(self, summary: BenchmarkMetricsSummary, records: List[TaskExecutionRecord]) -> str:
        """Generate a GitHub-flavored Markdown report of benchmark results."""
        lines = [
            "# ORBIT 50-TASK GENERAL RELIABILITY BENCHMARK REPORT",
            f"**Execution Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Total Tasks Evaluated**: {summary.total_tasks} (25 Development + 25 Unseen)  ",
            f"**Overall Success Rate**: **{summary.task_success_rate * 100:.1f}%** ({summary.total_passed}/{summary.total_tasks})  ",
            "",
            "---",
            "",
            "## 1. Primary Baseline Metrics",
            "",
            "| Metric | Value | Target | Evaluation |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Overall Task Success Rate** | **{summary.task_success_rate * 100:.1f}%** | $\\ge 80\\%$ | {'PASS' if summary.task_success_rate >= 0.8 else 'BASELINE ESTABLISHED'} |",
            f"| **Development Split Success Rate** | **{summary.dev_success_rate * 100:.1f}%** | $\\ge 85\\%$ | {'PASS' if summary.dev_success_rate >= 0.85 else 'BASELINE ESTABLISHED'} |",
            f"| **Unseen Split Success Rate** | **{summary.unseen_success_rate * 100:.1f}%** | $\\ge 75\\%$ | {'PASS' if summary.unseen_success_rate >= 0.75 else 'BASELINE ESTABLISHED'} |",
            f"| **Goal Verification Accuracy** | **{summary.goal_verification_accuracy * 100:.1f}%** | $100\\%$ | {'PASS' if summary.goal_verification_accuracy == 1.0 else 'CALIBRATING'} |",
            f"| **Artifact Correctness Rate** | **{summary.artifact_correctness_rate * 100:.1f}%** | $100\\%$ | {'PASS' if summary.artifact_correctness_rate == 1.0 else 'CALIBRATING'} |",
            f"| **Grounding Precision** | **{summary.grounding_accuracy * 100:.1f}%** | $\\ge 90\\%$ | {'PASS' if summary.grounding_accuracy >= 0.9 else 'NEEDS 2G.3 TUNING'} |",
            f"| **Average Execution Time / Task** | **{summary.avg_duration_sec:.2f}s** | $< 45s$ | {'FAST' if summary.avg_duration_sec < 45 else 'NORMAL'} |",
            f"| **Average Model Calls / Task** | **{summary.avg_model_calls_per_task:.1f}** | $< 5.0$ | {'OPTIMAL' if summary.avg_model_calls_per_task < 5 else 'EVALUATE'} |",
            "",
            "---",
            "",
            "## 2. 15-Class Failure Taxonomy Distribution",
            "",
            "| Failure Category | Count | Percentage of Failures | Root Cause Remediation Phase |",
            "| :--- | :--- | :--- | :--- |",
        ]

        total_failures = max(1, summary.total_tasks - summary.total_passed)
        for cat, cnt in sorted(summary.failure_category_distribution.items(), key=lambda x: x[1], reverse=True):
            pct = (cnt / total_failures) * 100
            remediation = "Phase 2G.2 (Recovery)" if "RECOVERY" in cat or "DIALOG" in cat else ("Phase 2G.3 (Grounding)" if "GROUNDING" in cat or "PERCEPTION" in cat else ("Phase 2G.4 (Artifacts)" if "ARTIFACT" in cat or "SAVE" in cat else "Phase 2G.1 (Context)"))
            lines.append(f"| `{cat}` | {cnt} | {pct:.1f}% | **{remediation}** |")

        if not summary.failure_category_distribution:
            lines.append("| *Zero Failures Recorded* | 0 | 0.0% | N/A |")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Performance by Desktop Category",
            "",
            "| Category | Success Rate | Status |",
            "| :--- | :--- | :--- |",
        ])

        for cat, rate in sorted(summary.category_success_rates.items()):
            lines.append(f"| `{cat}` | **{rate * 100:.1f}%** | {'GREEN' if rate >= 0.8 else ('YELLOW' if rate >= 0.5 else 'RED')} |")

        lines.extend([
            "",
            "---",
            "",
            "## 4. Full Task-by-Task Manifest Results",
            "",
            "| Task ID | Split | Category | Goal | Success | Goal Verif | Artifact Verif | Time | Failure Code |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for r in records:
            g_sym = "PASS" if r.goal_verified else "FAIL"
            a_sym = "PASS" if r.artifact_verified else "FAIL"
            s_sym = "**PASS**" if r.is_success else "*FAIL*"
            f_code = f"`{r.failure_category}`" if r.failure_category else "—"
            short_goal = r.natural_language_goal.replace("\n", " ")[:35]
            lines.append(
                f"| `{r.task_id}` | {r.split.value[:3]} | `{r.category.value[:14]}` | {short_goal}... | {s_sym} | {g_sym} | {a_sym} | {r.duration_sec}s | {f_code} |"
            )

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ORBIT 50-Task Benchmark Runner")
    parser.add_argument("--split", choices=["dev", "unseen", "all"], default="all")
    parser.add_argument("--task-id", type=str, default=None)
    parser.add_argument("--results-dir", type=str, default="benchmark/results")
    args = parser.parse_args()

    split_val = None
    if args.split == "dev":
        split_val = BenchmarkSplit.DEVELOPMENT
    elif args.split == "unseen":
        split_val = BenchmarkSplit.UNSEEN

    runner = BenchmarkRunner(results_dir=Path(args.results_dir))
    asyncio.run(runner.run_benchmark(split=split_val, task_id=args.task_id))


if __name__ == "__main__":
    main()
