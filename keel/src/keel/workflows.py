from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .commands import discover as discover_commands, find as find_command, render_custom, execute_builtin


@dataclass
class WorkflowStep:
    kind: str  # tool | command | shell | map | loop | human
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    command: str = ""
    args: str = ""
    # C5.1/C5.2: deterministic data-flow controls.
    items: list[Any] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    times: int = 1
    timeout_s: int = 300
    default: Any = None


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
                    items=raw.get("items", []) if isinstance(raw.get("items", []), list) else [],
                    steps=raw.get("steps", []) if isinstance(raw.get("steps", []), list) else [],
                    times=max(0, min(1000, int(raw.get("times", 1) or 1))),
                    timeout_s=max(0, int(raw.get("timeout_s", 300) or 300)),
                    default=raw.get("default"),
                ))
            out.append(Workflow(name=name, description=str(doc.get("description", "")),
                               steps=steps, source=scope))
    return out


def find(name: str, project_root: Path | None = None) -> Workflow | None:
    for wf in discover(project_root):
        if wf.name == name:
            return wf
    return None


def _bind(value: Any, item: Any) -> Any:
    """Recursively bind ``{{item}}``/``{{index}}`` placeholders in inputs."""
    if isinstance(value, str):
        return (value.replace("{{item}}", str(item))
                     .replace("{{index}}", str(item)))
    if isinstance(value, dict):
        return {key: _bind(val, item) for key, val in value.items()}
    if isinstance(value, list):
        return [_bind(val, item) for val in value]
    return value


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
                # Route through the secured tool execution path (tier-2 safety).
                # Do not use subprocess.run(shell=True) directly.
                if tool_executor is None:
                    raise RuntimeError("no tool executor provided for shell step")
                result = tool_executor("run_shell", {"command": step.command, "shell": "posix"})
                entry["result"] = result
                entry["ok"] = True
            elif step.kind == "map":
                # Deterministic: run sub-steps once per item with {{item}} bound.
                mapped = []
                for item in step.items[:1000]:
                    sub = Workflow(name=f"map[{i}]", steps=[
                        WorkflowStep(
                            kind=str(s.get("kind", "tool")),
                            name=str(s.get("name", "")),
                            input=_bind(s.get("input", {}), item),
                            command=str(s.get("command", "")),
                            args=str(s.get("args", "")).replace("{{item}}", str(item)),
                        ) for s in step.steps if isinstance(s, dict)])
                    mapped.append(execute_workflow(
                        sub, tool_executor=tool_executor,
                        project_root=project_root, cwd=cwd))
                entry["result"] = mapped
                entry["ok"] = True
            elif step.kind == "loop":
                loop_results = []
                for n in range(step.times):
                    sub = Workflow(name=f"loop[{i}:{n}]", steps=[
                        WorkflowStep(
                            kind=str(s.get("kind", "tool")),
                            name=str(s.get("name", "")),
                            input=_bind(s.get("input", {}), n),
                            command=str(s.get("command", "")),
                            args=str(s.get("args", "")).replace("{{index}}", str(n)),
                        ) for s in step.steps if isinstance(s, dict)])
                    loop_results.append(execute_workflow(
                        sub, tool_executor=tool_executor,
                        project_root=project_root, cwd=cwd))
                entry["result"] = loop_results
                entry["ok"] = True
            elif step.kind == "human":
                # A human-task node: consult a callback (approval/answer),
                # with a bounded timeout and a default when no one answers.
                responder = (tool_executor if callable(tool_executor) else None)
                if responder is None:
                    entry["result"] = step.default
                    entry["ok"] = True
                    entry["defaulted"] = True
                else:
                    answer = responder("ask_user", {
                        "question": step.name or "Approve this step?",
                        "options": step.input.get("options", []),
                        "timeout": step.timeout_s,
                    })
                    entry["result"] = answer
                    entry["ok"] = True
            else:
                raise ValueError(f"unknown step kind: {step.kind}")
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
            entry["ok"] = False
            results.append(entry)
            break
        results.append(entry)
    return results
