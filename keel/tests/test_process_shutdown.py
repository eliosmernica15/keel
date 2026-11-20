"""Process-tree shutdown test.

The background command starts a Python helper, which starts one long-running
child. Both PIDs are written to disk by the helper. The test asserts that:

* exactly one valid child PID was recorded,
* the background process, the helper and the child are alive before cleanup,
* ``cleanup_background_processes()`` terminates all of them.

Missing or malformed PID data fails the test immediately; it never degrades
into a vacuous "zero children were checked" pass.
"""

from __future__ import annotations

import ctypes
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

_STILL_ACTIVE = 259


def _pid_alive(pid: int) -> bool:
    """Return True only while *pid* is a live (non-zombie) process."""
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            process_query_limited_information, False, int(pid))
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    # A zombie has already terminated. Linux exposes this through /proc;
    # macOS and the BSDs are covered by ps(1).
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.is_file():
        try:
            state = proc_stat.read_text(encoding="utf-8").split()[2]
            if state == "Z":
                return False
        except (OSError, IndexError):
            pass
    try:
        ps = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True, text=True, timeout=5,
        )
        if ps.returncode != 0:
            return False
        if ps.stdout.strip().startswith("Z"):
            return False
    except (OSError, subprocess.SubprocessError):
        pass
    return True


def _wait_dead(pids: list[int], timeout: float = 15.0) -> list[int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        alive = [pid for pid in pids if _pid_alive(pid)]
        if not alive:
            return []
        time.sleep(0.1)
    return [pid for pid in pids if _pid_alive(pid)]


@pytest.fixture
def background_spawner(tmp_path):
    """Start a background shell whose helper spawns one long-running child."""
    helper = tmp_path / "spawner.py"
    helper.write_text(
        "\n".join([
            "import json, os, subprocess, sys, time",
            "pid_file = sys.argv[1]",
            "child = subprocess.Popen([sys.executable, '-c', "
            "'import time; time.sleep(300)'])",
            "with open(pid_file, 'w', encoding='utf-8') as fh:",
            "    json.dump({'parent': os.getpid(), 'children': [child.pid]}, fh)",
            "time.sleep(300)",
            "",
        ]),
        encoding="utf-8",
    )
    pid_file = tmp_path / "pids.json"
    command = subprocess.list2cmdline(
        [sys.executable, str(helper), str(pid_file)])
    shell = "cmd" if os.name == "nt" else "posix"
    if os.name != "nt":
        command = shlex.join([sys.executable, str(helper), str(pid_file)])

    sys.path.insert(0, str(SRC))
    from keel.runner import RealTools

    tools = RealTools()
    _, payload = tools._background_shell({"command": command, "shell": shell})
    background_pid = int(payload["pid"])
    try:
        yield {
            "tools": tools,
            "background_pid": background_pid,
            "pid_file": pid_file,
        }
    finally:
        from keel.runner import cleanup_background_processes

        cleanup_background_processes()


def _read_recorded_pids(pid_file: Path) -> tuple[int, list[int]]:
    deadline = time.monotonic() + 15.0
    last_error: object = None
    while time.monotonic() < deadline:
        if pid_file.is_file():
            try:
                doc = json.loads(pid_file.read_text(encoding="utf-8"))
                parent = doc["parent"]
                children = doc["children"]
                if isinstance(parent, int) and isinstance(children, list):
                    return parent, children
            except (OSError, ValueError, KeyError, TypeError) as exc:
                last_error = exc
        time.sleep(0.05)
    pytest.fail(f"PID file was not written with valid data: {last_error!r}")


def test_process_shutdown_cleanup(background_spawner):
    from keel.runner import RealTools, cleanup_background_processes

    background_pid = background_spawner["background_pid"]
    assert background_pid > 0

    helper_pid, children = _read_recorded_pids(background_spawner["pid_file"])

    # Exactly one child must have been recorded. An empty list is a test
    # failure, not a reason to skip the child-termination assertion.
    assert helper_pid > 0, f"invalid helper PID: {helper_pid!r}"
    assert isinstance(children, list), f"children is not a list: {children!r}"
    assert len(children) == 1, (
        f"expected exactly 1 recorded child PID, got {len(children)}: {children!r}")
    child_pid = children[0]
    assert isinstance(child_pid, int) and child_pid > 0, (
        f"invalid child PID: {child_pid!r}")
    assert child_pid != helper_pid, "child PID must differ from helper PID"

    recorded = [background_pid, helper_pid, child_pid]
    for pid in recorded:
        assert _pid_alive(pid), (
            f"pid {pid} was not alive before cleanup; recorded={recorded}")

    killed = cleanup_background_processes()
    assert killed >= 1, f"cleanup reported no killed processes: {killed}"

    still_alive = _wait_dead(recorded)
    assert not still_alive, (
        "process tree survived cleanup: "
        f"alive={still_alive}; background={background_pid}; "
        f"helper={helper_pid}; child={child_pid}")
    assert RealTools._BG_PROCESSES == {}, (
        f"tracked background processes were not cleared: "
        f"{RealTools._BG_PROCESSES!r}")
