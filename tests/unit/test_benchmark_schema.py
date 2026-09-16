"""Unit tests validating 50-task benchmark specifications and schemas."""

import json
from pathlib import Path
import pytest

from benchmark.schema import (
    BenchmarkCategory,
    BenchmarkSplit,
    BenchmarkTask,
)


def test_benchmark_tasks_schema_validation():
    root = Path(__file__).resolve().parents[2]
    dev_dir = root / "benchmark" / "development"
    unseen_dir = root / "benchmark" / "unseen"

    dev_files = sorted(dev_dir.glob("*.json"))
    unseen_files = sorted(unseen_dir.glob("*.json"))

    assert len(dev_files) == 25, f"Expected exactly 25 development tasks, found {len(dev_files)}"
    assert len(unseen_files) == 25, f"Expected exactly 25 unseen tasks, found {len(unseen_files)}"

    all_tasks = []
    # Validate Development Tasks
    for f in dev_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        task = BenchmarkTask.model_validate(data)
        assert task.split == BenchmarkSplit.DEVELOPMENT
        assert task.task_id.startswith("task_")
        assert len(task.natural_language_goal) > 0
        all_tasks.append(task)

    # Validate Unseen Tasks
    for f in unseen_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        task = BenchmarkTask.model_validate(data)
        assert task.split == BenchmarkSplit.UNSEEN
        assert task.task_id.startswith("task_")
        assert len(task.natural_language_goal) > 0
        all_tasks.append(task)

    # Verify ID uniqueness across all 50 tasks
    task_ids = [t.task_id for t in all_tasks]
    assert len(task_ids) == 50
    assert len(set(task_ids)) == 50

    # Verify Category Coverage
    categories_present = set(t.category for t in all_tasks)
    expected_categories = set(BenchmarkCategory)
    assert categories_present == expected_categories, f"Missing categories: {expected_categories - categories_present}"
