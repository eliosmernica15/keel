"""C4.5/C4.6/C4.8/C4.14 — dev tooling helpers."""

from __future__ import annotations

import json

from keel.dev_tools import (architecture_snapshot, check_port, security_scan,
                            summarize_sarif)


def test_sarif_summary(tmp_path):
    path = tmp_path / "results.sarif"
    path.write_text(json.dumps({"runs": [{"results": [
        {"level": "error"}, {"level": "warning"}, {"level": "warning"}]}]}),
        encoding="utf-8")
    summary = summarize_sarif(path)
    assert summary["total"] == 3 and summary["by_level"]["warning"] == 2


def test_security_scan_clean_and_hit(tmp_path):
    (tmp_path / "code.py").write_text("x = 1\n", encoding="utf-8")
    assert security_scan(tmp_path)["clean"] is True
    (tmp_path / "leak.txt").write_text("sk-abcdefghijklmnopqrstuvwxyz",
                                       encoding="utf-8")
    assert security_scan(tmp_path)["clean"] is False


def test_architecture_snapshot(tmp_path):
    (tmp_path / "mod.py").write_text("def f(): pass\n", encoding="utf-8")
    snap = architecture_snapshot(tmp_path)
    assert "mod" in snap["modules"]
    assert "f" in snap["modules"]["mod"]["symbols"]


def test_check_port_closed():
    assert check_port(1, "127.0.0.1") is False
