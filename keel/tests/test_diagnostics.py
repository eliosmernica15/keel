"""B4.12 — redacted diagnostics bundle."""

from __future__ import annotations

import json
import zipfile

from keel.cli.main import main
from keel.diagnostics import collect, mask, write_bundle


def test_mask_hides_values():
    assert mask("") == "(unset)"
    result = mask("sk-abcdefghijklmnop")
    assert "abcdef" not in result and "19 chars" in result


def test_collect_masks_credentials(monkeypatch):
    monkeypatch.setenv("KEEL_TEST_API_KEY", "super-secret-value")
    doc = collect()
    assert doc["app"] == "Keel" and doc["version"]
    assert doc["env_flags"]["KEEL_TEST_API_KEY"] == "••18 chars"
    assert "super-secret-value" not in json.dumps(doc)


def test_bundle_is_redacted_zip(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_TEST_TOKEN", "secret-token-value")
    target = write_bundle(tmp_path / "diag.zip")
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert "diagnostics.json" in names and "README.txt" in names
        content = archive.read("diagnostics.json").decode("utf-8")
        assert "secret-token-value" not in content


def test_cli_doctor_bundle(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["doctor", "--bundle"]) == 0
    assert "redacted diagnostics bundle" in capsys.readouterr().out
    assert (tmp_path / "keel-diagnostics.zip").is_file()
