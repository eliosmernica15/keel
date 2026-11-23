"""Adversarial tests for the native Linux sandbox backend.

Every test on Linux launches *real* restricted child processes.  A failure to
apply the kernel boundary is a test failure (``SandboxUnavailable`` is never
converted into a skip here) -- see F6 in the accompanying research note.
Non-Linux runners skip the whole module cleanly.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from keel.sandbox_linux import (
    capabilities,
    landlock_abi,
    build_network_filter,
    install_network_filter,
    run_confined,
    PR_SET_NO_NEW_PRIVS,
    _LIBC,
)

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="native Landlock/seccomp confinement is Linux-only",
)

LINUX = sys.platform.startswith("linux")
SECRET = "TOP-SECRET-DO-NOT-LEAK"


def _workspace(tmp_path: Path, name: str = "workspace") -> Path:
    ws = tmp_path / name
    ws.mkdir()
    return ws


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


# ---------------------------------------------------------------------------
# Capability / pre-flight evidence (F7)
# ---------------------------------------------------------------------------
def test_capabilities_report_real_preflight_enforcement():
    caps = capabilities()
    assert caps["os"] == sys.platform
    assert caps["linux_landlock"] is True
    assert caps["linux_seccomp"] is True
    assert caps["linux_landlock_abi"] >= 1
    # These are derived from an actually-restricted forked child, not from
    # feature detection or from a try/except that swallows failure.
    assert caps["filesystem_enforcement"] is True
    assert caps["network_enforcement"] is True
    assert "fs_denied=True" in caps["preflight_evidence"]
    assert "net_denied=True" in caps["preflight_evidence"]
    # F8: honest documentation that bwrap/unshare are not used here.
    assert any("bwrap" in item for item in caps["limitations"])


def test_landlock_abi_query_is_real():
    from keel.sandbox_linux import SYS_LANDLOCK_CREATE_RULESET
    assert landlock_abi() >= 1
    assert SYS_LANDLOCK_CREATE_RULESET == 444


# ---------------------------------------------------------------------------
# BPF filter structure + forked-child behaviour (F1)
# ---------------------------------------------------------------------------
def test_bpf_program_uses_correct_load_and_return_actions():
    insns = build_network_filter()
    # BPF_LD | BPF_W | BPF_ABS == 0x20, offsetof(seccomp_data.nr) == 0.
    assert insns[0][0] == 0x20
    assert insns[0][3] == 0
    # socket() == 41 must branch to EPERM, not to KILL_THREAD.
    assert (0x15, 0, 1, 41) in insns           # jeq 41, jt=0, jf=1
    assert (0x06, 0, 0, 0x00050001) in insns   # ret ERRNO|EPERM
    assert insns[-1] == (0x06, 0, 0, 0x7FFF0000)  # default ALLOW
    # The broken opcode / offset / action from os_sandbox.py must be absent.
    assert (0x00, 0, 0, 4) not in insns
    assert (0x06, 0, 0, 1) not in insns


def test_network_filter_forked_child_socket_denied_write_ok():
    """Fork a child, install only the BPF filter, verify real behaviour."""
    assert _LIBC is not None
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:  # child
        os.close(read_fd)
        try:
            assert _LIBC.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0
            install_network_filter()
            os.write(write_fd, b"WRITE_OK\n")
            try:
                import socket as child_socket
                child_socket.socket()
                os.write(write_fd, b"SOCKET_OK\n")
            except PermissionError:
                os.write(write_fd, b"SOCKET_PERMISSION_ERROR\n")
            except OSError as exc:
                os.write(write_fd, f"SOCKET_OSERR_{exc.errno}\n".encode())
        except BaseException as exc:  # noqa: BLE001 - report via pipe
            os.write(write_fd, ("CHILD_ERR:" + repr(exc)).encode())
        finally:
            os._exit(0)

    os.close(write_fd)
    chunks = []
    while True:
        part = os.read(read_fd, 4096)
        if not part:
            break
        chunks.append(part)
    os.close(read_fd)
    os.waitpid(pid, 0)
    text = b"".join(chunks).decode("utf-8", errors="replace")
    assert "WRITE_OK" in text, text
    assert "SOCKET_PERMISSION_ERROR" in text, text
    assert "SOCKET_OK" not in text, text


# ---------------------------------------------------------------------------
# Filesystem confinement
# ---------------------------------------------------------------------------
def test_authorized_workspace_read_and_write(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "allowed.txt").write_text("workspace-secret", encoding="utf-8")
    r = run_confined(
        _py("from pathlib import Path; "
            "print(Path('allowed.txt').read_text()); "
            "Path('created.txt').write_text('CREATED-BY-CHILD')"),
        workspace=ws, timeout_s=15)
    assert r.ok, r.stderr
    assert "workspace-secret" in r.stdout
    assert (ws / "created.txt").read_text(encoding="utf-8") == "CREATED-BY-CHILD"
    assert r.mechanism.startswith("landlock+seccomp")


def test_unauthorized_host_file_read_denied(tmp_path):
    ws = _workspace(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text(SECRET, encoding="utf-8")
    r = run_confined(
        _py(f"print(open({str(outside)!r}).read())"),
        workspace=ws, timeout_s=15)
    assert not r.ok
    assert SECRET not in r.stdout
    assert "PermissionError" in r.stderr or "Permission denied" in r.stderr


def test_unauthorized_host_file_write_denied(tmp_path):
    ws = _workspace(tmp_path)
    outside = tmp_path / "protected.txt"
    outside.write_text("ORIGINAL", encoding="utf-8")
    r = run_confined(
        _py(f"open({str(outside)!r}, 'w').write('OVERWRITTEN')"),
        workspace=ws, timeout_s=15)
    assert not r.ok
    assert outside.read_text(encoding="utf-8") == "ORIGINAL"


def test_path_traversal_and_symlink_escape_denied(tmp_path):
    ws = _workspace(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text(SECRET, encoding="utf-8")
    # Symlink created by the trusted parent, not by the child.
    (ws / "escape").symlink_to(outside)
    (ws / "subdir").mkdir()
    code = (
        "paths = ["
        f" {str(ws / '..' / 'outside.txt')!r},"
        " 'subdir/../../outside.txt',"
        " 'escape']\n"
        "import os\n"
        "for p in paths:\n"
        "    try:\n"
        "        print('LEAK', p, open(p).read())\n"
        "    except OSError:\n"
        "        print('DENIED', p)\n"
    )
    r = run_confined(_py(code), workspace=ws, timeout_s=15)
    assert r.ok, r.stderr
    assert "LEAK" not in r.stdout
    assert SECRET not in r.stdout
    assert r.stdout.count("DENIED") == 3


# ---------------------------------------------------------------------------
# Network denial
# ---------------------------------------------------------------------------
def test_tcp_udp_and_dns_denied(tmp_path):
    ws = _workspace(tmp_path)
    code = (
        "import socket\n"
        "results = []\n"
        "for family, kind in ((socket.AF_INET, socket.SOCK_STREAM),\n"
        "                     (socket.AF_INET, socket.SOCK_DGRAM)):\n"
        "    try:\n"
        "        s = socket.socket(family, kind)\n"
        "        results.append('SOCKET_CREATED')\n"
        "        s.close()\n"
        "    except PermissionError:\n"
        "        results.append('SOCKET_DENIED')\n"
        "    except OSError as exc:\n"
        "        results.append('SOCKET_OSERR_%d' % exc.errno)\n"
        "try:\n"
        "    socket.getaddrinfo('example.com', 80)\n"
        "    results.append('DNS_OK')\n"
        "except OSError:\n"
        "    results.append('DNS_DENIED')\n"
        "print(','.join(results))\n"
    )
    r = run_confined(_py(code), workspace=ws, timeout_s=15)
    assert r.ok, r.stderr
    assert "SOCKET_CREATED" not in r.stdout
    assert "DNS_OK" not in r.stdout
    assert r.stdout.count("SOCKET_DENIED") == 2


def test_child_process_inherits_filesystem_and_network_restrictions(tmp_path):
    ws = _workspace(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text(SECRET, encoding="utf-8")
    child_code = (
        f"print(open({str(outside)!r}).read())"
    )
    code = (
        "import subprocess, sys\n"
        f"p = subprocess.run([sys.executable, '-c', {child_code!r}], "
        "capture_output=True, text=True)\n"
        "print('CHILD_RC', p.returncode)\n"
        "print('CHILD_OUT', repr(p.stdout))\n"
        "import socket\n"
        "try:\n"
        "    socket.socket(); print('GRANDCHILD_SOCKET_OK')\n"
        "except PermissionError:\n"
        "    print('GRANDCHILD_SOCKET_DENIED')\n"
    )
    r = run_confined(_py(code), workspace=ws, timeout_s=20)
    assert r.ok, r.stderr
    assert SECRET not in r.stdout
    assert "GRANDCHILD_SOCKET_DENIED" in r.stdout
    assert "GRANDCHILD_SOCKET_OK" not in r.stdout


def test_unauthorized_inherited_fd_is_closed(tmp_path):
    ws = _workspace(tmp_path)
    secret = tmp_path / "fd_secret.txt"
    secret.write_text(SECRET, encoding="utf-8")
    fd = os.open(str(secret), os.O_RDONLY)
    try:
        code = (
            f"import os\n"
            f"try:\n"
            f"    print('FD_DATA', os.read({fd}, 100))\n"
            f"except OSError as exc:\n"
            f"    print('FD_CLOSED', exc.errno)\n"
        )
        r = run_confined(_py(code), workspace=ws, timeout_s=15)
        assert r.ok, r.stderr
        assert "FD_CLOSED" in r.stdout
        assert SECRET not in r.stdout
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# rlimits / timeout / cleanup
# ---------------------------------------------------------------------------
def test_cpu_limit_kills_busy_loop(tmp_path):
    ws = _workspace(tmp_path)
    r = run_confined(_py("while True: pass"), workspace=ws,
                     timeout_s=8, cpu_s=1, memory_mb=256)
    assert not r.ok
    assert not r.timed_out
    assert r.exit_code is not None and r.exit_code != 0
    assert r.elapsed_s < 8


def test_memory_limit_blocks_large_allocation(tmp_path):
    ws = _workspace(tmp_path)
    r = run_confined(
        _py("blob = bytearray(250 * 1024 * 1024); print('ALLOCATED')"),
        workspace=ws, timeout_s=15, cpu_s=5, memory_mb=64)
    assert not r.ok
    assert "ALLOCATED" not in r.stdout


def test_process_limit_is_applied_but_allows_normal_children(tmp_path):
    ws = _workspace(tmp_path)
    code = (
        "import resource, subprocess, sys\n"
        "soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)\n"
        "print('NPROC', soft, hard)\n"
        "p = subprocess.run([sys.executable, '-c', 'print(\"GRANDCHILD_OK\")'], "
        "capture_output=True, text=True)\n"
        "print('CHILD', p.returncode, p.stdout.strip())\n"
    )
    r = run_confined(_py(code), workspace=ws, timeout_s=20)
    assert r.ok, r.stderr
    assert "NPROC 256 256" in r.stdout
    assert "GRANDCHILD_OK" in r.stdout


def test_timeout_kills_whole_process_group(tmp_path):
    ws = _workspace(tmp_path)
    marker = ws / "grandchild-survived"
    child_code = (
        "import time, pathlib; time.sleep(2); "
        f"pathlib.Path(\"{marker}\").write_text(\"survived\")"
    )
    code = (
        "import subprocess, sys, time\n"
        f"child_code = {child_code!r}\n"
        "subprocess.Popen([sys.executable, '-c', child_code])\n"
        "time.sleep(30)\n"
    )
    r = run_confined(_py(code), workspace=ws, timeout_s=1)
    assert r.timed_out is True
    time.sleep(2.5)
    assert not marker.exists(), "grandchild survived process-group kill"


def test_concurrent_confinement_is_isolated(tmp_path):
    import concurrent.futures

    def run(i: int):
        ws = _workspace(tmp_path, f"ws{i}")
        (ws / "id.txt").write_text(str(i), encoding="utf-8")
        return run_confined(
            _py("from pathlib import Path; print(Path('id.txt').read_text())"),
            workspace=ws, timeout_s=15)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(4)))
    assert all(r.ok for r in results)
    assert sorted(r.stdout.strip() for r in results) == ["0", "1", "2", "3"]
