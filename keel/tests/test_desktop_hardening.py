"""Regression tests for the Electron desktop shell hardening.

The renderer/main-process code is JavaScript, so its lifecycle contracts are
asserted here as source-level invariants plus one real sidecar-launch test
that checks the stderr URL contract the shell parses.  These tests fail on
the pre-hardening main.js (orphaned sidecar, fragile token regex, detached
log pipe, permissive window-open handler).
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_APP = ROOT / "desktop-app"
MAIN_JS = DESKTOP_APP / "main.js"
LAUNCHER_PY = DESKTOP_APP / "launcher.py"


def _main_js() -> str:
    return MAIN_JS.read_text(encoding="utf-8")


def _handler(text: str, marker: str, length: int = 700) -> str:
    """Return a fixed window of source starting at ``marker``."""
    pos = text.find(marker)
    assert pos != -1, f"marker not found in main.js: {marker!r}"
    return text[pos:pos + length]


# --- sidecar lifecycle / orphan regression ---------------------------------

def test_single_cleanup_helper_kills_process_tree_on_windows():
    text = _main_js()
    assert "function stopSidecar()" in text, "no single sidecar cleanup helper"
    assert 'execFileSync("taskkill"' in text, "Windows cleanup must kill the tree"
    assert '"/T"' in text and '"/F"' in text, "taskkill must include /T /F"
    assert 'process.platform === "win32"' in text


def test_before_quit_uses_cleanup_helper():
    text = _main_js()
    block = _handler(text, 'app.on("before-quit"')
    assert "stopAllChildren()" in block
    assert "sidecar.kill(" not in block, "bare kill bypasses process-tree cleanup"


def test_window_closed_also_stops_sidecar():
    text = _main_js()
    block = _handler(text, 'mainWindow.on("closed"')
    # Stop at the next top-level handler so we only inspect the closed block.
    block = block.split("setWindowOpenHandler", 1)[0]
    assert "mainWindow = null" in block
    assert "stopAllChildren()" in block, "closing the window must stop child processes"


def test_startup_failure_kills_sidecar_before_exit():
    text = _main_js()
    # Locate the startup-failure fallback (not the runtime server error box).
    pos = text.rindex('dialog.showErrorBox("Keel failed to start"')
    block = text[max(0, pos - 300):pos + 120]
    assert "stopAllChildren()" in block, "app.exit() skips before-quit; clean up here"
    assert "app.exit(1)" in block
    assert block.index("stopAllChildren()") < block.index("app.exit(1)")


def test_no_bare_sidecar_kill_outside_helper():
    # All termination goes through stopSidecar()'s process-tree helper.
    text = _main_js()
    kills = [line for line in text.splitlines() if "sidecar.kill(" in line]
    assert kills == [], kills
    assert "proc.kill()" in text  # fallback inside the helper only


# --- token parsing / diagnostics -------------------------------------------

def test_token_parsed_via_url_api_not_fragile_regex():
    text = _main_js()
    assert "new URL(m[1])" in text, "URL line must be parsed with the URL API"
    assert 'searchParams.get("t")' in text
    assert "url.hostname !== \"127.0.0.1\"" in text, "loopback must be enforced"
    assert "if (!token)" in text, "bridge tokens must be present"
    assert "[A-Za-z0-9_-]" not in text, "old restrictive token regex must be gone"


def test_log_pipe_survives_sidecar_startup():
    text = _main_js()
    code_lines = [ln for ln in text.splitlines() if not ln.strip().startswith("//")]
    code = "\n".join(code_lines)
    assert 'removeListener("data", onData)' in code
    assert 'removeAllListeners("data")' not in code, (
        "removeAllListeners also detaches the pipe(log) diagnostic stream"
    )
    assert "sidecar.stderr.pipe(log)" in code


# --- renderer / navigation hardening ---------------------------------------

def test_window_open_handler_denies_non_web_schemes():
    text = _main_js()
    block = _handler(text, "setWindowOpenHandler", 900)
    assert 'parsed.protocol === "http:"' in block
    assert 'parsed.protocol === "https:"' in block
    assert 'parsed.hostname === "127.0.0.1"' in block
    assert block.count('action: "deny"') >= 2
    assert "file:, javascript:, data:" in text  # documented denial in comment


def test_renderer_has_no_node_or_preload():
    text = _main_js()
    block = _handler(text, "function createWindow", 900)
    assert "contextIsolation: true" in block
    assert "sandbox: true" in block
    assert "nodeIntegration: false" in block
    assert "preload: undefined" in block


# --- static syntax + real launcher contract --------------------------------

def test_update_check_cannot_crash_shell_on_spawn_error():
    text = _main_js()
    block = _handler(text, "function checkForUpdates", 1400)
    assert 'child.on("error", () => {})' in block, (
        "an advisory update-check spawn failure must not crash the shell"
    )


def test_node_syntax_check():
    node = shutil.which("node")
    if not node:
        return  # Node is optional in the Python-only test environment
    result = subprocess.run(
        [node, "--check", str(MAIN_JS)],
        cwd=str(DESKTOP_APP), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_launcher_uses_absolute_import():
    text = LAUNCHER_PY.read_text(encoding="utf-8")
    assert "from keel.cli.main import main" in text
    assert "raise SystemExit(main())" in text


@pytest.mark.skipif(sys.platform != "win32", reason="taskkill is Windows-only")
def test_taskkill_tree_terminates_grandchild():
    """Prove the /T /F strategy in stopSidecar() reaps a whole process tree.

    A plain ``proc.kill()`` on Windows terminates only the parent (the
    PyInstaller bootloader), leaving the grandchild that owns the listening
    socket orphaned.  This test builds exactly that shape and verifies the
    taskkill invocation used by main.js removes both processes.
    """
    parent_code = (
        "import subprocess,sys,time;"
        "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "print(c.pid, flush=True);time.sleep(60)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        grandchild = int(parent.stdout.readline().strip())
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {grandchild}", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        assert str(grandchild) in listing, "grandchild did not start"

        subprocess.run(
            ["taskkill", "/PID", str(parent.pid), "/T", "/F"],
            capture_output=True, text=True, timeout=10,
        )
        parent.wait(timeout=10)

        deadline = time.time() + 5
        while time.time() < deadline:
            listing = subprocess.run(
                ["tasklist", "/FI", f"PID eq {grandchild}", "/NH"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            if str(grandchild) not in listing:
                return  # grandchild reaped — no orphan
            time.sleep(0.2)
        pytest.fail(f"grandchild PID {grandchild} survived taskkill /T /F")
    finally:
        if parent.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(parent.pid), "/T", "/F"],
                capture_output=True, timeout=10,
            )
            try:
                parent.wait(timeout=10)
            except subprocess.TimeoutExpired:
                parent.kill()


def test_sidecar_stderr_contract_matches_desktop_parser():
    """Real launch: bridge prints a loopback URL whose token round-trips.

    Uses an ephemeral port and a token containing '.' and '=' — characters the
    old ``[A-Za-z0-9_-]+`` regex silently truncated — to prove the hardened
    URL-based parser is required and correct.  A plain ``python -m keel``
    process is spawned (no PyInstaller child tree), so termination is clean.
    """
    token = "desktop.hardening=ABC-123_xyz"
    env = {**os.environ, "KEEL_TOKEN": token, "KEEL_NO_BANNER": "1"}
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [sys.executable, "-m", "keel", "serve", "--port", "0"],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, text=True,
    )
    lines: queue.Queue[str] = queue.Queue()

    def _reader() -> None:
        for line in proc.stderr:
            lines.put(line)

    threading.Thread(target=_reader, daemon=True).start()
    try:
        url = None
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            match = re.search(r"keel webapp running at (\S+)", line)
            if match:
                url = match.group(1)
                break
        assert url, "sidecar did not print its startup URL on stderr"

        parsed = urllib.parse.urlparse(url)
        assert parsed.scheme == "http", url
        assert parsed.hostname in ("127.0.0.1", "localhost"), url
        assert parsed.port and parsed.port > 0, url
        assert urllib.parse.parse_qs(parsed.query).get("t") == [token], url

        # This is exactly what main.js now does: URL + validation + token.
        assert urllib.parse.parse_qs(parsed.query)["t"][0] == token
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
