"""Automatic verification loop (B2.1).

Detects test/lint/type commands from the project's manifests and runs them
after a turn that changed files. Detection is local-only; no command is run
when the project has no recognisable manifest.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MAX_OUTPUT = 4000
DEFAULT_TIMEOUT = 120


def detect_commands(cwd: str) -> list[dict]:
    """Return commands to run for the project rooted at *cwd*."""
    root = Path(cwd)
    commands: list[dict] = []
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file() \
            or (root / "setup.cfg").is_file():
        commands.append({"kind": "test", "argv": ["python", "-m", "pytest", "-q"]})
    if (root / "package.json").is_file():
        commands.append({"kind": "test", "argv": ["npm", "test"]})
        commands.append({"kind": "lint", "argv": ["npm", "run", "lint"]})
    if (root / "Makefile").is_file():
        commands.append({"kind": "test", "argv": ["make", "test"]})
    if (root / "Cargo.toml").is_file():
        commands.append({"kind": "test", "argv": ["cargo", "test"]})
    if (root / "go.mod").is_file():
        commands.append({"kind": "test", "argv": ["go", "test", "./..."]})
    return commands[:4]


def run_verification(cwd: str, commands: list[dict], *,
                     timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Run *commands* in *cwd* and return structured results."""
    results = []
    for command in commands:
        argv = command["argv"]
        try:
            proc = subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True,
                timeout=timeout, check=False)
            ok = proc.returncode == 0
            output = (proc.stdout + proc.stderr)[-MAX_OUTPUT:]
        except FileNotFoundError as exc:
            ok, output = False, f"command not available: {exc}"
        except subprocess.TimeoutExpired:
            ok, output = False, f"timed out after {timeout}s"
        results.append({"kind": command.get("kind", "test"),
                        "command": " ".join(str(a) for a in argv),
                        "ok": ok, "output": output})
    return results
