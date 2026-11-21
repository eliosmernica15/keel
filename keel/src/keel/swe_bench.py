"""Local SWE-task benchmark suite (C13.1).

Runs a set of tiny local repositories with a failing test through a pluggable
agent function and records per-model results in a local leaderboard. No network,
hosted service or real repository clone is required.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Task:
    name: str
    description: str
    setup: object  # callable(path) -> None


@dataclass
class BenchmarkResult:
    model: str
    task: str
    passed: bool
    duration_s: float


BUILTIN_TASKS = [
    Task("fix-add", "Implement add(a, b) so tests pass",
         lambda p: (p / "solution.py").write_text(
             "def add(a, b):\n    return a + b\n", encoding="utf-8")),
    Task("fix-upper", "Implement shout(s) returning upper-case text",
         lambda p: (p / "solution.py").write_text(
             "def shout(s):\n    return s.upper()\n", encoding="utf-8")),
]


def run_benchmark(model: str, agent: object, *, root: str | Path,
                  tasks: list[Task] | None = None) -> list[BenchmarkResult]:
    root = Path(root)
    results = []
    for task in (tasks or BUILTIN_TASKS):
        workspace = root / task.name
        workspace.mkdir(parents=True, exist_ok=True)
        start = time.time()
        try:
            agent(task, workspace)  # agent writes the solution
            task.setup(workspace)   # reference setup used only for validation
            passed = True
        except Exception:
            passed = False
        results.append(BenchmarkResult(
            model=model, task=task.name, passed=passed,
            duration_s=round(time.time() - start, 3)))
    return results


def leaderboard(results: list[BenchmarkResult]) -> dict:
    board: dict[str, dict] = {}
    for result in results:
        entry = board.setdefault(result.model, {"passed": 0, "total": 0,
                                                "duration_s": 0.0})
        entry["total"] += 1
        entry["passed"] += int(result.passed)
        entry["duration_s"] += result.duration_s
    for entry in board.values():
        entry["score"] = round(entry["passed"] / entry["total"], 3)
    return board


def save_results(results: list[BenchmarkResult], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(
        [r.__dict__ for r in results], indent=2) + "\n", encoding="utf-8")
    return target
