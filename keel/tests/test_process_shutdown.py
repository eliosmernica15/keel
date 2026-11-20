from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bg_process_script(tmp_path):
    child = tmp_path / "child_proc.py"
    child.write_text("import time; time.sleep(300)\n", encoding="utf-8")
    child_path = str(child).replace("\\", "\\\\")

    pid_file = tmp_path / "pids.txt"

    if os.name == "nt":
        inner_cmd = f'import subprocess,sys,time; c=subprocess.Popen([sys.executable,r"{child_path}"]); print("CHILD",c.pid,flush=True); open(r"{pid_file}", "w").write(str(c.pid)); time.sleep(300)'
        shell = "cmd"
    else:
        inner_cmd = f'import subprocess,sys,time; c=subprocess.Popen([sys.executable,"{child}"]); print("CHILD",c.pid,flush=True); open("{pid_file}", "w").write(str(c.pid)); time.sleep(300)'
        shell = "posix"

    lines = []
    lines.append("import sys, os, time")
    lines.append(f'sys.path.insert(0, r"{ROOT / "src"}")')
    lines.append("from keel.runner import RealTools, cleanup_background_processes")
    lines.append("r = RealTools()")
    lines.append(f'cmd = {repr(inner_cmd)}')
    lines.append(f'shell = "{shell}"')
    lines.append('res = r._background_shell({"command": cmd, "shell": shell})')
    lines.append("os_pid = res[1]['pid']")
    lines.append('print(f"STARTED {os_pid}", flush=True)')
    lines.append("time.sleep(2)")
    lines.append(f'pid_file = r"{pid_file}"')
    lines.append("child_pids = []")
    lines.append("try:")
    lines.append("    with open(pid_file) as f:")
    lines.append("        child_pids = [int(f.read().strip())]")
    lines.append("except Exception:")
    lines.append("    pass")
    lines.append('print(f"CHILD_PIDS {child_pids}", flush=True)')
    # Verify parent running
    lines.append("running = False")
    lines.append("try:")
    if os.name == "nt":
        lines.append("    import ctypes")
        lines.append("    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, os_pid)")
        lines.append("    if h:")
        lines.append("        ctypes.windll.kernel32.CloseHandle(h)")
        lines.append("        running = True")
    else:
        lines.append("    os.kill(os_pid, 0)")
        lines.append("    running = True")
    lines.append("except Exception:")
    lines.append("    running = False")
    lines.append('print("RUNNING" if running else "NOT_RUNNING", flush=True)')
    # Cleanup
    lines.append("killed = cleanup_background_processes()")
    lines.append('print(f"KILLED {killed}", flush=True)')
    lines.append("time.sleep(2)")
    # Verify parent gone
    lines.append("parent_gone = True")
    lines.append("try:")
    if os.name == "nt":
        lines.append("    import ctypes")
        lines.append("    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, os_pid)")
        lines.append("    if h:")
        lines.append("        ctypes.windll.kernel32.CloseHandle(h)")
        lines.append("        parent_gone = False")
    else:
        lines.append("    os.kill(os_pid, 0)")
        lines.append("    parent_gone = False")
    lines.append("except Exception:")
    lines.append("    parent_gone = True")
    lines.append('print("PARENT_GONE" if parent_gone else "PARENT_ALIVE", flush=True)')
    # Verify children gone
    lines.append("children_gone = True")
    lines.append("for cpid in child_pids:")
    lines.append("    try:")
    if os.name == "nt":
        lines.append("        import ctypes")
        lines.append("        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, cpid)")
        lines.append("        if h:")
        lines.append("            ctypes.windll.kernel32.CloseHandle(h)")
        lines.append("            children_gone = False")
    else:
        lines.append("        os.kill(cpid, 0)")
        lines.append("        children_gone = False")
    lines.append("    except Exception:")
    lines.append("        pass")
    lines.append('print("CHILDREN_GONE" if children_gone else "CHILDREN_ALIVE", flush=True)')

    script = tmp_path / "bg_test.py"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


def test_process_shutdown_cleanup(bg_process_script):
    result = subprocess.run(
        [sys.executable, str(bg_process_script)],
        capture_output=True, text=True, timeout=60,
    )
    print("stdout:", result.stdout)
    print("stderr:", result.stderr)
    assert "PARENT_GONE" in result.stdout, result.stdout
    assert "CHILDREN_GONE" in result.stdout, result.stdout
    assert "PARENT_ALIVE" not in result.stdout
    assert "CHILDREN_ALIVE" not in result.stdout
