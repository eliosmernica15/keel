"""A1.5 — `keel init` generates AGENTS.md from a repository scan."""

from __future__ import annotations

import pytest

from keel import init_project
from keel.cli.main import main


def _make_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("# demo", encoding="utf-8")


def test_scan_detects_layout(tmp_path):
    _make_project(tmp_path)
    scan = init_project.scan_project(tmp_path)
    assert "pyproject.toml" in scan["manifests"]
    assert "src" in scan["directories"]
    assert scan["test_dirs"] == ["tests"]


def test_detect_commands(tmp_path):
    _make_project(tmp_path)
    scan = init_project.scan_project(tmp_path)
    assert "python -m pytest -q" in init_project.detect_commands(scan)


def test_render_has_expected_sections(tmp_path):
    _make_project(tmp_path)
    text = init_project.render_agents_md(init_project.scan_project(tmp_path))
    assert "# AGENTS.md" in text
    assert "## Project layout" in text
    assert "## Build and verification commands" in text
    assert "`src/`" in text
    assert "python -m pytest -q" in text


def test_write_refuses_overwrite_without_force(tmp_path):
    _make_project(tmp_path)
    target = init_project.write_agents_md(tmp_path)
    assert target.is_file()
    with pytest.raises(FileExistsError):
        init_project.write_agents_md(tmp_path)
    init_project.write_agents_md(tmp_path, force=True)


def test_cli_init_command(tmp_path, monkeypatch):
    _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--help"]) == 0
    assert main(["init"]) == 0
    assert (tmp_path / "AGENTS.md").is_file()
    assert main(["init"]) == 1
    assert main(["init", "--force"]) == 0
