"""Real Git worktree runtime and non-Git exact-file staging runtime.

This module deliberately keeps two different isolation strategies in one place
because Keel has two different project shapes:

* For Git projects, create one worktree per session on a deterministic branch
  and let Git own the file-level isolation (the CodeDen-style pattern).
* For non-Git projects, claim an exact relative file list, copy **only** those
  files into a private staging area, and have the driver validate and apply the
  result with backups and a journal (the Frenemy-style pattern).

SECURITY MODEL — read before using either runtime
-------------------------------------------------
1. A Git worktree isolates **files, not processes**. Code run inside a worktree
   is the same OS user with the same privileges as code in the main checkout.
   Worktrees do not sandbox network access, credentials, child processes or
   writes elsewhere on the user's filesystem.
2. The staging lock is **cooperative, not a security sandbox**. It is an
   advisory file that well-behaved callers honour. A same-user process can
   delete, ignore or forge it. Keel must back it with its own OS-level sandbox
   and permissions whenever untrusted code can run.
3. Cleanup of processes owned by a worktree session is **out of scope** for
   this module. It never signals, kills or reaps processes. A caller that
   starts work in a worktree must confirm the old worker has actually stopped
   before reusing or removing that worktree; elapsed time is not proof of
   termination.

All paths are resolved with ``os.path.realpath`` and checked for containment.
Symlinked path components that escape the permitted root are rejected. Git is
invoked with argument lists and ``shell=False`` only. The staging runtime uses
the Python standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

_GIT_TIMEOUT = 30
_MAX_SUFFIX = 100
_WRITE_TASKS = frozenset({"write", "apply", "edit"})


class WorktreeError(RuntimeError):
    """Typed failure for both runtimes; ``code`` is stable for callers/tests."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Shared path safety helpers
# ---------------------------------------------------------------------------


def _contained(root: Path, candidate: Path) -> bool:
    """True when ``candidate`` is ``root`` or lies below it (both realpaths)."""
    return candidate == root or root in candidate.parents


def _normalize_rel(value: Any, *, label: str = "path") -> str:
    """Normalize a relative path to ``a/b`` form, rejecting escapes early.

    Accepts Windows-style backslashes but rejects drive letters, UNC prefixes,
    rooted paths, ``..`` segments, NUL bytes and empty paths. This is done
    before touching the filesystem, so a hostile claim cannot reach a path
    outside the project even through separator tricks.
    """
    if isinstance(value, (bytes, os.PathLike)):
        value = os.fspath(value)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise WorktreeError("invalid_path", f"{label} must be a non-empty string")
    text = value.replace("\\", "/")
    if re.match(r"^[A-Za-z]:", text) or text.startswith("/"):
        raise WorktreeError("absolute_path", f"{label} must be relative: {value!r}")
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise WorktreeError("path_traversal", f"{label} contains '..': {value!r}")
        parts.append(part)
    if not parts:
        raise WorktreeError("empty_path", f"{label} names no file or directory")
    return "/".join(parts)


def _reject_symlink_components(root: Path, rel: str) -> None:
    """Reject any existing symlink component on ``root / rel``."""
    current = root
    for part in rel.split("/"):
        current = current / part
        if current.is_symlink():
            raise WorktreeError("symlink_path", f"symlink component is not allowed: {current}")


def _resolve_within(root: Path, value: Any, *, allow_missing: bool = True,
                    label: str = "path") -> Path:
    """Resolve a relative path under ``root``, rejecting symlinks and escapes."""
    rel = _normalize_rel(value, label=label)
    _reject_symlink_components(root, rel)
    candidate = Path(os.path.realpath(str(root / rel)))
    if not _contained(root, candidate):
        raise WorktreeError("path_escape", f"{label} escapes {root}: {value!r}")
    if not allow_missing and not candidate.exists():
        raise WorktreeError("path_missing", f"{label} does not exist: {candidate}")
    return candidate


