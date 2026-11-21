"""C7.1 — read other tools' instruction files as untrusted context."""

from __future__ import annotations

from keel.instructions import INSTRUCTION_FILES, build_attachment, discover


def test_discovers_other_tool_instruction_files(tmp_path):
    (tmp_path / ".cursorrules").write_text("cursor rules", encoding="utf-8")
    (tmp_path / ".windsurfrules").write_text("windsurf rules", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text(
        "copilot rules", encoding="utf-8")
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "rules").mkdir()
    (tmp_path / ".cursor" / "rules" / "python.md").write_text(
        "python rules", encoding="utf-8")
    found = discover(tmp_path)
    names = [path.as_posix() for path in found]
    assert any(name.endswith(".cursorrules") for name in names)
    assert any(name.endswith(".windsurfrules") for name in names)
    assert any(name.endswith("copilot-instructions.md") for name in names)
    assert any(name.endswith(".cursor/rules/python.md") for name in names)


def test_discovery_is_root_first(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    (parent / "AGENTS.md").write_text("parent guide", encoding="utf-8")
    (child / "AGENTS.md").write_text("child guide", encoding="utf-8")
    found = discover(child)
    assert len(found) == 2
    assert found[0].parent == parent
    assert found[1].parent == child


def test_attachment_marks_sources_as_untrusted(tmp_path):
    path = tmp_path / ".cursorrules"
    path.write_text("cursor rules", encoding="utf-8")
    text = build_attachment([path])
    assert "untrusted" in text.lower()
    assert "cursor rules" in text
