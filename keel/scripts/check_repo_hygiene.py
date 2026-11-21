"""C1.1 — verify the repository hygiene stack is present and configured."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KEEL = REPO / "keel"


def _nested(doc: dict, path: str):
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def problems() -> list[str]:
    found = []
    required = [
        REPO / ".editorconfig",
        REPO / ".gitleaks.toml",
        REPO / ".pre-commit-config.yaml",
        KEEL / "CHANGELOG.md",
        KEEL / "patches" / "README.md",
        KEEL / "pyproject.toml",
    ]
    for path in required:
        if not path.is_file():
            found.append(f"missing {path.relative_to(REPO)}")
    pyproject_path = KEEL / "pyproject.toml"
    if pyproject_path.is_file():
        doc = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        for section in ("tool.ruff", "tool.mypy", "tool.pytest.ini_options"):
            if _nested(doc, section) is None:
                found.append(f"pyproject.toml missing [{section}]")
    return found


def main() -> int:
    found = problems()
    if found:
        for item in found:
            print(item, file=sys.stderr)
        return 1
    print("repo hygiene stack: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
