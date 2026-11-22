"""B2.2 — Spec-driven mode with real state, task breakdown and approval gates.

A local, persistent workflow: write a spec → break it into tasks → implement →
verify → done. Each phase transition requires an explicit recorded approval,
so an agent cannot silently mark its own work complete. Evidence can be
attached to tasks and is required to complete the verify phase. Everything is
stored as JSON in a local state root; no external service is contacted.

This upgrades the earlier ``authoring.spec_scaffold`` descriptor into an
executable workflow while keeping that helper backward compatible.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

PHASES = ("spec", "tasks", "implement", "verify", "done")


def create_spec(goal: str, *, requirements: list[str] | None = None,
                out_of_scope: list[str] | None = None,
                name: str = "spec") -> dict:
    """Build a structured, reviewable specification for *goal*."""
    goal = str(goal).strip()
    if not goal:
        raise ValueError("goal must not be empty")
    reqs = [str(r).strip() for r in (requirements or []) if str(r).strip()]
    if not reqs:
        reqs = [f"Define and deliver: {goal}"]
    return {
        "name": name,
        "goal": goal,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spec": {
            "problem": goal,
            "requirements": [
                {"id": f"R{i}", "text": text, "status": "pending"}
                for i, text in enumerate(reqs, 1)],
            "out_of_scope": [str(s).strip() for s in (out_of_scope or [])
                             if str(s).strip()],
        },
        "tasks": [],
        "evidence": {},
        "approvals": {},
        "phase": "spec",
        "history": [{"phase": "spec", "at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}],
    }


def break_down_tasks(spec: dict) -> dict:
    """Turn requirements into dependency-ordered tasks (idempotent)."""
    if spec.get("phase") not in ("spec", "tasks"):
        raise ValueError(f"cannot break down tasks in phase {spec['phase']}")
    reqs = spec["spec"]["requirements"]
    tasks = [
        {"id": f"T{i}", "requirement": req["id"],
         "description": f"Implement {req['text']}",
         "depends_on": [f"T{i-1}"] if i > 1 else [],
         "status": "pending"}
        for i, req in enumerate(reqs, 1)
    ]
    tasks.append({"id": f"T{len(reqs)+1}", "requirement": "ALL",
                  "description": "Verify all requirements with evidence",
                  "depends_on": [f"T{i}" for i in range(1, len(reqs) + 1)],
                  "status": "pending"})
    spec["tasks"] = tasks
    if spec["phase"] == "spec":
        spec["phase"] = "tasks"
        spec["history"].append({"phase": "tasks", "at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return spec


def can_advance(spec: dict) -> bool:
    """Whether the current phase has its required approval."""
    phase = spec.get("phase")
    if phase == "done":
        return False
    if phase == "verify":
        # Verification needs evidence for every implementation task.
        impl = [t for t in spec.get("tasks", []) if t["requirement"] != "ALL"]
        return bool(impl) and all(t["id"] in spec.get("evidence", {})
                                  for t in impl)
    return spec.get("approvals", {}).get(phase, {}).get("approved", False)


def approve(spec: dict, *, approver: str = "owner", note: str = "") -> dict:
    """Record an approval for the current phase and advance the workflow.

    The verify phase also requires attached evidence before it can advance.
    """
    phase = spec.get("phase")
    if phase == "done":
        raise ValueError("workflow already complete")
    if phase == "verify" and not can_advance(spec):
        missing = [t["id"] for t in spec["tasks"]
                   if t["requirement"] != "ALL"
                   and t["id"] not in spec.get("evidence", {})]
        raise ValueError(f"verification evidence missing for: {missing}")
    spec.setdefault("approvals", {})[phase] = {
        "approved": True, "approver": str(approver), "note": str(note),
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    nxt = PHASES[PHASES.index(phase) + 1]
    spec["phase"] = nxt
    spec["history"].append({"phase": nxt, "at": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return spec


def record_evidence(spec: dict, task_id: str, evidence: str) -> dict:
    """Attach verification evidence to a task (required to finish verify)."""
    ids = {t["id"] for t in spec.get("tasks", [])}
    if task_id not in ids:
        raise ValueError(f"unknown task: {task_id}")
    spec.setdefault("evidence", {})[task_id] = str(evidence)
    return spec


def set_task_status(spec: dict, task_id: str, status: str) -> dict:
    if status not in ("pending", "in_progress", "done"):
        raise ValueError("invalid task status")
    for task in spec.get("tasks", []):
        if task["id"] == task_id:
            deps = task.get("depends_on", [])
            if status in ("in_progress", "done"):
                unmet = [d for d in deps if next(
                    (t for t in spec["tasks"] if t["id"] == d), {}
                ).get("status") != "done"]
                if unmet:
                    raise ValueError(f"unmet dependencies: {unmet}")
            task["status"] = status
            return spec
    raise ValueError(f"unknown task: {task_id}")


def status(spec: dict) -> dict:
    tasks = spec.get("tasks", [])
    done = sum(1 for t in tasks if t["status"] == "done")
    return {
        "name": spec.get("name"), "goal": spec.get("goal"),
        "phase": spec.get("phase"), "can_advance": can_advance(spec),
        "requirements": len(spec["spec"]["requirements"]),
        "tasks_total": len(tasks), "tasks_done": done,
        "evidence_count": len(spec.get("evidence", {})),
        "approvals": sorted(spec.get("approvals", {})),
    }


class SpecStore:
    """Persist spec workflows in a local state root."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "specs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
            raise ValueError("invalid spec name")
        return self.root / f"{name}.json"

    def save(self, spec: dict) -> Path:
        path = self._path(spec["name"])
        path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, name: str) -> dict:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
