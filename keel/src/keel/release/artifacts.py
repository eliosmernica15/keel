"""Release artifact allowlisting and prohibited-content checks (M1).

These checks are intentionally path-name based: they detect source maps,
development-only files, internal planning documents and third-party research
captures before an installer or staged release can be published. They do not
remove or relocate source-tree material.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

# Internal material that must never be copied into a public installer or a
# staged release directory. Matched against POSIX-style relative paths.
PROHIBITED_PATTERNS: tuple[str, ...] = (
    "*.map",
    "*.pdb",
    "*.pyc",
    "*.pyo",
    "*.py",
    "*.ts",
    "*.tsx",
    ".env",
    ".env.*",
    "*/.env",
    "*/.env.*",
    "*/.vercel/*",
    "*/.vercel/**/*",
    "*/.git/*",
    "*/.git/**/*",
    "*/agent-reference-shots/*",
    "*/agent-reference-shots/**/*",
    "agent-reference-shots/*",
    "agent-reference-shots/**/*",
    "*/research/*",
    "*/research/**/*",
    "research/*",
    "research/**/*",
    "*/.verify-*/*",
    "*/.verify-*/**/*",
    "*/.build/*",
    "*/.probe/*",
    "*/.rea-inspect/*",
    "*/.claude/*",
    "*/_check_*.py",
    "*_check_*.py",
    "*_wf-findings-raw.json",
    "*_corrections-ledger.md",
    "*/claude-code-evidence.md",
    "claude-code-evidence.md",
    "*/agent-evidence*.md",
    "agent-evidence*.md",
    "*/prompt-pattern-analysis.md",
    "prompt-pattern-analysis.md",
    "*/licensing-and-provenance-review.md",
    "licensing-and-provenance-review.md",
    "*/implementation-plan.md",
    "*/security-plan.md",
    "*/architecture.md",
    "*/test-plan.md",
    "*/feature-checklist.md",
    "*/FINAL-APPROVAL-GATE.md",
    "*/HOSTING.md",
    "*/ROADMAP.md",
    "*/docs/proprietary/*",
    "*/docs/proprietary/**/*",
    "*/docs/internal/*",
    "*/docs/internal/**/*",
)


def _matches(rel: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(rel, pattern):
        return True
    parts = rel.split("/")
    if fnmatch.fnmatchcase(parts[-1], pattern):
        return True
    suffix_pattern = pattern[2:] if pattern.startswith("*/") else pattern
    for index in range(len(parts)):
        if fnmatch.fnmatchcase("/".join(parts[index:]), suffix_pattern):
            return True
    return False


def scan_tree(root: Path) -> list[str]:
    """Return sorted relative paths under *root* that violate the allowlist."""
    if not root.is_dir():
        return []
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(_matches(rel, pattern) for pattern in PROHIBITED_PATTERNS):
            violations.append(rel)
    return sorted(violations)


def validate_tree(root: Path) -> None:
    violations = scan_tree(root)
    if violations:
        preview = ", ".join(violations[:20])
        suffix = "" if len(violations) <= 20 else f" (and {len(violations) - 20} more)"
        raise ValueError(
            f"prohibited files in {root}: {preview}{suffix}")


def validate_staged_release(out_dir: Path, version: str,
                            required: set[str] | None = None) -> None:
    """Fail on prohibited content, and on missing names when *required* is given."""
    violations = scan_tree(out_dir)
    if violations:
        raise ValueError("prohibited staged release files: " + ", ".join(violations[:20]))
    if required is None:
        return
    names = {p.name for p in out_dir.iterdir() if p.is_file()}
    missing = sorted(required - names)
    if missing:
        raise ValueError("missing required artifacts: " + ", ".join(missing))
