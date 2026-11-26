from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATE_PATH = REPO / "scripts" / "check_model_licenses.py"
_spec = importlib.util.spec_from_file_location(
    "check_model_licenses_under_test", GATE_PATH)
license_gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = license_gate
_spec.loader.exec_module(license_gate)


@pytest.mark.parametrize(
    ("license_name", "bundled", "commercial", "redistribution", "expected", "message"),
    [
        ("UNKNOWN", True, True, True, 1, "license is unknown/unreviewed"),
        ("UnreviewedLicense-9.9", True, True, True, 1,
         "not in reviewed allowlist"),
        ("UNKNOWN", False, False, False, 0, "LICENSE GATE OK"),
        ("MIT", True, True, True, 0, "LICENSE GATE OK"),
    ],
)
def test_license_gate_fails_closed_for_unreviewed_bundled_entries(
        tmp_path, monkeypatch, capsys, license_name, bundled, commercial,
        redistribution, expected, message):
    registry = tmp_path / "licenses.json"
    registry.write_text(json.dumps({
        "entries": [{
            "id": "probe",
            "name": "Probe asset",
            "bundled": bundled,
            "license": license_name,
            "commercial_use_allowed": commercial,
            "redistribution_allowed": redistribution,
            "verified_date": "2026-01-01",
            "ci_gate": True,
        }],
        "ci_policy": {"reject_non_commercial_bundled": True},
    }), encoding="utf-8")
    monkeypatch.setattr(license_gate, "REGISTRY", registry)

    assert license_gate.main() == expected
    assert message in capsys.readouterr().out
