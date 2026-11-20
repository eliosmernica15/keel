from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import skills as skills_mod
from .skills import Skill, SkillError, _load_file, default_roots, discover

STATE_PATH = Path(os.path.expanduser("~")) / ".keel" / "skills-state.json"


def _state() -> dict[str, bool]:
    if not STATE_PATH.is_file():
        return {}
    try:
        doc = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _save_state(state: dict[str, bool]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def is_enabled(name: str) -> bool:
    return bool(_state().get(name, True))


def set_enabled(name: str, enabled: bool) -> None:
    state = _state()
    state[name] = bool(enabled)
    _save_state(state)


def validate_skill(skill: Skill) -> list[str]:
    errors: list[str] = []
    if not skill.name:
        errors.append("missing name")
    if not skill.description:
        errors.append("missing description")
    if skill.injection_suspects:
        errors.append(f"injection suspects: {len(skill.injection_suspects)}")
    if not skill.trusted and skill.scope == "project":
        # project skills are untrusted by default; not an error, but report
        pass
    return errors


def discover_all(project_root: Path | None = None) -> list[Skill]:
    skills = discover(project_root)
    # attach enabled flag via state (Skill is frozen; return as-is, state queried separately)
    return skills


def select_skills(task: str, project_root: Path | None = None, limit: int = 5) -> list[Skill]:
    task_terms = set(w.lower() for w in task.replace("/", " ").split() if len(w) > 2)
    scored = []
    for skill in discover(project_root):
        if not is_enabled(skill.name):
            continue
        haystack = f"{skill.name} {skill.description}".lower()
        score = sum(1 for t in task_terms if t in haystack)
        if score > 0:
            scored.append((score, skill))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return [s for _, s in scored[:limit]]


def _target_root(scope: str, project_root: Path | None) -> Path:
    if scope == "user":
        return Path(os.path.expanduser("~")) / ".keel" / "skills"
    if scope == "project":
        if project_root is None:
            raise ValueError("project_root is required for project scope")
        return Path(project_root) / ".keel" / "skills"
    if scope == "bundled":
        raise ValueError("cannot install into bundled scope")
    raise ValueError(f"unknown scope: {scope}")


def install(source: str | Path, scope: str = "user",
           project_root: Path | None = None, name: str | None = None) -> Skill:
    src = Path(source)
    if src.is_file():
        if src.name != "SKILL.md":
            raise SkillError(f"expected SKILL.md, got {src.name}")
        skill_dir_src = src.parent
    elif src.is_dir():
        if not (src / "SKILL.md").is_file():
            raise SkillError(f"no SKILL.md in {src}")
        skill_dir_src = src
    else:
        raise SkillError(f"source not found: {src}")

    # Determine name from frontmatter if not given
    raw = (skill_dir_src / "SKILL.md").read_text(encoding="utf-8")
    fm, _ = skills_mod._parse_frontmatter(raw)
    skill_name = name or str(fm.get("name", "")).strip().lower()
    if not skill_name:
        raise SkillError("skill name missing")

    root = _target_root(scope, project_root)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / skill_name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(skill_dir_src, dest)

    skill = _load_file(dest / "SKILL.md", scope)
    errs = validate_skill(skill)
    if errs:
        shutil.rmtree(dest, ignore_errors=True)
        raise SkillError("; ".join(errs))
    return skill


def remove(name: str, scope: str = "user", project_root: Path | None = None) -> bool:
    root = _target_root(scope, project_root)
    target = root / name
    if not target.exists():
        return False
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return True


def update(name: str, source: str | Path, scope: str = "user",
          project_root: Path | None = None) -> Skill:
    return install(source, scope=scope, project_root=project_root, name=name)


def list_managed(project_root: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for path, scope in default_roots(project_root):
        if not path.exists():
            continue
        for child in sorted(path.iterdir()):
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                skill = _load_file(skill_md, scope)
            except SkillError as exc:
                out.append({"name": child.name, "scope": scope, "error": str(exc),
                            "enabled": is_enabled(child.name)})
                continue
            out.append({
                "name": skill.name,
                "description": skill.description,
                "scope": scope,
                "path": str(skill.path),
                "sha256": skill.sha256,
                "trusted": skill.trusted,
                "injection_suspects": list(skill.injection_suspects),
                "enabled": is_enabled(skill.name),
                "version": skill.frontmatter.get("version"),
            })
    return out
