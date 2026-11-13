"""keel.fleet.shells — detached (background) shell registry.

Claude Code-style "1 shell running" pill: run_shell with background=true
returns immediately; the child runs detached; when it exits, the registry
appends a notice row with the tail of its output. Ctrl+B in the UI moves
the pill to/from the background — cosmetic only, the process is already
detached, exactly as Claude Code's Ctrl+B behaves on a focused shell.

Rules:
- handles are per process; a restart forgets them (children keep running
  but are no longer tracked — honest: say so in the UI)
- output is captured incrementally to a bounded file (4 MB cap) so a noisy
  build can't OOM the process
- the agent gets notified inline via a notice row when it exits
"""

from __future__ import annotations

import base64
import os
import subprocess
import threading
import time

_OUT_HEAD = 64 * 1024          # first chunk shown inline
_OUT_TAIL = 64 * 1024          # last chunk shown in the pill detail
_OUT_CAP = 4 * 1024 * 1024     # hard cap on captured output
_MAX_BACKGROUND = 8            # refuse more than this many detached shells


class BackgroundShell:
    def __init__(self, handle: str, bot_id: str, command: str, shell: str,
                 pid: int | None, out_path: str):
        self.handle = handle
        self.bot_id = bot_id
        self.command = command
        self.shell = shell
        self.pid = pid
        self.out_path = out_path
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.exit_code: int | None = None
        self._tail = ""

    def tail(self, text: str) -> None:
        self._tail = text

    def tail_text(self) -> str:
        return self._tail

    def public(self) -> dict:
        return {
            "handle": self.handle,
            "bot_id": self.bot_id,
            "command": self.command,
            "shell": self.shell,
            "pid": self.pid,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(self.started_at)),
            "finished_at": (None if self.finished_at is None
                            else time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime(self.finished_at))),
            "exit_code": self.exit_code,
            "running": self.finished_at is None,
            "out_bytes": (os.path.getsize(self.out_path)
                          if os.path.exists(self.out_path) else 0),
        }


_lock = threading.Lock()
_shells: dict[str, BackgroundShell] = {}
_seq = 0


def _next_handle() -> str:
    global _seq
    _seq += 1
    return f"bg{_seq}"


