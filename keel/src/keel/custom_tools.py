"""Custom Python tools from ``.keel/tools/*.py`` (A1.13).

Discovery and listing use AST parsing only — no project code is imported or
executed until the operator has explicitly approved the tool. Approval is
keyed by path plus file content, so editing a tool requires re-approval.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path


def tools_dir(cwd: str | Path) -> Path:
    return Path(cwd) / ".keel" / "tools"


def approvals_path() -> Path:
    raw = os.environ.get("KEEL_CUSTOM_TOOL_APPROVALS")
    if raw:
        return Path(raw)
    return (Path(os.environ.get("KEEL_STATE_DIR", str(Path.home() / ".keel")))
            / "custom-tool-approvals.json")


def approvals() -> dict:
    path = approvals_path()
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _save(doc: dict) -> None:
    path = approvals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def approval_key(path: str | Path) -> str:
    target = Path(path).resolve()
    raw = str(target) + "\n" + target.read_text(encoding="utf-8", errors="replace")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_approved(path: str | Path) -> bool:
    key = approval_key(path)
    return any(entry.get("key") == key for entry in approvals().values()
               if isinstance(entry, dict))


def approve(path: str | Path) -> str:
    target = Path(path).resolve()
    spec = describe(target)
    doc = approvals()
    doc[spec["name"]] = {"path": str(target), "key": approval_key(target)}
    _save(doc)
    return spec["name"]


def revoke(name: str) -> bool:
    doc = approvals()
    if name not in doc:
        return False
    doc.pop(name)
    _save(doc)
    return True


def describe(path: str | Path) -> dict:
    """Extract tool metadata from source without executing it."""
    target = Path(path).resolve()
    tree = ast.parse(target.read_text(encoding="utf-8"))
    values: dict = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for item in node.targets:
            if isinstance(item, ast.Name) and item.id in (
                    "TOOL_NAME", "DESCRIPTION", "INPUT_SCHEMA"):
                try:
                    values[item.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
    schema = values.get("INPUT_SCHEMA")
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    return {
        "name": str(values.get("TOOL_NAME") or target.stem),
        "description": str(values.get("DESCRIPTION") or ""),
        "input_schema": schema,
        "path": str(target),
    }


def discover(cwd: str | Path) -> list[dict]:
    root = tools_dir(cwd)
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = describe(path)
        except (OSError, SyntaxError, ValueError):
            continue
        spec["approved"] = is_approved(path)
        found.append(spec)
    return found


def load_callable(path: str | Path):
    """Import an approved tool module and return its ``run`` callable."""
    target = Path(path).resolve()
    module_name = "keel_custom_" + hashlib.sha1(str(target).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load custom tool: {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise ValueError("custom tool must define run(tool_input, context=None)")
    return run