def _resolve_target(root: Path, value: Any) -> Path:
    """Resolve a worktree destination (relative or absolute) under ``root``."""
    text = os.fspath(value) if isinstance(value, os.PathLike) else value
    if not isinstance(text, str) or not text or "\x00" in text:
        raise WorktreeError("invalid_path", "worktree destination must be a non-empty path")
    text = text.replace("\\", "/")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        candidate = Path(os.path.realpath(text))
        if not _contained(root, candidate):
            raise WorktreeError("path_escape", f"worktree destination escapes {root}: {value!r}")
        rel = os.path.relpath(str(candidate), str(root))
        if rel != "." and not rel.startswith(".."):
            _reject_symlink_components(root, rel.replace("\\", "/"))
        return candidate
    return _resolve_within(root, text, label="worktree destination")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _atomic_write_bytes(dest: Path, data: bytes, mode: int) -> None:
    """Write ``data`` to ``dest`` via a same-directory temp file + replace."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".keel-tmp-", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp, mode)
        except OSError:
            # Some filesystems (notably Windows mounts) cannot set POSIX modes.
            pass
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Git worktree runtime
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorktreeInfo:
    """One line of ``git worktree list --porcelain``, with a realpath."""

    path: str
    head: str
    branch: str
    detached: bool = False
    bare: bool = False
    locked: bool = False
    prunable: bool = False


def _git(repo: Path, *args: str, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run Git with an argv list. Never uses a shell."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        raise WorktreeError("git_missing", "git executable was not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise WorktreeError("git_timeout", f"git {' '.join(args)} timed out") from None
    except OSError as exc:
        raise WorktreeError("git_failed", str(exc)) from None


def _git_ok(repo: Path, *args: str) -> str:
    proc = _git(repo, *args)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:800]
        raise WorktreeError("git_failed", f"git {' '.join(args)} failed: {detail}")
    return proc.stdout.strip()


def repo_root(repo: str | Path) -> Path:
    """Return the realpath of the repository's top-level directory."""
    candidate = Path(os.path.realpath(os.fspath(repo)))
    if not candidate.is_dir():
        raise WorktreeError("invalid_repo", f"not a directory: {candidate}")
    if not (candidate / ".git").exists():
        raise WorktreeError("not_a_repo", f"no .git entry: {candidate}")
    toplevel = _git_ok(candidate, "rev-parse", "--show-toplevel").splitlines()
    if not toplevel:
        raise WorktreeError("not_a_repo", f"cannot resolve toplevel: {candidate}")
    root = Path(os.path.realpath(toplevel[0]))
    if not _contained(candidate, root) and not _contained(root, candidate):
        raise WorktreeError("path_escape", f"repository toplevel is unexpected: {root}")
    return root


def is_dirty(repo: str | Path) -> bool:
    """True when the checkout has staged, unstaged or untracked changes."""
    return bool(_git_ok(repo_root(repo), "status", "--porcelain"))


def _slug(value: str, *, limit: int = 40) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:limit].strip("-")
    return text or "session"


def branch_name(session_id: str, *, prefix: str = "keel") -> str:
    """Deterministic branch name for a session (no randomness, no ambivalence)."""
    if not isinstance(session_id, str) or not session_id:
        raise WorktreeError("invalid_session", "session_id must be a non-empty string")
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]
    return f"{_slug(prefix)}/{_slug(session_id)}-{digest}"


def _branch_exists(root: Path, branch: str) -> bool:
    return _git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


def _resolve_ref(root: Path, ref: str) -> str:
    if (not isinstance(ref, str) or not ref or ref.startswith("-")
            or not re.fullmatch(r"[A-Za-z0-9_./~^+-]+", ref)
            or ".." in ref or "@{" in ref):
        raise WorktreeError("invalid_ref", f"unsafe base ref: {ref!r}")
    proc = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if proc.returncode != 0:
        raise WorktreeError("unknown_ref", f"base ref does not name a commit: {ref!r}")
    return proc.stdout.strip()


