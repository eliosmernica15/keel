from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .commands import discover as discover_commands, find as find_command, render_custom, execute_builtin


@dataclass
class WorkflowStep:
    kind: str  # tool | command | shell
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    command: str = ""
    args: str = ""


@dataclass
class Workflow:
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    source: str = "user"  # user | project | builtin


def _roots(project_root: Path | None) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = []
    if project_root is not None:
        roots.append((Path(project_root) / ".keel" / "workflows", "project"))
    roots.append((Path(os.path.expanduser("~")) / ".keel" / "workflows", "user"))
    return roots


def discover(project_root: Path | None = None) -> list[Workflow]:
    out: list[Workflow] = []
    for root, scope in _roots(project_root):
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(doc, dict):
                continue
            name = str(doc.get("name") or path.stem)
            steps = []
            for raw in doc.get("steps", []) or []:
                if not isinstance(raw, dict):
                    continue
                kind = str(raw.get("kind", "tool"))
                steps.append(WorkflowStep(
                    kind=kind,
                    name=str(raw.get("name", "")),
                    input=raw.get("input", {}) if isinstance(raw.get("input", {}), dict) else {},
                    command=str(raw.get("command", "")),
                    args=str(raw.get("args", "")),
                ))
            out.append(Workflow(name=name, description=str(doc.get("description", "")),
                               steps=steps, source=scope))
    return out


def find(name: str, project_root: Path | None = None) -> Workflow | None:
    for wf in discover(project_root):
        if wf.name == name:
            return wf
    return None


def execute_workflow(workflow: Workflow, *, tool_executor: Callable[[str, dict], Any] | None = None,
                     project_root: Path | None = None, cwd: str | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for i, step in enumerate(workflow.steps):
        entry = {"step": i, "kind": step.kind, "name": step.name or step.command, "ok": False}
        try:
            if step.kind == "tool":
                if tool_executor is None:
                    raise RuntimeError("no tool executor provided")
                result = tool_executor(step.name, step.input)
                entry["result"] = result
                entry["ok"] = True
            elif step.kind == "command":
                cmd = find_command(step.command, Path(project_root) if project_root else Path.cwd()) if step.command else None
                if cmd is None:
                    raise RuntimeError(f"unknown command: {step.command}")
                if cmd.source == "builtin":
                    out = execute_builtin(cmd.name, step.args, Path(project_root or cwd or "."))
                else:
                    out = render_custom(cmd, step.args)
                entry["result"] = out
                entry["ok"] = True
            elif step.kind == "shell":
                import subprocess
                proc = subprocess.run(step.command, shell=True, capture_output=True, timeout=120, check=False, cwd=cwd)
                stdout = proc.stdout.decode("utf-8", errors="replace")
                stderr = proc.stderr.decode("utf-8", errors="replace")
                entry["result"] = stdout + ("\n" if stdout and stderr else "") + stderr
                entry["ok"] = proc.returncode == 0
                entry["exit_code"] = proc.returncode
            else:
                raise ValueError(f"unknown step kind: {step.kind}")
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
            entry["ok"] = False
            results.append(entry)
            break
        results.append(entry)
    return results
