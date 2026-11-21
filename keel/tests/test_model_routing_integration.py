"""B1.3 — model routing is wired into the real CLI run path (opt-in)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_routing_off_by_default(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "keel", "-p", "hello", "--state-root",
         str(tmp_path / "state")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "model_routing" not in result.stderr


def test_routing_logs_tier_when_enabled(tmp_path):
    import os

    env = dict(os.environ, KEEL_MODEL_ROUTING="1")
    result = subprocess.run(
        [sys.executable, "-m", "keel", "-p", "hello", "--state-root",
         str(tmp_path / "state")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, env=env)
    assert result.returncode == 0
    assert "[keel:model_routing]" in result.stderr
    payload = next(line for line in result.stderr.splitlines()
                   if "model_routing" in line)
    assert json.loads(payload.split(" ", 1)[1])["tier"] in (
        "easy", "medium", "hard")
