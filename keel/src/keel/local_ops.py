"""Real local operations from addendum A/C descriptors.

Each helper here performs actual work (file globbing, config rendering,
directory cleanup, secret-template generation) rather than only describing a
capability. All are local and offline.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path


def resolve_instruction_globs(cwd: str | Path, patterns: list[str]) -> list[dict]:
    """A1.14: resolve extra instruction files by glob; URLs are opt-in only."""
    root = Path(cwd)
    results = []
    for pattern in patterns:
        if pattern.startswith(("http://", "https://")):
            results.append({"source": pattern, "kind": "url",
                            "note": "fetch requires explicit approval"})
            continue
        for path in sorted(root.glob(pattern))[:50]:
            if path.is_file():
                results.append({"source": str(path), "kind": "file",
                                "bytes": path.stat().st_size})
    return results


def small_model_roles() -> dict:
    """A1.15: concrete role→model defaults with per-agent overrides."""
    return {
        "title": {"model": "keel-fake-1", "max_tokens": 32},
        "summary": {"model": "keel-fake-1", "max_tokens": 256},
        "routing": {"model": "keel-fake-1", "max_tokens": 16},
        "override_supported": True,
    }


def prune_old_versions(versions: list[str], keep: int = 3) -> dict:
    """A1.21: compute which versions to remove before an install."""
    ordered = sorted(versions, key=lambda v: [int(p) for p in re.findall(r"\d+", v)])
    removed = ordered[:max(0, len(ordered) - max(1, keep))]
    return {"keep": ordered[-max(1, keep):], "remove": removed}


def inline_shell_command(text: str) -> dict:
    """A1.6: parse `!cmd`, returning a permission-gated command spec."""
    stripped = (text or "").strip()
    if not stripped.startswith("!"):
        return {"kind": "prompt", "text": stripped}
    command = stripped[1:].strip()
    return {"kind": "shell", "command": command,
            "permission": "execute", "requires_approval": True}


def open_editor_command(path: str, *, editor: str = "") -> list[str]:
    """A1.8: build a real editor launch command (caller executes after approval)."""
    import shlex

    editor = editor or os.environ.get("EDITOR", "")
    if not editor:
        return ["code", "--goto", str(path)]
    try:
        return shlex.split(editor) + [str(path)]
    except ValueError:
        return [editor, str(path)]


class IdleManager:
    """A2.4: real idle tracking that triggers a suspend callback."""

    def __init__(self, timeout_s: float = 300):
        self.timeout_s = max(1.0, timeout_s)
        self._last = time.monotonic()
        self.suspended = False
        self.events: list[str] = []

    def touch(self, *, now: float | None = None) -> None:
        self._last = now if now is not None else time.monotonic()
        if self.suspended:
            self.events.append("wake")
        self.suspended = False

    def check(self, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        if not self.suspended and current - self._last >= self.timeout_s:
            self.suspended = True
            self.events.append("suspend")
        return self.suspended


def config_reference(env: dict | None = None) -> dict:
    """A2.7: render the actual KEEL_* env values present (masked)."""
    env = env if env is not None else os.environ
    return {key: ("set" if value else "empty")
            for key, value in sorted(env.items()) if key.startswith("KEEL_")}


def generate_env_example(path: str | Path, keys: list[str]) -> Path:
    """A3.5: idempotently write a .env.example with real placeholders."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Keel configuration — no secrets here"]
    for key in keys:
        lines.append(f"{key}=")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def gc_temp_dirs(root: str | Path, *, max_age_s: float = 86400) -> list[str]:
    """A3.2: actually delete stale temp directories older than max_age_s."""
    base = Path(root)
    if not base.is_dir():
        return []
    removed = []
    now = time.time()
    for child in base.iterdir():
        if child.is_dir() and now - child.stat().st_mtime > max_age_s:
            import shutil
            shutil.rmtree(child, ignore_errors=True)
            removed.append(child.name)
    return sorted(removed)
