"""Operations helpers (A3.x): webhook retry/backoff, workspace GC, setup, status."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def retry_backoff(attempt: int, *, base: float = 1.0, cap: float = 60.0) -> float:
    """Exponential backoff with jitter-free deterministic delay."""
    return min(cap, base * (2 ** max(0, attempt - 1)))


def gc_temp_dirs(state_root: str | Path, *, max_age_s: float = 86400) -> list[str]:
    """Delete old temp workspaces (returns relative names removed)."""
    root = Path(state_root) / "temp"
    if not root.is_dir():
        return []
    removed = []
    now = time.time()
    for path in root.iterdir():
        if not path.is_dir():
            continue
        if now - path.stat().st_mtime > max_age_s:
            import shutil
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
    return removed


def setup_env_example(state_root: str | Path, *, keys: list[str]) -> Path:
    """Generate an idempotent .env.example with masked placeholders."""
    root = Path(state_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / ".env.example"
    lines = ["# Keel configuration reference (no secrets here)"]
    for key in keys:
        lines.append(f"{key}=")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def project_status(verified: int, implemented: int, blocked: int) -> dict:
    return {"verified": verified, "implemented": implemented,
            "blocked": blocked,
            "note": "verified = tests pass; implemented = code exists"}
