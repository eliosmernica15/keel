"""Release artifact allowlisting and prohibited-content checks (M1).

These checks are intentionally path-name based: they detect source maps,
development-only files, internal planning documents and third-party research
captures before an installer or staged release can be published. They do not
remove or relocate source-tree material.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# A PyInstaller one-file sidecar produces exactly one executable at the root
# of its output directory. One-folder layouts add an _internal directory whose
# compiled runtime files are validated by scan_tree(), not blanket-excluded.
EXPECTED_SIDECAR_BINARIES: frozenset[str] = frozenset({"keel", "keel.exe"})

# Clear-text credential markers. Full history scanning remains gitleaks' job;
# this catches accidentally placed credential files in a runtime payload.
SECRET_MARKERS = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{16,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"\bgithub_pat_[A-Za-z0-9_]{20,}|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----)"
)

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


def scan_secret_markers(root: Path) -> list[str]:
    """Return relative paths containing clear-text credential markers."""
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:4096]:
            continue  # compiled/binary runtime file
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if SECRET_MARKERS.search(text):
            hits.append(path.relative_to(root).as_posix())
    return sorted(hits)


def scan_sidecar_payload(root: Path) -> list[str]:
    """Validate the real sidecar output, including one-folder runtime payloads."""
    violations = set(scan_tree(root))
    violations.update(scan_secret_markers(root))
    for child in root.iterdir():
        if child.is_file() and child.name not in EXPECTED_SIDECAR_BINARIES:
            violations.add(f"unexpected sidecar root file: {child.name}")
    return sorted(violations)


def validate_tree(root: Path) -> None:
    violations = scan_tree(root)
    if violations:
        preview = ", ".join(violations[:20])
        suffix = "" if len(violations) <= 20 else f" (and {len(violations) - 20} more)"
        raise ValueError(
            f"prohibited files in {root}: {preview}{suffix}")


def validate_sidecar(root: Path) -> None:
    violations = scan_sidecar_payload(root)
    if violations:
        raise ValueError(
            "prohibited sidecar payload: " + ", ".join(violations[:20]))


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
