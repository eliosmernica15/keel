"""C13.1 — local SWE-task benchmark suite and leaderboard."""

from __future__ import annotations

from keel.swe_bench import (BUILTIN_TASKS, BenchmarkResult, leaderboard,
                            run_benchmark, save_results)


def test_benchmark_and_leaderboard(tmp_path):
    def good_agent(task, workspace):
        task.setup(workspace)  # writes the correct solution

    results = run_benchmark("model-a", good_agent, root=tmp_path)
    assert len(results) == len(BUILTIN_TASKS)
    assert all(r.passed for r in results)
    board = leaderboard(results)
    assert board["model-a"]["score"] == 1.0


def test_failing_agent_scored_zero(tmp_path):
    def bad_agent(task, workspace):
        raise RuntimeError("could not solve")

    results = run_benchmark("model-b", bad_agent, root=tmp_path)
    assert leaderboard(results)["model-b"]["score"] == 0.0


def test_save_results(tmp_path):
    path = save_results(
        [BenchmarkResult("m", "t", True, 0.1)], tmp_path / "results.json")
    assert path.is_file() and "model" in path.read_text(encoding="utf-8")
