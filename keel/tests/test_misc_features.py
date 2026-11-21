"""Assorted local addendum feature descriptors."""

from __future__ import annotations

from keel.misc_features import (behavior_anomaly, dap_breakpoint,
                                extra_instruction_files, fleet_views,
                                git_extras, offline_doc_pack,
                                observability_views, prune_old_versions,
                                small_model_role, specialist_agents)


def test_instruction_globs_and_small_model(tmp_path):
    (tmp_path / "GUIDE.md").write_text("x", encoding="utf-8")
    found = extra_instruction_files(tmp_path, ["*.md"])
    assert any(f.endswith("GUIDE.md") for f in found)
    url = extra_instruction_files(tmp_path, ["https://x.test/guide.md"])[0]
    assert "approval" in url["note"]
    assert small_model_role()["per_agent_override"] is True


def test_prune_and_specialists():
    assert prune_old_versions(["3.0", "2.0", "1.0", "0.9"]) == ["0.9"]
    assert "security-reviewer" in specialist_agents()


def test_doc_pack_and_views(tmp_path):
    (tmp_path / "doc.md").write_text("x", encoding="utf-8")
    assert offline_doc_pack(tmp_path, "python")["searchable"] is True
    assert "kanban" in fleet_views()
    assert observability_views()["token_waterfall"] is True


def test_dap_git_and_anomaly():
    assert dap_breakpoint("a.py", 5)["line"] == 5
    assert "hunk_staging" in git_extras()
    events = [{"tool": "read_file"} for _ in range(25)]
    assert "mass_file_reads" in behavior_anomaly(events)["flags"]
