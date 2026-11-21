"""C8.5 — plugin/skill supply-chain review with permission diffs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from keel.supply_chain import (permission_diff, review_summary,
                               skill_capabilities)


@dataclass
class FakeSkill:
    name: str
    scope: str
    frontmatter: dict
    body: str
    trusted: bool = True


def test_declared_and_inferred_capabilities():
    skill = FakeSkill(
        "demo", "user", {"allowed-tools": ["read_file", "grep"]},
        "Please use write_file and run_shell to do the task.")
    caps = skill_capabilities(skill)
    assert "read_file" in caps and "write_file" in caps and "run_shell" in caps


def test_permission_diff_shows_gained_capabilities():
    skill = FakeSkill(
        "demo", "user", {"allowed-tools": ["read_file"]},
        "Use delete_file and git_push here.", trusted=True)
    diff = permission_diff(skill, {"read_file"})
    assert "delete_file" in diff["gained"]
    assert "git_push" in diff["gained"]
    assert diff["requires_review"] is True
    assert "delete files" in diff["summary"]


def test_trusted_skill_with_no_new_caps_needs_no_review():
    skill = FakeSkill("ok", "bundled", {"allowed-tools": ["read_file"]},
                      "Just read a file.", trusted=True)
    diff = permission_diff(skill, {"read_file"})
    assert diff["requires_review"] is False
    assert diff["summary"] == "no new capabilities requested"


def test_untrusted_project_skill_always_requires_review():
    skill = FakeSkill("proj", "project", {}, "read only", trusted=False)
    diff = permission_diff(skill, {"read_file"})
    assert diff["requires_review"] is True
    assert "untrusted" in diff["summary"]
