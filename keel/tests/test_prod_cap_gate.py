"""Production gate: capability policy failures are typed and fail closed."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from keel import capabilities  # noqa: E402


def _install_cap(monkeypatch, name="core.prod.test"):
    cap = capabilities.Capability(
        id=name, module="test", surface="core", permission="read",
        description="test", input_schema={"type": "object"},
        handler=lambda params, context: {"ok": True})
    monkeypatch.setitem(capabilities._REGISTRY, name, cap)
    return name


def test_corrupt_saved_policy_is_typed_policy_error(tmp_path, monkeypatch):
    """A corrupt policy file must not escape as a raw JSON/OS exception."""
    name = _install_cap(monkeypatch)
    policy_dir = tmp_path / "exec-policies"
    policy_dir.mkdir(parents=True)
    (policy_dir / "default.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(capabilities.CapabilityError) as exc:
        capabilities.invoke(name, {}, context={"state_root": str(tmp_path)})
    assert exc.value.code == "policy_error"


def test_ask_policy_without_confirmation_fails_closed(tmp_path, monkeypatch):
    """An unconfirmed policy `ask` must not execute a handler."""
    name = _install_cap(monkeypatch)
    policy_dir = tmp_path / "exec-policies"
    policy_dir.mkdir(parents=True)
    doc = {"prefix_rules": [
        {"pattern": ["prod-test"], "decision": "prompt",
         "justification": "needs approval"}]}
    (policy_dir / "default.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(capabilities.CapabilityError) as exc:
        capabilities.invoke(name, {"command": "prod-test"}, context={
            "state_root": str(tmp_path), "interactive": False})
    assert exc.value.code in {"confirmation_required", "policy_denied"}
