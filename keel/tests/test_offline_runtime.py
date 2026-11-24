"""Offline boot + coding task with no credentials and no network.

Addendum 3 X0.8: Keel must boot and complete a coding task using a local
model without an account, API key or internet connection. This module is
also executed inside a `unshare -n` network namespace in CI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _no_provider_keys(monkeypatch) -> None:
    for key in ("KEEL_OPENROUTER_API_KEY", "KEEL_GOOGLE_API_KEY",
                "KEEL_NVIDIA_API_KEY", "KEEL_ANTHROPIC_API_KEY",
                "KEEL_COMPAT_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_offline_module_imports_without_network(monkeypatch):
    _no_provider_keys(monkeypatch)
    sys.path.insert(0, str(SRC))
    import keel
    import keel.runner
    import keel.session
    assert keel.__version__


def test_configured_providers_empty_without_credentials(monkeypatch):
    _no_provider_keys(monkeypatch)
    sys.path.insert(0, str(SRC))
    from keel.provider_validation import configured_providers
    configured = configured_providers()
    assert configured == [], configured


def test_offline_coding_task_via_fake_model(tmp_path, monkeypatch):
    """A real coding turn completes offline using the deterministic local model."""
    _no_provider_keys(monkeypatch)
    monkeypatch.syspath_prepend(str(SRC))
    from keel import runner

    script = tmp_path / "script.json"
    # Fake scripts are JSON: {"script": [[block, ...turn-1], [...turn-2]]}.
    script.write_text(
        json.dumps({"script": [[{
            "type": "tool_use", "id": "t1", "name": "write_file",
            "input": {"path": "hello.txt", "content": "offline ok"},
        }]]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    plan = runner.parse_argv([
        "write hello.txt", "--fake-script", str(script), "-p", "text",
        "--allow-rule", "write_file", "--state-root", str(tmp_path / "state")])
    result = runner.run(plan)
    assert result is not None
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "offline ok"


def test_no_outbound_import_hooks():
    """Importing the runtime must not perform network I/O.

    In the offline CI job the network namespace has no route, so any hidden
    outbound attempt would raise here. Locally we assert no socket is created
    during import by patching socket.socket.
    """
    import socket
    import builtins

    sys.path.insert(0, str(SRC))
    original = socket.socket
    calls: list[object] = []

    def tracked(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    socket.socket = tracked  # type: ignore[assignment]
    # Snapshot every keel module we evict so the rest of the suite keeps the
    # SAME module objects (and therefore the same class identities). Deleting
    # them permanently makes `isinstance(x, Tool)` fail in tests that imported
    # Tool at collection time — a real test-pollution defect, fixed here.
    saved = {
        name: module for name, module in list(sys.modules.items())
        if name == "keel" or name.startswith("keel.")
    }
    try:
        for name in saved:
            del sys.modules[name]
        import keel  # noqa: F401
        import keel.webapp  # noqa: F401
    finally:
        # Discard the fresh copies and restore the originals.
        for name in list(sys.modules):
            if name == "keel" or name.startswith("keel."):
                del sys.modules[name]
        sys.modules.update(saved)
        socket.socket = original  # type: ignore[assignment]
    assert not calls, f"network used during import: {calls[:3]}"
