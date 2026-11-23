"""Execution-path coverage: every capability that can run code is authorised.

Invariants asserted here:
(a) command-bearing capabilities carry an execute/write permission tier;
(b) invoking them without that tier is denied by the capability hub;
(c) a representative route actually calls the native sandbox boundary;
(d) saved execution policy binds routes whose command lives in a non-canonical
    field (``argv``, ``code``, ``source``), not just ``command``.
"""

from __future__ import annotations

import json
import sys

import pytest

from keel import capability_registry, exec_guard, os_sandbox, sandbox_exec
from keel.capabilities import CapabilityError, get, invoke
from keel.exec_policy import ExecPolicyStore

# Capabilities from which untrusted input can reach a real process or the
# Python audit-hook sandbox.
COMMAND_CAPABILITIES = {
    "core.os.sandbox.run": "execute",
    "code.sandbox.run": "execute",
    "cowork.notebook.execute": "execute",
    "code.debug.inspect": "execute",
    "external.ci.run": "execute",
}

POLICY = {
    "prefix_rules": [
        {"pattern": ["git", "reset", "--hard"], "decision": "forbidden",
         "justification": "destructive git reset"},
        {"pattern": ["rm", "-rf"], "decision": "forbidden",
         "justification": "recursive delete"},
    ],
    "network_rules": [],
}


class _Confined:
    ok = True
    exit_code = 0
    timed_out = False
    elapsed_s = 0.01
    mechanism = "test-boundary"
    stdout = "ok"
    stderr = ""
    limitations = ["test"]


class _Sandbox:
    ok = True
    stdout = ""
    stderr = ""
    exit_code = 0
    elapsed_s = 0.01
    timed_out = False
    limits = {}


@pytest.mark.parametrize("cap_id,tier", sorted(COMMAND_CAPABILITIES.items()))
def test_command_capability_declares_execute_permission(cap_id, tier):
    cap = get(cap_id)
    assert cap is not None, f"{cap_id} not registered"
    assert cap.permission in ("execute", "write")
    assert cap.permission == tier


@pytest.mark.parametrize("cap_id", sorted(COMMAND_CAPABILITIES))
def test_insufficient_permissions_denied(cap_id):
    # read/write-only callers must never reach a command-bearing handler.
    with pytest.raises(CapabilityError) as exc:
        invoke(cap_id, {"path": "unused.py", "argv": ["echo", "x"],
                        "code": "pass", "source": "pass", "prompt": "hi"},
               allowed_permissions={"read", "write"})
    assert exc.value.code == "permission_denied"


def test_os_sandbox_route_calls_run_confined(monkeypatch, tmp_path):
    calls = []

    def spy(argv, **kwargs):
        calls.append((argv, kwargs))
        return _Confined()

    monkeypatch.setattr(os_sandbox, "run_confined", spy)
    result = invoke("core.os.sandbox.run", {"argv": ["echo", "hi"]},
                    context={"state_root": str(tmp_path)})
    assert result["ok"] is True
    assert len(calls) == 1
    assert calls[0][0] == ["echo", "hi"]
    assert calls[0][1]["allow_network"] is False


def test_python_sandbox_route_calls_run_python(monkeypatch, tmp_path):
    calls = []

    def spy(code, **kwargs):
        calls.append((code, kwargs))
        return _Sandbox()

    monkeypatch.setattr(sandbox_exec, "run_python", spy)
    result = invoke("code.sandbox.run",
                    {"code": "print(2 + 2)", "allow_network": False},
                    context={"state_root": str(tmp_path)})
    assert result["ok"] is True
    assert len(calls) == 1
    assert "print(2 + 2)" in calls[0][0]


def test_debug_route_calls_sandbox_boundary(monkeypatch, tmp_path):
    script = tmp_path / "sample.py"
    script.write_text("def compute():\n    x = 1\n    return x\n\ncompute()\n",
                      encoding="utf-8")
    calls = []
    payload = {"stops": [{"file": str(script), "line": 2,
                          "function": "compute", "locals": {"x": "1"}}]}

    def spy(code, **kwargs):
        calls.append((code, kwargs))
        fake = _Sandbox()
        fake.stdout = (capability_registry._DEBUG_TOKEN
                       + json.dumps(payload) + "\n")
        return fake

    monkeypatch.setattr(sandbox_exec, "run_python", spy)
    result = invoke("code.debug.inspect",
                    {"path": str(script), "breakpoint": str(script), "line": 2},
                    context={"state_root": str(tmp_path)})
    assert result["result"]["sandboxed"] is True
    assert result["result"]["stops"] == 1
    assert calls and "compute" in calls[0][0]


