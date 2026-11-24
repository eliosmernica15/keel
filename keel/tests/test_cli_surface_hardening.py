"""Hardening regressions for the implemented CLI/TUI capability surfaces.

Each test here corresponds to a defect found by exercising the real `keel`
process (or the real ``Tui`` command loop) with an isolated state root:

* ``keel --help`` was rejected as an unknown option (exit 1).
* ``keel provider --help`` omitted the implemented ``validate`` subcommand.
* ``capability invoke --confirm`` never reached ``capabilities.invoke``'s
  policy-confirmation context, so a policy ``prompt`` rule still denied it.
* ``Tui``'s ``/invoke`` ran mutating capabilities with no confirmation at all
  and wrote no audit record, unlike the CLI and web surfaces.
* ``keel doctor`` (advertised in the master plan) fell through to the model
  loop instead of the local readiness builtin; ``keel doctor --help`` errored.
* ``execpolicy check``/``network`` with missing operands exited 1 silently.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from keel.tui import Tui

SRC = Path(__file__).resolve().parents[1] / "src"


def _env(state_root: Path | None = None) -> dict[str, str]:
    """Keep subprocesses on this worktree's source, not an installed copy."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + existing if existing else "")
    if state_root is not None:
        env["KEEL_STATE_DIR"] = str(state_root)
    return env


def _cli(*args: str, cwd: Path, state_root: Path | None = None):
    return subprocess.run(
        [sys.executable, "-m", "keel", *args], cwd=str(cwd),
        env=_env(state_root), capture_output=True, text=True, timeout=60)


def _prompt_policy() -> dict:
    return {"prefix_rules": [{
        "pattern": ["ssh", "deploy"], "decision": "prompt",
        "justification": "deployment needs explicit consent",
        "match": ["ssh deploy now"], "not_match": ["ssh build now"],
    }]}


def _install_prompt_policy(state_root: Path) -> None:
    folder = state_root / "exec-policies"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "default.json").write_text(
        json.dumps(_prompt_policy()), encoding="utf-8")


_REMOTE_PARAMS = json.dumps({
    "kind": "ssh", "location": "build-host", "command": "ssh deploy now",
})


# --------------------------------------------------------------- top-level help
def test_top_level_help_is_clean_exit_zero(tmp_path):
    for flag in ("--help", "-h", "help"):
        result = _cli(flag, cwd=tmp_path)
        assert result.returncode == 0, (flag, result.stderr)
        text = result.stdout + result.stderr
        assert "usage: keel" in text.lower(), text
        for command in ("capability", "tui", "provider", "execpolicy", "skills"):
            assert command in text, (flag, text)


def test_provider_help_advertises_implemented_validate(tmp_path):
    result = _cli("provider", "--help", cwd=tmp_path)
    assert result.returncode == 0
    assert "validate" in result.stderr, result.stderr
    # The advertised command actually exists and is non-interactive.
    result = _cli("provider", "validate", cwd=tmp_path,
                  state_root=tmp_path / "state")
    assert result.returncode == 0, result.stderr
    assert "providers" in json.loads(result.stdout)


# --------------------------------------------------- capability invoke / policy
def test_cli_confirm_reaches_policy_enforcement(tmp_path):
    state = tmp_path / "state"
    _install_prompt_policy(state)
    base = ("capability", "invoke", "external.remote.cmd",
            "--params", _REMOTE_PARAMS)

    denied = _cli(*base, cwd=tmp_path, state_root=state)
    assert denied.returncode == 1
    assert "policy_denied" in denied.stderr, denied.stderr

    allowed = _cli(*base, "--confirm", cwd=tmp_path, state_root=state)
    assert allowed.returncode == 0, allowed.stderr
    assert json.loads(allowed.stdout)["ok"] is True