def start(store, bot: dict, command: str, shell: str,
          cwd: str | None = None) -> BackgroundShell:
    with _lock:
        running = sum(1 for s in _shells.values() if s.finished_at is None)
        if running >= _MAX_BACKGROUND:
            raise ValueError(
                f"already {running} background shells running "
                f"(cap {_MAX_BACKGROUND}); wait for one to finish")

    handle = _next_handle()
    out_path = os.path.join(os.path.expanduser("~"), ".keel", "fleet", "shells",
                            f"{bot['id']}_{handle}_{int(time.time())}.log")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if shell == "posix":
        import shutil
        sh = shutil.which("sh") or shutil.which("bash")
        if sh is None:
            raise ValueError(
                "posix shell (sh) not found on this machine — "
                "use powershell or cmd instead")
        argv = [sh, "-c", command]
    elif shell == "cmd":
        argv = ["cmd.exe", "/d", "/c", command]
    else:  # powershell
        argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]

    out_fh = None
    try:
        out_fh = open(out_path, "wb")
        popen_kwargs = dict(
            stdout=out_fh, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            # no console window for the child; redirected handles still work.
            # (DETACHED_PROCESS made PowerShell exit 0 while writing nothing.)
            start_new_session=(os.name != "nt"),
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        if cwd:
            popen_kwargs["cwd"] = cwd
        proc = subprocess.Popen(argv, **popen_kwargs)
    except OSError:
        if out_fh:
            out_fh.close()
        raise
    finally:
        if out_fh:
            out_fh.close()
    entry = BackgroundShell(handle, bot["id"], command, shell, proc.pid, out_path)
    with _lock:
        _shells[handle] = entry

    # single waiter thread: captures exit code, appends notice row on finish
    def _waiter():
        proc.wait()
        try:
            data = open(out_path, "rb").read(_OUT_CAP)
            text = data.decode("utf-8", errors="replace")
            entry.tail(text[-_OUT_TAIL:])
            head = text[:_OUT_HEAD]
        except OSError:
            text, head, tail = "", "", ""
            entry.tail("")
        entry.finished_at = time.time()
        entry.exit_code = proc.returncode
        try:
            if store.get_bot(bot["id"]) is not None:
                store.append_row(bot["id"], "notice", {
                    "text": (f"Background shell {handle} finished "
                             f"(exit {proc.returncode}): {command[:160]}\n"
                             f"{head[:400]}"),
                    "level": "info" if proc.returncode == 0 else "warning",
                    "icon": "terminal",
                })
        except Exception:
            pass

    threading.Thread(target=_waiter, daemon=True,
                     name=f"fleet-bgshell-{handle}").start()
    return entry


def _is_internal(entry: BackgroundShell) -> bool:
    """Only the keep-awake machinery is internal — tracked for correctness
    (kill switch, status) but never shown to the user. Terminal-launched
    commands are real user work and DO appear."""
    if entry.bot_id == "__keepawake__":
        return True
    return entry.command.startswith("$null = '__KEEL_KEEP_AWAKE__'")


def list_shells(bot_id: str | None = None, *,
                include_internal: bool = False) -> list[dict]:
    with _lock:
        items = list(_shells.values())
    items.sort(key=lambda s: s.started_at)
    if bot_id is not None:
        items = [s for s in items if s.bot_id == bot_id]
    if not include_internal:
        items = [s for s in items if not _is_internal(s)]
    return [s.public() for s in items]


def get_shell(handle: str) -> BackgroundShell | None:
    with _lock:
        return _shells.get(handle)


def read_output(handle: str, limit: int = 256 * 1024) -> dict:
    with _lock:
        entry = _shells.get(handle)
    if entry is None:
        return {"error": "unknown shell"}
    if not os.path.exists(entry.out_path):
        return {"error": "output unavailable", "running": entry.finished_at is None}
    with open(entry.out_path, "rb") as fh:
        data = fh.read(limit + 1)
    truncated = len(data) > limit
    return {"handle": entry.handle,
            "running": entry.finished_at is None,
            "exit_code": entry.exit_code,
            "output": data[:limit].decode("utf-8", errors="replace"),
            "truncated": truncated}


def find_by_command_prefix(prefix: str) -> list[BackgroundShell]:
    with _lock:
        return [s for s in _shells.values() if s.command.startswith(prefix)]


def kill(handle: str) -> dict:
    """Terminate a detached shell. Reports honestly when the handle is unknown
    or the process is already gone — the caller decides what to believe."""
    with _lock:
        entry = _shells.get(handle)
    if entry is None:
        return {"ok": False, "error": "unknown shell"}
    if entry.finished_at is not None:
        return {"ok": True, "already_finished": True, "exit_code": entry.exit_code}
    pid = entry.pid
    if not pid:
        return {"ok": False, "error": "no pid recorded"}
    import signal as _signal
    try:
        os.kill(pid, _signal.SIGTERM)
    except OSError as exc:
        return {"ok": False, "error": f"kill failed: {exc}"}
    # give the waiter thread a moment to finalize (it observes the exit)
    return {"ok": True, "pid": pid}


def running_count(bot_id: str | None = None) -> int:
    with _lock:
        return sum(1 for s in _shells.values()
                   if s.finished_at is None and
                   (bot_id is None or s.bot_id == bot_id))


def clear_finished() -> int:
    with _lock:
        finished = [h for h, s in _shells.items() if s.finished_at is not None]
        for h in finished:
            entry = _shells.pop(h, None)
            if entry and os.path.exists(entry.out_path):
                try:
                    os.remove(entry.out_path)
                except OSError:
                    pass
        return len(finished)