def list_worktrees(repo: str | Path) -> list[WorktreeInfo]:
    """List worktrees, validating that every reported path stays in the repo."""
    root = repo_root(repo)
    output = _git_ok(root, "worktree", "list", "--porcelain")
    found: list[WorktreeInfo] = []
    block: dict[str, Any] = {}

    def flush() -> None:
        if "worktree" not in block:
            return
        raw = block["worktree"]
        path = Path(os.path.realpath(str(raw)))
        if not _contained(root, path):
            raise WorktreeError("path_escape", f"worktree path escapes {root}: {raw}")
        rel = os.path.relpath(str(path), str(root))
        if rel != "." and not rel.startswith(".."):
            _reject_symlink_components(root, rel.replace("\\", "/"))
        found.append(WorktreeInfo(
            path=str(path),
            head=str(block.get("HEAD", "")),
            branch=str(block.get("branch", "")).removeprefix("refs/heads/"),
            detached="detached" in block,
            bare="bare" in block,
            locked="locked" in block,
            prunable="prunable" in block,
        ))

    for line in output.splitlines():
        if not line.strip():
            flush()
            block = {}
            continue
        key, _, value = line.partition(" ")
        block[key] = value
    flush()
    return found


def create_worktree(
    repo: str | Path,
    session_id: str,
    *,
    base_ref: str = "HEAD",
    worktree_dir: str | Path | None = None,
    collision: str = "reject",
    allow_dirty: bool = False,
    prefix: str = "keel",
) -> WorktreeInfo:
    """Create a worktree on a deterministic branch at ``base_ref``.

    ``collision='reject'`` (the default) refuses when the deterministic branch
    or destination already exists. ``collision='suffix'`` deterministically
    tries ``-2``, ``-3``, ... instead. The source checkout must be clean unless
    ``allow_dirty`` is explicitly set. Managed paths default to
    ``.git/keel/worktrees/<session-slug>`` so the source checkout is not
    dirtied by its own worktrees.
    """
    if collision not in ("reject", "suffix"):
        raise WorktreeError("invalid_option", "collision must be 'reject' or 'suffix'")
    root = repo_root(repo)
    if is_dirty(root) and not allow_dirty:
        raise WorktreeError("dirty_checkout", "source checkout is dirty; commit/stash first "
                            "or pass allow_dirty=True")
    commit = _resolve_ref(root, base_ref)
    branch = branch_name(session_id, prefix=prefix)
    managed = f".git/keel/worktrees/{_slug(session_id)}"
    base_dir = os.fspath(worktree_dir) if worktree_dir is not None else managed

    registered = {info.path for info in list_worktrees(root)}
    chosen_branch = ""
    target = root
    for attempt in range(1, _MAX_SUFFIX + 1):
        candidate_branch = branch if attempt == 1 else f"{branch}-{attempt}"
        candidate_dir = base_dir if attempt == 1 else f"{base_dir}-{attempt}"
        candidate_target = _resolve_target(root, candidate_dir)
        if _branch_exists(root, candidate_branch):
            if collision == "reject" and attempt == 1:
                raise WorktreeError("branch_collision", f"branch already exists: {candidate_branch}")
            continue
        if candidate_target.exists() or str(candidate_target) in registered:
            if collision == "reject":
                raise WorktreeError("worktree_exists", f"destination is in use: {candidate_target}")
            continue
        chosen_branch, target = candidate_branch, candidate_target
        break
    else:
        raise WorktreeError("collision_exhausted", f"no free branch suffix after {_MAX_SUFFIX} tries")

    target.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(root, "worktree", "add", "-b", chosen_branch, str(target), commit)
    for info in list_worktrees(root):
        if info.path == str(target):
            return info
    raise WorktreeError("worktree_missing", f"git did not report the new worktree: {target}")


def _find_worktree(root: Path, target: str | Path) -> Path:
    """Resolve a session id, branch slug, or contained path to a worktree."""
    text = os.fspath(target) if isinstance(target, os.PathLike) else target
    if not isinstance(text, str) or not text:
        raise WorktreeError("invalid_worktree", "worktree identifier must be non-empty")
    normal = text.replace("\\", "/")
    if normal.startswith(".") or normal.startswith("/") or re.match(r"^[A-Za-z]:", normal):
        return _resolve_target(root, normal)
    # Session ids may contain slashes; the deterministic branch is a stronger
    # identifier than a relative path, so try it first.
    wanted = branch_name(normal)
    for info in list_worktrees(root):
        if info.branch == wanted:
            return Path(info.path)
    candidate = _resolve_target(root, normal)
    if candidate.exists():
        return candidate
    fallback = _resolve_target(root, f".git/keel/worktrees/{_slug(normal)}")
    if fallback.exists():
        return fallback
    raise WorktreeError("unknown_worktree", f"no worktree for session: {text}")


