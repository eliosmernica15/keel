from __future__ import annotations

import json
from pathlib import Path

import pytest

from keel import skills_manager as sm
from keel.skills import Skill, SkillError


def make_skill_dir(tmp_path: Path, name: str = "demo-skill", desc: str = "demo desc") -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\nBody for {name}.\n",
        encoding="utf-8",
    )
    return d


def test_validate_and_list_managed(tmp_path):
    skill_dir = make_skill_dir(tmp_path)
    # install into user scope by monkeypatching target root via project scope
    project = tmp_path / "proj"
    project.mkdir()
    skill = sm.install(skill_dir, scope="project", project_root=project)
    assert skill.name == "demo-skill"
    managed = sm.list_managed(project)
    assert any(m["name"] == "demo-skill" for m in managed)
    assert sm.is_enabled("demo-skill") is True


def test_enable_disable(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    sm.set_enabled("demo-skill", False)
    assert sm.is_enabled("demo-skill") is False
    sm.set_enabled("demo-skill", True)
    assert sm.is_enabled("demo-skill") is True


def test_remove_skill(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    skill_dir = make_skill_dir(tmp_path)
    sm.install(skill_dir, scope="project", project_root=project)
    assert sm.remove("demo-skill", scope="project", project_root=project) is True
    assert sm.remove("demo-skill", scope="project", project_root=project) is False


def test_list_managed_prefers_project_scope_for_duplicate_skill_names(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    project_skill = make_skill_dir(tmp_path, "shared", "project copy")
    project_dest = project / ".keel" / "skills" / "project-folder"
    project_dest.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(project_skill, project_dest)

    user_root = tmp_path / "user-skills"
    bundled_root = tmp_path / "bundled-skills"
    for root, folder in ((user_root, "user-folder"), (bundled_root, "bundled-folder")):
        root.mkdir()
        dest = root / folder
        shutil.copytree(project_skill, dest)

    monkeypatch.setattr(sm, "default_roots",
                        lambda project_root=None: [
                            (project / ".keel" / "skills", "project"),
                            (user_root, "user"),
                            (bundled_root, "bundled"),
                        ])
    managed = sm.list_managed(project)
    shared = [row for row in managed if row["name"] == "shared"]
    assert len(shared) == 1
    assert shared[0]["scope"] == "project"


def test_select_skills(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    for name, desc in [("alpha", "alpha tooling"), ("beta", "beta testing")]:
        sm.install(make_skill_dir(tmp_path, name, desc), scope="project", project_root=project)
    selected = sm.select_skills("alpha", project_root=project)
    assert any(s.name == "alpha" for s in selected)


def test_install_invalid_skill_raises(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: bad\n---\nno desc\n", encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    with pytest.raises(SkillError):
        sm.install(bad, scope="project", project_root=project)


def test_update_skill(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    d1 = make_skill_dir(tmp_path, "upd", "v1")
    sm.install(d1, scope="project", project_root=project)
    d2 = tmp_path / "upd2"
    d2.mkdir()
    (d2 / "SKILL.md").write_text("---\nname: upd\ndescription: v2\n---\n\nv2 body\n", encoding="utf-8")
    s = sm.update("upd", d2, scope="project", project_root=project)
    assert s.description == "v2"
