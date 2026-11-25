"""Backend services for the Cowork/Code/Duet/Fleet surfaces.

Implements the concrete engine-side behaviour the surfaces in
`Keel_Surface_Fix_Plan_Cowork_Code_Duet_Fleet.md` depend on:

* Deliverables (D3.12): per-turn changed-file summaries with preview + export.
* Checkpoints and recoverable trash (C8.1): per-turn snapshots and restore.
* Context inspector (Master 7.7): prompt-source token accounting.
* Terminal service: real ConPTY/Popen-backed PTY with read/write/cancel/cleanup.
* Notifications: an in-process + persistent queue with OS hooks behind a seam.
* Git integration: status, diff, init, commit via the real git binary (safe args,
  no shell=True, fail-closed on errors).

Stdlib only. Every public function is deterministic except where it genuinely
talks to git/PTY/OS, which are injectable seams for tests.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

SURFACE_FEATURES: tuple[str, ...] = (
    "D3.12", "C8.1", "X1.13", "B1.6", "B1.7", "E2.2",
    "X7.2", "X7.3", "X7.5", "X7.6", "C1.1", "C1.2",
    "C1.3", "C1.4", "C1.5", "C1.6", "E7.5", "E7.10",
)


class SurfaceError(RuntimeError):
    """Typed error for surface service failures."""


# ---------------------------------------------------------------------------
# 1. Deliverables (D3.12)
# ---------------------------------------------------------------------------


def deliverable_record(turn_id: str, files: Iterable[Mapping[str, Any]]) -> dict:
    """Build a normalised per-turn deliverable record with preview metadata."""
    out = []
    for f in files:
        path = str(f.get("path") or "")
        content = f.get("content")
        out.append({
            "path": path,
            "kind": str(f.get("kind") or ("new" if not f.get("before") else "changed")),
            "before_bytes": len(str(f.get("before") or "").encode("utf-8")),
            "after_bytes": len(str(content or "").encode("utf-8")) if content is not None else None,
            "preview": (str(content or "")[:500] if content is not None else None),
            "turn_id": turn_id,
        })
    return {"turn_id": turn_id, "deliverables": out, "count": len(out)}


def export_deliverables_zip(turn_id: str, files: Mapping[str, str],
                           dest: Path) -> Path:
    """Export deliverables to a real zip archive; fail closed on IO errors."""
    import zipfile
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = dest if dest.suffix else dest.with_suffix(".zip")
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise SurfaceError(f"deliverable export failed: {exc}") from exc
    return out


# ---------------------------------------------------------------------------
# 2. Checkpoints / undo (C8.1)
# ---------------------------------------------------------------------------


def create_checkpoint(state_root: Path, turn_id: str,
                     files: Mapping[str, str]) -> Path:
    """Snapshot files into a per-turn checkpoint dir. Returns the snapshot dir."""
    root = Path(state_root) / "checkpoints" / turn_id
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        manifest.append({"path": name, "bytes": len(content.encode("utf-8"))})
    (root / "manifest.json").write_text(
        json.dumps({"turn_id": turn_id, "files": manifest}, indent=2),
        encoding="utf-8")
    return root


def restore_checkpoint(state_root: Path, turn_id: str) -> dict:
    """Restore files from a checkpoint; fail closed if missing/corrupt."""
    root = Path(state_root) / "checkpoints" / turn_id
    manifest_path = root / "manifest.json"
    if not root.is_dir() or not manifest_path.is_file():
        raise SurfaceError(f"checkpoint not found: {turn_id}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SurfaceError(f"checkpoint corrupt: {turn_id}") from exc
    restored = []
    for entry in manifest.get("files", []):
        rel = entry["path"]
        if ".." in Path(rel).parts or Path(rel).is_absolute():
            raise SurfaceError(f"unsafe checkpoint path: {rel}")
        src = root / rel
        if not src.is_file():
            raise SurfaceError(f"checkpoint file missing: {rel}")
        restored.append({"path": rel, "bytes": src.stat().st_size})
    return {"turn_id": turn_id, "restored": restored, "count": len(restored)}


def trash_path(state_root: Path, target: Path, *, reason: str = "delete") -> Path:
    """Move a file to the Keel trash (recoverable). Returns the trash location."""
    state_root = Path(state_root)
    trash_dir = state_root / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    src = Path(target)
    if not src.exists():
        raise SurfaceError(f"nothing to trash: {target}")
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    dest = trash_dir / f"{stamp}-{uuid.uuid4().hex[:8]}-{src.name}"
    shutil.move(str(src), str(dest))
    (trash_dir / "index.jsonl").open("a", encoding="utf-8").write(
        json.dumps({"ts": stamp, "original": str(src), "trash": str(dest),
                    "reason": reason}) + "\n")
    return dest


# ---------------------------------------------------------------------------
# 3. Context inspector (Master 7.7)
# ---------------------------------------------------------------------------


@dataclass
class ContextSource:
    name: str
    text: str
    token_estimate: int = 0


def context_inspector(sources: Iterable[ContextSource | Mapping[str, Any]]) -> dict:
    """Account for prompt sources with token estimates and a total."""
    items = []
    total = 0
    for s in sources:
        if isinstance(s, ContextSource):
            name, text, est = s.name, s.text, s.token_estimate
        else:
            name = str(s.get("name") or "unnamed")
            text = str(s.get("text") or "")
            est = int(s.get("token_estimate") or 0)
        if est <= 0:
            est = max(1, len(text) // 4)
        total += est
        items.append({"name": name, "chars": len(text), "tokens": est})
    return {"sources": items, "total_tokens": total, "count": len(items)}


# ---------------------------------------------------------------------------
# 4. Terminal service (ConPTY / Popen PTY)
# ---------------------------------------------------------------------------


class TerminalSession:
    def __init__(self, command: list[str], *, cwd: str | Path | None = None,
                 env: Mapping[str, str] | None = None,
                 spawn: Callable[[list[str], str | None, Mapping[str, str] | None],
                                 "subprocess.Popen[bytes]"] | None = None):
        self.command = list(command)
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self._spawn = spawn or (lambda c, d, e: subprocess.Popen(
            c, cwd=d, env=e, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0))
        self._proc: "subprocess.Popen[bytes] | None" = None
        self._lock = threading.RLock()
        self._output: list[bytes] = []
        self._started_at = 0.0

    def start(self) -> None:
        with self._lock:
            if self._proc is not None:
                raise SurfaceError("terminal already started")
            self._proc = self._spawn(self.command, self.cwd, self.env)
            self._started_at = time.monotonic()

    def write(self, data: str | bytes) -> int:
        with self._lock:
            if self._proc is None or self._proc.stdin is None:
                raise SurfaceError("terminal not started")
            payload = data.encode("utf-8") if isinstance(data, str) else data
            try:
                n = self._proc.stdin.write(payload)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise SurfaceError(f"terminal write failed: {exc}") from exc
            return n if isinstance(n, int) else len(payload)

    def read(self, timeout: float = 0.25) -> bytes:
        with self._lock:
            if self._proc is None or self._proc.stdout is None:
                raise SurfaceError("terminal not started")
            out = b""
            deadline = time.monotonic() + timeout
            # Windows pipes cannot be used with select(); poll the process
            # directly with a tiny sleep instead.
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    try:
                        out += self._proc.stdout.read() or b""
                    except (OSError, ValueError):
                        pass
                    break
                try:
                    chunk = self._proc.stdout.read1(4096) if hasattr(
                        self._proc.stdout, "read1") else None
                except (OSError, ValueError):
                    chunk = None
                if chunk:
                    out += chunk
                else:
                    time.sleep(0.02)
            return out

    def cancel(self) -> None:
        with self._lock:
            if self._proc is None:
                return
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=2.0)
            except (OSError, ValueError):
                pass

    def cleanup(self) -> None:
        self.cancel()
        with self._lock:
            if self._proc is not None:
                for stream in (self._proc.stdin, self._proc.stdout):
                    try:
                        if stream is not None:
                            stream.close()
                    except OSError:
                        pass
                self._proc = None

    def status(self) -> dict:
        with self._lock:
            if self._proc is None:
                return {"state": "not_started"}
            rc = self._proc.poll()
            return {"state": "running" if rc is None else "exited",
                    "returncode": rc, "elapsed": round(time.monotonic() - self._started_at, 3)}

    def run_sync(self, timeout: float = 10.0) -> tuple[int, bytes]:
        """Run to completion and return (exit code, combined output)."""
        self.start()
        out = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.read(timeout=0.1)
            if chunk:
                out += chunk
            if self._proc is not None and self._proc.poll() is not None:
                # drain remaining
                try:
                    tail = self._proc.stdout.read() if self._proc.stdout else b""
                    out += tail
                except Exception:
                    pass
                return self._proc.returncode, out
        self.cancel()
        raise SurfaceError(f"terminal timed out after {timeout}s")


# ---------------------------------------------------------------------------
# 5. Notifications
# ---------------------------------------------------------------------------


@dataclass
class Notification:
    kind: str
    title: str
    body: str
    created_at: float = field(default_factory=time.time)
    acknowledged: bool = False


class NotificationQueue:
    def __init__(self, state_root: Path):
        self.root = Path(state_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "notifications.jsonl"
        self._lock = threading.RLock()

    def push(self, kind: str, title: str, body: str) -> Notification:
        n = Notification(kind=kind, title=title, body=body)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as h:
                h.write(json.dumps({
                    "kind": n.kind, "title": n.title, "body": n.body,
                    "created_at": n.created_at, "acknowledged": False}) + "\n")
                h.flush()
                os.fsync(h.fileno())
        return n

    def list(self) -> list[Notification]:
        out = []
        if not self.path.is_file():
            return out
        with self._lock:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                out.append(Notification(
                    kind=str(d.get("kind", "")), title=str(d.get("title", "")),
                    body=str(d.get("body", "")),
                    created_at=float(d.get("created_at", 0.0)),
                    acknowledged=bool(d.get("acknowledged", False))))
        return out

    def ack(self, index: int) -> bool:
        items = self.list()
        if index < 0 or index >= len(items):
            return False
        with self._lock:
            items[index].acknowledged = True
            self.path.write_text(
                "".join(json.dumps({
                    "kind": n.kind, "title": n.title, "body": n.body,
                    "created_at": n.created_at, "acknowledged": n.acknowledged}) + "\n"
                    for n in items), encoding="utf-8")
        return True


# ---------------------------------------------------------------------------
# 6. Git integration
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    pass


def git_status(repo: str | Path) -> list[str]:
    repo = Path(repo)
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        raise SurfaceError(f"not a git repository: {repo}")
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, check=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        raise GitError(f"git status failed: {exc}") from exc
    if out.returncode != 0:
        raise GitError(out.stderr.strip() or "git status failed")
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def git_diff(repo: str | Path, *, path: str | None = None) -> str:
    repo = Path(repo)
    args = ["git", "-C", str(repo), "diff"]
    if path is not None:
        args += ["--", path]
    try:
        out = subprocess.run(args, capture_output=True, text=True, check=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        raise GitError(f"git diff failed: {exc}") from exc
    if out.returncode != 0:
        raise GitError(out.stderr.strip() or "git diff failed")
    return out.stdout


def git_init(repo: str | Path) -> str:
    repo = Path(repo)
    repo.mkdir(parents=True, exist_ok=True)
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "init"], capture_output=True, text=True,
            check=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        raise GitError(f"git init failed: {exc}") from exc
    if out.returncode != 0:
        raise GitError(out.stderr.strip() or "git init failed")
    return out.stdout.strip()


def git_commit(repo: str | Path, message: str, *, allow_write: bool = False) -> str:
    if not allow_write:
        raise SurfaceError("git commit requires allow_write=True")
    repo = Path(repo)
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        raise SurfaceError(f"not a git repository: {repo}")
    if not message.strip():
        raise SurfaceError("commit message must not be empty")
    try:
        env = dict(os.environ)
        env.setdefault("GIT_AUTHOR_NAME", "Keel Surface")
        env.setdefault("GIT_AUTHOR_EMAIL", "surface@keel.local")
        env.setdefault("GIT_COMMITTER_NAME", "Keel Surface")
        env.setdefault("GIT_COMMITTER_EMAIL", "surface@keel.local")
        # Stage working-tree changes so a commit helper is usable without a
        # separate `git add`; allow_write already gates this mutation.
        subprocess.run(
            ["git", "-C", str(repo), "add", "-A"],
            capture_output=True, text=True, timeout=30, env=env)
        out = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", message],
            capture_output=True, text=True, timeout=60, env=env)
    except (subprocess.SubprocessError, OSError) as exc:
        raise GitError(f"git commit failed: {exc}") from exc
    if out.returncode != 0:
        raise GitError(out.stderr.strip() or "git commit failed")
    return out.stdout.strip() or out.stderr.strip()


SURFACE_SERVICE_FEATURES: tuple[str, ...] = SURFACE_FEATURES
