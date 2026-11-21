"""Local code intelligence (C4.2, C4.3, C4.4).

Pure-Python, regex-based analysis of a source tree: symbol extraction,
a dependency graph via imports, change-risk scoring, and structural search.
No LSP server or external tool is required.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def scan_symbols(root: str | Path) -> dict[str, list[str]]:
    """Map module names to top-level symbols found in Python files."""
    root = Path(root)
    result: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if any(part in ("__pycache__", ".git", "node_modules")
               for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        symbols = [node.name for node in tree.body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.ClassDef))]
        result[path.stem] = symbols
    return result


def dependency_graph(root: str | Path) -> dict[str, list[str]]:
    """Map modules to the local modules they import."""
    root = Path(root)
    local_names = {path.stem for path in root.rglob("*.py")}
    graph: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                name = node.module.split(".")[-1]
                if name in local_names and name != path.stem:
                    deps.add(name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[-1]
                    if name in local_names and name != path.stem:
                        deps.add(name)
        graph[path.stem] = sorted(deps)
    return graph


def impacted(graph: dict[str, list[str]], changed: str) -> list[str]:
    """Return modules that transitively depend on *changed*."""
    reverse: dict[str, set[str]] = {}
    for module, deps in graph.items():
        for dep in deps:
            reverse.setdefault(dep, set()).add(module)
    seen: set[str] = set()
    stack = [changed]
    while stack:
        current = stack.pop()
        for dependent in reverse.get(current, ()):
            if dependent not in seen:
                seen.add(dependent)
                stack.append(dependent)
    return sorted(seen)


def change_risk(graph: dict[str, list[str]], changed: list[str]) -> dict:
    impact = set()
    for module in changed:
        impact.update(impacted(graph, module))
    score = min(1.0, len(impact) / max(1, len(graph)))
    return {"risk": round(score, 3), "impacted": sorted(impact)}


def structural_search(root: str | Path, pattern: str) -> list[dict]:
    """Regex search across source lines with file/line references."""
    root = Path(root)
    regex = re.compile(pattern)
    hits = []
    for path in sorted(root.rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines, 1):
            if regex.search(line):
                hits.append({"file": str(path), "line": index,
                             "text": line.strip()[:200]})
    return hits[:500]
