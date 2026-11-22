"""C1.8 — real notes-vault backlinks, graph view, daily notes and templates."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keel.notes_vault import Vault, render_template

ROOT = Path(__file__).resolve().parents[1]


def _vault(tmp_path):
    root = tmp_path / "vault"
    vault = Vault(root)
    vault.write("Index", "Welcome. See [[Project]] and [[Missing]] and #work.\n")
    vault.write("Project", "Tracked in [[Index]]. Status #work #active.\n")
    vault.write("Lonely", "No links here.\n")
    return vault


def test_links_and_backlinks_with_missing(tmp_path):
    vault = _vault(tmp_path)
    graph = vault.backlinks()
    assert graph["backlinks"]["Project"] == ["Index"]
    assert graph["backlinks"]["Index"] == ["Project"]
    assert "Missing" in graph["missing"]


def test_tags_and_orphans(tmp_path):
    vault = _vault(tmp_path)
    tags = vault.tags()
    assert set(tags["work"]) == {"Index", "Project"}
    assert tags["active"] == ["Project"]
    assert vault.orphans() == ["Lonely"]


def test_graph_has_nodes_edges_svg(tmp_path):
    vault = _vault(tmp_path)
    graph = vault.graph()
    ids = {n["id"] for n in graph["nodes"]}
    assert {"Index", "Project", "Missing"} <= ids
    assert len(graph["edges"]) == 3
    assert "<svg" in graph["svg"]
    missing = next(n for n in graph["nodes"] if n["id"] == "Missing")
    assert missing["exists"] is False


def test_daily_note_creation_and_idempotence(tmp_path):
    vault = _vault(tmp_path)
    first = vault.daily("2026-11-22")
    assert first["created"] is True
    assert "2026-11-22" in first["content"]
    second = vault.daily("2026-11-22")
    assert second["created"] is False
    assert second["content"] == first["content"]


def test_templates_and_rendering(tmp_path):
    text = render_template("# {{title}}\nDate {{date}} / {{today}}",
                           title="X", day="2026-01-02")
    assert "X" in text and text.count("2026-01-02") == 2
    vault = _vault(tmp_path)
    path = vault.apply_template("Meeting", "meeting", title="Standup",
                                day="2026-01-02")
    assert "Standup" in path.read_text(encoding="utf-8")


def test_invalid_name_rejected(tmp_path):
    vault = _vault(tmp_path)
    try:
        vault.write("../escape", "x")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal accepted")


def test_capability_integration(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    _vault(tmp_path)
    vault_root = str(tmp_path / "vault")
    result = invoke("cowork.notes.vault.backlinks",
                    {"root": vault_root}, context={})["result"]
    assert result["backlinks"]["Project"] == ["Index"]


def test_cli_vault(tmp_path):
    _vault(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "keel", "vault", "backlinks",
         str(tmp_path / "vault")],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "Project" in json.loads(proc.stdout)["backlinks"]
