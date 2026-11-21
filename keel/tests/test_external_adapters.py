"""Local adapters for external features — no external runtime needed."""

from __future__ import annotations

import pytest

from keel.external_adapters import (LicenseTokenVerifier, container_command,
                                    delta_update_plan, judge_score,
                                    wasm_command)


def test_wasm_and_container_commands():
    assert wasm_command("main.wasm")[0] == "python"
    cmd = container_command("python:3.11", "echo hi", memory_mb=256)
    assert "--memory=256m" in cmd and "--network=none" in cmd
    with pytest.raises(ValueError):
        container_command("x", "y", cpus=0)


def test_delta_and_license():
    plan = delta_update_plan("0.1.0", "0.2.0", channel="beta")
    assert plan["requires_opt_in"] is True
    verifier = LicenseTokenVerifier()
    result = verifier.verify({"format": verifier.FORMAT,
                              "claims": {"tier": "standard"},
                              "signature": ""}, "key")
    assert result["valid"] is True and result["active"] is False


def test_judge_score():
    result = judge_score([{"ok": True}, {"ok": False}, {"ok": True}])
    assert result["score"] > 0.5 and result["steps"] == 3
