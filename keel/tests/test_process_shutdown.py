from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _is_running(pid):
    """Check if a process is running without killing it."""
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


@pytest.fixture
def bg_process_script(tmp_path):
    if os.name == "nt":
        cmd = "timeout /t 300 /nobreak"
        shell = "cmd"
    else:
        cmd = "sleep 300"
        shell = "posix"
    script = tmp_path / "bg_test.py"
    script.write_text(f'''
import sys, os, time
sys.path.insert(0, r"{ROOT / "src"}")
from keel.runner import RealTools, cleanup_background_processes
r = RealTools()
res = r._background_shell({{"command": "{cmd}", "shell": "{shell}"}})
pid = res[1]["process_id"]
os_pid = res[1]["pid"]
print(f"STARTED {{pid}} {{os_pid}}", flush=True)
time.sleep(1)
# Verify running (without killing)
running = False
try:
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, os_pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            running = True
    else:
        os.kill(os_pid, 0)
        running = True
except Exception:
    running = False
print("RUNNING" if running else "NOT_RUNNING", flush=True)
# Cleanup
killed = cleanup_background_processes()
print(f"KILLED {{killed}}", flush=True)
time.sleep(0.5)
# Verify gone
gone = True
try:
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, os_pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            gone = False
    else:
        os.kill(os_pid, 0)
        gone = False
except Exception:
    gone = True
print("PROCESS_GONE" if gone else "STILL_RUNNING", flush=True)
''', encoding="utf-8")
    return script


def test_process_shutdown_cleanup(bg_process_script):
    result = subprocess.run(
        [sys.executable, str(bg_process_script)],
        capture_output=True, text=True, timeout=30,
    )
    print("stdout:", result.stdout)
    print("stderr:", result.stderr)
    assert "PROCESS_GONE" in result.stdout, result.stdout
    assert "STILL_RUNNING" not in result.stdout
