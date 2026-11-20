from __future__ import annotations

import pytest
from pathlib import Path

from keel import skills_manager as sm
from keel.skills import SkillError


def test_skill_path_traversal_rejected(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # Create a valid skill dir
    skill_dir = tmp_path / "evil"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ../../../etc/passwd\ndescription: evil\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillError):
        sm.install(skill_dir, scope="project", project_root=project)


def test_skill_invalid_name_rejected(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    skill_dir = tmp_path / "badname"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: INVALID_NAME\ndescription: bad\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillError):
        sm.install(skill_dir, scope="project", project_root=project)


def test_skill_remove_traversal_rejected(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    with pytest.raises(SkillError):
        sm.remove("../../../etc", scope="project", project_root=project)


def test_skill_remove_nonexistent(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    assert sm.remove("nonexistent-skill", scope="project", project_root=project) is False