def _worktree_dirty(worktree: Path) -> bool:
    return bool(_git_ok(worktree, "status", "--porcelain"))


def remove_worktree(
    repo: str | Path,
    target: str | Path,
    *,
    force: bool = False,
    delete_branch: bool = False,
) -> None:
    """Remove a registered worktree; refuse a dirty one unless ``force``.

    Only paths contained in the repository root are accepted. Reusing or
    removing a worktree whose worker is still alive is the caller's
    responsibility — see the process-cleanup note in this module's docstring.
    """
    root = repo_root(repo)
    worktree = _find_worktree(root, target)
    if not _contained(root, worktree):
        raise WorktreeError("path_escape", f"worktree escapes {root}: {worktree}")
    registered = {info.path: info for info in list_worktrees(root)}
    info = registered.get(str(worktree))
    if info is None:
        raise WorktreeError("unknown_worktree", f"not a registered worktree: {worktree}")
    if _worktree_dirty(worktree) and not force:
        raise WorktreeError("dirty_worktree", "worktree has local changes; pass force=True")
    _git_ok(root, "worktree", "remove", *(["--force"] if force else []), "--", str(worktree))
    if delete_branch and info.branch:
        _git_ok(root, "branch", "-d", "--", info.branch)


def prune_worktrees(repo: str | Path) -> None:
    """Prune stale administrative worktree records for a repository."""
    _git_ok(repo_root(repo), "worktree", "prune")


# ---------------------------------------------------------------------------
# Non-Git exact-file staging runtime
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StagedFile:
    rel: str
    baseline_sha256: str | None
    baseline_mode: int | None
    staged_sha256: str
    staged_mode: int


@dataclass(frozen=True)
class ApplyReport:
    applied: tuple[str, ...]
    created: tuple[str, ...]
    rolled_back: tuple[str, ...]
    preserved: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryReport:
    restored: tuple[str, ...]
    removed: tuple[str, ...]
    preserved: tuple[str, ...]
    state: str


def _normalize_claim(files: Iterable[Any]) -> tuple[str, ...]:
    if isinstance(files, (str, bytes, os.PathLike)):
        raise WorktreeError("invalid_claim", "files must be a list of relative paths")
    try:
        items = list(files)
    except TypeError:
        raise WorktreeError("invalid_claim", "files must be iterable") from None
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        rel = _normalize_rel(item, label="claimed file")
        if rel in seen:
            raise WorktreeError("duplicate_claim", f"duplicate claim: {rel}")
        seen.add(rel)
        result.append(rel)
    return tuple(result)


def _check_overlaps(paths: Iterable[str]) -> None:
    ordered = sorted(paths)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if right == left or right.startswith(left + "/") or left.startswith(right + "/"):
                raise WorktreeError("overlapping_claim", f"overlapping claims: {left} and {right}")