def test_broken_saved_policy_is_a_clean_cli_error(tmp_path):
    state = tmp_path / "state"
    folder = state / "exec-policies"
    folder.mkdir(parents=True)
    (folder / "default.json").write_text("{not json", encoding="utf-8")
    result = _cli("capability", "invoke", "core.hardware.detect",
                  "--params", "{}", cwd=tmp_path, state_root=state)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr, result.stderr
    assert result.stderr.strip(), result.stderr


def test_cli_invoke_records_audit_with_cli_surface(tmp_path):
    result = _cli("capability", "invoke", "core.hardware.detect", "--params", "{}",
                  cwd=tmp_path, state_root=tmp_path / "state")
    assert result.returncode == 0, result.stderr
    audit = tmp_path / "state" / "capability-audit.jsonl"
    entries = [json.loads(line) for line in audit.read_text().splitlines() if line]
    assert any(e.get("surface") == "cli" and e.get("ok") is True for e in entries)


# ---------------------------------------------------------------- TUI /invoke
def test_tui_invoke_requires_confirmation_for_mutating_capability(tmp_path):
    state = tmp_path / "state"
    command = '/invoke core.flags.set {"name":"probe","enabled":true}'
    flag_file = state / "feature-flags.json"

    declined: list[str] = []
    tui = Tui(cwd=str(tmp_path), state_root=str(state),
              output_fn=declined.append, input_fn=lambda _: "n")
    assert tui.handle_command(command) is True
    assert not flag_file.exists(), "mutating capability ran without consent"
    assert any("cancel" in line.lower() for line in declined), declined

    accepted: list[str] = []
    tui = Tui(cwd=str(tmp_path), state_root=str(state),
              output_fn=accepted.append, input_fn=lambda _: "y")
    assert tui.handle_command(command) is True
    assert flag_file.is_file(), accepted
    assert json.loads(flag_file.read_text())["probe"]["enabled"] is True
    audit = state / "capability-audit.jsonl"
    entries = [json.loads(line) for line in audit.read_text().splitlines() if line]
    assert any(e.get("surface") == "tui" and e.get("capability") ==
               "core.flags.set" for e in entries)


def test_tui_invoke_confirm_satisfies_policy_prompt(tmp_path):
    state = tmp_path / "state"
    _install_prompt_policy(state)
    # Keep the JSON compact but valid inside the single-line TUI command.
    command = '/invoke external.remote.cmd ' + json.dumps({
        "kind": "ssh", "location": "build-host", "command": "ssh deploy now",
    }, separators=(",", ":"))

    declined: list[str] = []
    tui = Tui(cwd=str(tmp_path), state_root=str(state),
              output_fn=declined.append, input_fn=lambda _: "n")
    assert tui.handle_command(command) is True
    assert not any("policy_denied" in line for line in declined), declined

    accepted: list[str] = []
    tui = Tui(cwd=str(tmp_path), state_root=str(state),
              output_fn=accepted.append, input_fn=lambda _: "y")
    assert tui.handle_command(command) is True
    assert any("'args'" in line or '"args"' in line for line in accepted), accepted


# ------------------------------------------------------------------- doctor
def test_doctor_is_a_registered_local_command(tmp_path):
    result = _cli("doctor", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "keel doctor" in result.stdout, result.stdout
    assert "python" in result.stdout
    assert "Keel scaffold" not in result.stdout  # must not run the model loop

    help_result = _cli("doctor", "--help", cwd=tmp_path)
    assert help_result.returncode == 0
    assert "--bundle" in (help_result.stdout + help_result.stderr)


# ------------------------------------------------------------ execpolicy errors
def test_execpolicy_missing_operands_report_an_error(tmp_path):
    policy = tmp_path / "policy.json"
    _install_prompt_policy(tmp_path / "state")
    policy.write_text(json.dumps(_prompt_policy()), encoding="utf-8")
    for argv in (("check", str(policy)), ("network", str(policy))):
        result = _cli("execpolicy", *argv, cwd=tmp_path,
                      state_root=tmp_path / "state")
        assert result.returncode == 1
        assert result.stderr.strip(), (argv, result)
        assert "Traceback" not in result.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