def test_ci_route_calls_sandbox_and_guard(monkeypatch, tmp_path):
    guarded = []
    confined = []

    def guard_spy(cap_id, params, ctx=None, **kwargs):
        guarded.append((cap_id, params, kwargs))
        return None

    def confine_spy(argv, **kwargs):
        confined.append((argv, kwargs))
        return _Confined()

    monkeypatch.setattr(exec_guard, "enforce_command", guard_spy)
    monkeypatch.setattr(os_sandbox, "run_confined", confine_spy)
    result = invoke("external.ci.run", {"prompt": "hi"},
                    context={"state_root": str(tmp_path)})
    assert result["result"]["mock"] is False
    assert result["result"]["sandboxed"] is True
    assert guarded and guarded[0][0] == "external.ci.run"
    assert "hi" in guarded[0][1]["argv"]
    assert confined and any("keel" in part for part in confined[0][0])


def test_saved_policy_binds_argv_route(tmp_path, monkeypatch):
    ExecPolicyStore(tmp_path).save("default", POLICY)
    called = []
    monkeypatch.setattr(os_sandbox, "run_confined",
                        lambda argv, **kw: called.append(argv) or _Confined())
    with pytest.raises(CapabilityError) as exc:
        invoke("core.os.sandbox.run", {"argv": ["git", "reset", "--hard"]},
               context={"state_root": str(tmp_path)})
    assert exc.value.code == "policy_denied"
    assert not called, "denied command must not reach the sandbox boundary"


def test_saved_policy_binds_code_route(tmp_path, monkeypatch):
    ExecPolicyStore(tmp_path).save("default", POLICY)
    called = []
    monkeypatch.setattr(sandbox_exec, "run_python",
                        lambda code, **kw: called.append(code) or _Sandbox())
    with pytest.raises(CapabilityError) as exc:
        invoke("code.sandbox.run", {"code": "rm -rf /tmp/x"},
               context={"state_root": str(tmp_path)})
    assert exc.value.code == "policy_denied"
    assert not called


def test_saved_policy_binds_notebook_source_route(tmp_path, monkeypatch):
    ExecPolicyStore(tmp_path).save("default", POLICY)
    called = []
    monkeypatch.setattr(sandbox_exec, "run_python",
                        lambda code, **kw: called.append(code) or _Sandbox())
    with pytest.raises(CapabilityError) as exc:
        invoke("cowork.notebook.execute", {"source": "rm -rf /tmp/x"},
               context={"state_root": str(tmp_path)})
    assert exc.value.code == "policy_denied"
    assert not called


def test_read_tier_secret_lookup_does_not_spawn_command_provider(tmp_path):
    marker = tmp_path / "provider-ran"
    config = {"providers": [{
        "kind": "command",
        "command": [sys.executable, "-c",
                    "import sys; open(sys.argv[1], 'w').write('x')",
                    str(marker)],
    }]}
    (tmp_path / "secret-providers.json").write_text(
        json.dumps(config), encoding="utf-8")
    result = invoke("core.secrets.has", {"key": "ANY_KEY"},
                    context={"state_root": str(tmp_path)})
    assert result["result"]["present"] is False
    assert not marker.exists(), "read-tier capability executed a provider"


def test_best_of_n_hub_response_exposes_real_score(tmp_path):
    """Additive audit fix: the hub must surface the scoring evidence."""
    payload = invoke("duet.best_of_n", {
        "prompt": "pick",
        "candidates": [
            {"text": "a", "score": 0.25, "evidence": "lower"},
            {"text": "b", "score": 0.9, "evidence": "higher"},
        ],
    }, context={"state_root": str(tmp_path)})["result"]
    assert payload["index"] == 1
    assert isinstance(payload["score"], (int, float))
    assert payload["score"] == 0.9
    assert payload["evidence"] == "higher"
