"""Real git extras using the user's local git (C4.9).

All operations are opt-in and run against an explicit repository path via
subprocess without a shell. Read operations work on any repo; write operations
require an explicit allow flag.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(repo: str | Path, *args: str, allow_write: bool = False) -> str:
    repo = Path(repo)
    if not (repo / ".git").exists():
        raise GitError(f"not a git repository: {repo}")
    write_cmds = {"commit", "add", "checkout", "reset", "rebase", "push", "stash"}
    if args and args[0] in write_cmds and not allow_write:
        raise GitError(f"write git command requires allow_write: {args[0]}")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
            timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git failed: {exc}") from None
    if proc.returncode != 0:
        raise GitError((proc.stderr or proc.stdout).strip()[:500])
    return proc.stdout.strip()


def status(repo: str | Path) -> list[str]:
    return _git(repo, "status", "--porcelain").splitlines()


def log(repo: str | Path, count: int = 10) -> list[str]:
    return _git(repo, "log", f"-{max(1, min(50, count))}", "--oneline").splitlines()


def blame(repo: str | Path, path: str) -> list[str]:
    return _git(repo, "blame", "--", path).splitlines()[:200]


def hunk_stage(repo: str | Path, path: str, *, allow_write: bool = False) -> str:
    """Interactive hunk staging via git add -p (requires opt-in)."""
    if not allow_write:
        raise GitError("hunk staging requires allow_write")
    return _git(repo, "add", "-p", "--", path, allow_write=True)


def stacked_commit(repo: str | Path, message: str, *, allow_write: bool = False) -> str:
    if not allow_write:
        raise GitError("commit requires allow_write")
    return _git(repo, "commit", "-m", message, allow_write=True)