class ExactFileStaging:
    """A private staging area with exact ownership, journal and recovery.

    Instances are created by :func:`stage_exact_files`. Nothing here is a
    security boundary: the lock file is advisory and the whole design assumes
    the worker cooperates. Validate-before-write, backups and the journal make
    ordinary mistakes and interruptions recoverable, not malicious actors
    harmless.
    """

    def __init__(
        self,
        root: Path,
        stage_dir: Path,
        control_dir: Path,
        files: Mapping[str, StagedFile],
        *,
        task: str = "write",
    ) -> None:
        self.root = Path(os.path.realpath(str(root)))
        self.stage_dir = Path(os.path.realpath(str(stage_dir)))
        self.control_dir = Path(os.path.realpath(str(control_dir)))
        self.files: dict[str, StagedFile] = dict(files)
        self.task = task
        self.journal_path = self.control_dir / "journal.json"
        self.lock_path = self.control_dir / "lock.json"
        self.state = "staged"
        self._steps: dict[str, str] = {rel: "pending" for rel in self.files}
        self._sealed: dict[str, list[Any]] | None = None
        self._owns_base = False
        self._lock_token: str | None = None
        if self.journal_path.is_file():
            self._load_journal()

    def _load_journal(self) -> None:
        data = json.loads(self.journal_path.read_text(encoding="utf-8"))
        self.state = str(data.get("state", "staged"))
        self._steps = {str(k): str(v) for k, v in dict(data.get("steps", {})).items()}
        sealed = data.get("sealed")
        self._sealed = None if sealed is None else {str(k): list(v) for k, v in sealed.items()}

    def _journal(self) -> dict[str, Any]:
        return {
            "version": 1,
            "project_root": str(self.root),
            "stage_dir": str(self.stage_dir),
            "control_dir": str(self.control_dir),
            "task": self.task,
            "state": self.state,
            "files": [asdict(record) for record in self.files.values()],
            "steps": dict(self._steps),
            "sealed": self._sealed,
        }

    def _write_journal(self) -> None:
        payload = json.dumps(self._journal(), indent=2, sort_keys=True).encode("utf-8")
        _atomic_write_bytes(self.journal_path, payload, 0o600)

    def _original_path(self, rel: str) -> Path:
        return _resolve_within(self.root, rel, label="original file")

    def _staged_path(self, rel: str) -> Path:
        return _resolve_within(self.stage_dir, rel, allow_missing=False, label="staged file")

    def _backup_path(self, rel: str) -> Path:
        return _resolve_within(self.control_dir / "backups", rel, label="backup file")

    def _set_step(self, rel: str, status: str) -> None:
        self._steps[rel] = status
        self._write_journal()

    # -- validation ---------------------------------------------------------

    def validate(self) -> dict[str, tuple[str, int]]:
        """Validate staged scope and original baselines before any write.

        Out-of-scope files or directories in the staging tree, missing claims,
        post-seal edits and stale originals all fail closed. Returns the
        current staged ``sha256``/mode snapshot for each claimed file.
        """
        if not self.root.is_dir():
            raise WorktreeError("invalid_project_root", f"project root is gone: {self.root}")
        if not self.stage_dir.is_dir() or not self.control_dir.is_dir():
            raise WorktreeError("staging_missing", "staging or control directory is gone")
        if (_contained(self.root, self.stage_dir) or _contained(self.root, self.control_dir)
                or _contained(self.stage_dir, self.root)):
            raise WorktreeError("stage_overlap", "staging/control must be outside the project")

        expected_files = set(self.files)
        expected_dirs: set[str] = set()
        for rel in expected_files:
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            while parent:
                expected_dirs.add(parent)
                parent = parent.rsplit("/", 1)[0] if "/" in parent else ""

        seen_files: set[str] = set()
        seen_dirs: set[str] = set()
        for current, dirnames, filenames in os.walk(self.stage_dir, followlinks=False):
            base = Path(os.path.realpath(current))
            if not _contained(self.stage_dir, base):
                raise WorktreeError("path_escape", f"staging tree escapes: {current}")
            rel_dir = "" if base == self.stage_dir else base.relative_to(self.stage_dir).as_posix()
            for dirname in dirnames:
                child = base / dirname
                if child.is_symlink():
                    raise WorktreeError("symlink_path", f"symlink in staging tree: {child}")
                child_rel = f"{rel_dir}/{dirname}" if rel_dir else dirname
                seen_dirs.add(child_rel)
                if child_rel not in expected_dirs:
                    raise WorktreeError("out_of_scope", f"unexpected staging directory: {child_rel}")
            for filename in filenames:
                child = base / filename
                if child.is_symlink():
                    raise WorktreeError("symlink_path", f"symlink in staging tree: {child}")
                child_rel = f"{rel_dir}/{filename}" if rel_dir else filename
                seen_files.add(child_rel)
                if child_rel not in expected_files:
                    raise WorktreeError("out_of_scope", f"unexpected staging file: {child_rel}")

        missing = sorted(expected_files - seen_files)
        if missing:
            raise WorktreeError("staged_missing", f"claimed files missing from staging: {missing}")

        snapshot: dict[str, tuple[str, int]] = {}
        for rel, record in self.files.items():
            staged = self._staged_path(rel)
            current = (_sha256(staged), _mode(staged))
            if self._sealed is not None:
                expected = tuple(self._sealed[rel])
                if current != expected:
                    raise WorktreeError("staged_modified", f"staged file changed after seal: {rel}")
            snapshot[rel] = current

            original = self._original_path(rel)
            if record.baseline_sha256 is None:
                if original.exists() or original.is_symlink():
                    raise WorktreeError("baseline_mismatch", f"new file now exists: {rel}")
            else:
                if original.is_symlink() or not original.is_file():
                    raise WorktreeError("baseline_mismatch", f"original is not a regular file: {rel}")
                if (_sha256(original) != record.baseline_sha256
                        or _mode(original) != record.baseline_mode):
                    raise WorktreeError("baseline_mismatch", f"original changed since claim: {rel}")
        return snapshot

    def seal(self) -> dict[str, tuple[str, int]]:
        """Freeze the reviewed staged contents; later edits are rejected."""
        snapshot = self.validate()
        self._sealed = {rel: list(value) for rel, value in snapshot.items()}
        self.state = "sealed"
        self._write_journal()
        return snapshot

    # -- cooperative lock ---------------------------------------------------

    def acquire_lock(self, owner: str, *, force: bool = False) -> None:
        """Take the advisory lock. This is conflict prevention, not a sandbox."""
        if self.lock_path.exists():
            if not force:
                try:
                    held = self.lock_path.read_text(encoding="utf-8")[:200]
                except OSError:
                    held = "unknown"
                raise WorktreeError("lock_held", f"staging lock held: {held}")
            self.lock_path.unlink()
        payload = json.dumps({"owner": owner, "pid": os.getpid(), "journal": str(self.journal_path)})
        fd = os.open(str(self.lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        self._lock_token = f"{owner}:{os.getpid()}"

    def release_lock(self) -> None:
        if self._lock_token is None or not self.lock_path.exists():
            return
        self.lock_path.unlink()
        self._lock_token = None

    # -- apply / rollback ----------------------------------------------------

    def apply(self, *, force: bool = False) -> ApplyReport:
        """Validate everything, then install staged files atomically.

        Ordinary failures roll back from backups. A hard interruption
        (``KeyboardInterrupt``/``SystemExit``) leaves a journal in the
        ``applying`` state for :meth:`recover` to complete.
        """
        snapshot = self.validate()
        # Record exactly what will be installed. The values captured when the
        # area was claimed may be stale: the worker is expected to edit the
        # staged files. Rollback and recovery compare against these values.
        for rel, (digest, mode) in snapshot.items():
            self.files[rel] = replace(self.files[rel], staged_sha256=digest, staged_mode=mode)
        self.acquire_lock("apply", force=force)
        applied: list[str] = []
        created: list[str] = []
        self.state = "applying"
        self._steps = {rel: "pending" for rel in self.files}
        self._write_journal()
        try:
            for rel in self.files:
                _install_one(self, rel)
                applied.append(rel)
                if self.files[rel].baseline_sha256 is None:
                    created.append(rel)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            rolled, preserved = self._rollback(applied)
            self.state = "rolled_back"
            self._write_journal()
            if isinstance(exc, WorktreeError):
                raise
            raise WorktreeError("apply_failed", str(exc)) from exc
        else:
            self.state = "applied"
            self._write_journal()
            return ApplyReport(tuple(applied), tuple(created), (), ())
        finally:
            self.release_lock()

    def _rollback(self, applied: Iterable[str]) -> tuple[list[str], list[str]]:
        restored: list[str] = []
        preserved: list[str] = []
        for rel in reversed(list(applied)):
            record = self.files[rel]
            dest = self._original_path(rel)
            current = _sha256(dest) if dest.is_file() and not dest.is_symlink() else None
            if current != record.staged_sha256:
                preserved.append(rel)
                self._set_step(rel, "preserved")
                continue
            if record.baseline_sha256 is None:
                if dest.exists():
                    dest.unlink()
                restored.append(rel)
            else:
                backup = self._backup_path(rel)
                if not backup.is_file():
                    raise WorktreeError("backup_missing", f"no backup for {rel}")
                _atomic_write_bytes(dest, backup.read_bytes(), int(record.baseline_mode or 0o644))
                restored.append(rel)
            self._set_step(rel, "restored")
        return restored, preserved

    def restore_backups(self, *, force: bool = False) -> tuple[str, ...]:
        """Restore applied originals from backups, preserving later edits."""
        self.acquire_lock("restore", force=force)
        try:
            applied = [rel for rel in self.files if self._steps.get(rel) == "applied"]
            restored, _ = self._rollback(applied)
            self.state = "restored"
            self._write_journal()
            return tuple(restored)
        finally:
            self.release_lock()

    # -- interrupted-apply recovery -----------------------------------------

    def recover(self, *, force: bool = False) -> RecoveryReport:
        """Finish an interrupted apply without clobbering later user edits.

        A step is undone only when the current original still has exactly the
        bytes this runtime wrote. Any other content is treated as a later user
        change and left alone.
        """
        if self.state != "applying":
            return RecoveryReport((), (), (), self.state)
        self.acquire_lock("recovery", force=force)
        restored: list[str] = []
        removed: list[str] = []
        preserved: list[str] = []
        try:
            for rel in reversed(list(self.files)):
                status = self._steps.get(rel, "pending")
                if status != "applied":
                    continue  # nothing was installed for this file
                record = self.files[rel]
                dest = self._original_path(rel)
                current = _sha256(dest) if dest.is_file() and not dest.is_symlink() else None
                if current != record.staged_sha256:
                    preserved.append(rel)
                    self._set_step(rel, "preserved")
                    continue
                if record.baseline_sha256 is None:
                    if dest.exists():
                        dest.unlink()
                    removed.append(rel)
                else:
                    backup = self._backup_path(rel)
                    if not backup.is_file():
                        raise WorktreeError("backup_missing", f"no backup for {rel}")
                    _atomic_write_bytes(dest, backup.read_bytes(),
                                        int(record.baseline_mode or 0o644))
                    restored.append(rel)
                self._set_step(rel, "restored")
            self.state = "recovered"
            self._write_journal()
            return RecoveryReport(tuple(restored), tuple(removed), tuple(preserved), self.state)
        finally:
            self.release_lock()

    def dispose(self) -> None:
        """Delete the private staging/control trees (never the project)."""
        if self.state == "applying":
            raise WorktreeError("apply_in_progress", "recover before disposing a staging area")
        base = self.control_dir.parent
        if not _contained(base, self.stage_dir) or not _contained(base, self.control_dir):
            raise WorktreeError("path_escape", "staging trees are not under the same base")
        if _contained(self.root, base):
            raise WorktreeError("stage_overlap", "refusing to delete inside the project")
        shutil.rmtree(base, ignore_errors=True)
        self._owns_base = False


def _install_one(area: ExactFileStaging, rel: str) -> None:
    """Back up and atomically install a single claimed file.

    Kept as a module-level function so drivers can inject failure/restart
    hooks in tests without patching instance internals.
    """
    record = area.files[rel]
    dest = area._original_path(rel)
    source = area._staged_path(rel)
    if _sha256(source) != record.staged_sha256 or _mode(source) != record.staged_mode:
        raise WorktreeError("staged_modified", f"staged file changed during apply: {rel}")
    if record.baseline_sha256 is None:
        if dest.exists() or dest.is_symlink():
            raise WorktreeError("baseline_mismatch", f"new file now exists: {rel}")
        area._set_step(rel, "intended")
        _atomic_write_bytes(dest, source.read_bytes(), record.staged_mode)
        area._set_step(rel, "applied")
        return
    if dest.is_symlink() or not dest.is_file():
        raise WorktreeError("baseline_mismatch", f"original is not a regular file: {rel}")
    if (_sha256(dest) != record.baseline_sha256 or _mode(dest) != record.baseline_mode):
        raise WorktreeError("baseline_mismatch", f"original changed since claim: {rel}")
    area._set_step(rel, "intended")
    backup = area._backup_path(rel)
    _atomic_write_bytes(backup, dest.read_bytes(), int(record.baseline_mode or 0o644))
    area._set_step(rel, "backed_up")
    _atomic_write_bytes(dest, source.read_bytes(), record.staged_mode)
    area._set_step(rel, "applied")


def stage_exact_files(
    project_root: str | Path,
    files: Iterable[Any],
    *,
    stage_root: str | Path | None = None,
    task: str = "write",
    name: str | None = None,
) -> ExactFileStaging:
    """Claim exact relative files and copy only those files to a staging dir.

    A write task with an empty claim is rejected. Missing claimed files are
    represented by an empty staged placeholder so that a new file is still an
    explicit, reviewable part of the claim.
    """
    root = Path(os.path.realpath(os.fspath(project_root)))
    if not root.is_dir():
        raise WorktreeError("invalid_project_root", f"not a directory: {root}")
    claimed = _normalize_claim(files)
    if not claimed and task in _WRITE_TASKS:
        raise WorktreeError("empty_claim", "write tasks must claim at least one file")
    _check_overlaps(claimed)

    if stage_root is None:
        base = Path(tempfile.mkdtemp(prefix="keel-stage-"))
        owns_base = True
    else:
        base = Path(os.path.realpath(os.fspath(stage_root)))
        base.mkdir(parents=True, exist_ok=True)
        owns_base = False
    if _contained(root, base) or _contained(base, root):
        raise WorktreeError("stage_overlap", "staging root must not overlap the project root")

    safe_name = _normalize_rel(name or f"stage-{uuid.uuid4().hex[:12]}", label="stage name")
    work = base / safe_name
    stage_dir = work / "staging"
    control_dir = work / "control"
    stage_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    staged: dict[str, StagedFile] = {}
    for rel in claimed:
        source = _resolve_within(root, rel, allow_missing=True, label="claimed file")
        destination = _resolve_within(stage_dir, rel, label="staged destination")
        if source.is_symlink() or not _contained(root, source):
            raise WorktreeError("symlink_path", f"claimed file may not be a symlink: {rel}")
        if source.is_dir():
            raise WorktreeError("unsupported_file_type", f"claim names a directory: {rel}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            shutil.copyfile(source, destination)
            baseline_hash: str | None = _sha256(source)
            baseline_mode: int | None = _mode(source)
            os.chmod(destination, int(baseline_mode or 0o644))
        else:
            _atomic_write_bytes(destination, b"", 0o644)
            baseline_hash, baseline_mode = None, None
        staged[rel] = StagedFile(
            rel=rel,
            baseline_sha256=baseline_hash,
            baseline_mode=baseline_mode,
            staged_sha256=_sha256(destination),
            staged_mode=_mode(destination),
        )

    area = ExactFileStaging(root, stage_dir, control_dir, staged, task=task)
    area._owns_base = owns_base
    area._write_journal()
    return area


def recover_interrupted_apply(
    control_dir: str | Path,
    *,
    project_root: str | Path | None = None,
    force: bool = False,
) -> RecoveryReport:
    """Rebuild a staging area from its journal and recover an interrupted apply."""
    control = Path(os.path.realpath(os.fspath(control_dir)))
    journal = control / "journal.json"
    if not journal.is_file():
        raise WorktreeError("journal_missing", f"no journal at {journal}")
    data = json.loads(journal.read_text(encoding="utf-8"))
    root = Path(os.path.realpath(os.fspath(project_root or data["project_root"])))
    stage_dir = Path(os.path.realpath(str(data["stage_dir"])))
    files: dict[str, StagedFile] = {}
    for entry in data.get("files", []):
        record = StagedFile(
            rel=str(entry["rel"]),
            baseline_sha256=entry.get("baseline_sha256"),
            baseline_mode=entry.get("baseline_mode"),
            staged_sha256=str(entry["staged_sha256"]),
            staged_mode=int(entry["staged_mode"]),
        )
        files[record.rel] = record
    area = ExactFileStaging(root, stage_dir, control, files, task=str(data.get("task", "write")))
    area.state = str(data.get("state", "staged"))
    area._steps = {str(k): str(v) for k, v in dict(data.get("steps", {})).items()}
    return area.recover(force=force)
